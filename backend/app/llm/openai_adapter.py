import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    StreamChunk,
    UniversalLLMInterface,
)
from app.llm.client_headers import browser_like_default_headers
from app.llm.dsml_tool_parser import contains_dsml, parse_dsml_tool_calls
from app.llm.retry import retry_async
from app.models.llm_config import ResolvedLLMConfig

logger = logging.getLogger(__name__)

# Exceptions that warrant a retry (transient / server-side failures).
_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


class OpenAIAdapter(UniversalLLMInterface):
    """OpenAI API 适配器 - 支持原生工具调用和流式输出"""

    def __init__(self, config: ResolvedLLMConfig, *, on_retry=None, cancel_event: asyncio.Event | None = None):
        self.config = config
        self.model = config.model
        self.on_retry = on_retry
        self.cancel_event = cancel_event

        self.client = AsyncOpenAI(
            api_key=config.api_key or "reflexion-placeholder-key",
            base_url=config.base_url if config.base_url else None,
            default_headers=browser_like_default_headers(),
        )

        logger.info("OpenAI 适配器初始化完成, 模型: %s", self.model)

    async def complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> LLMResponse:
        """
        同步补全（支持工具调用），带指数退避重试

        Args:
            messages: 消息列表
            tools: 可用工具列表

        Returns:
            LLMResponse: 响应结果
        """
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        response = await retry_async(
            lambda: self.client.chat.completions.create(**kwargs),
            retryable_exceptions=_RETRYABLE,
            on_retry=self.on_retry,
            raise_retry_exhausted=True,
            cancel_event=self.cancel_event,
        )

        return self._parse_response(response)

    _MAX_STREAM_RETRIES = 3

    async def stream_complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> AsyncIterator[StreamChunk]:
        """
        流式补全（支持工具调用），连接阶段和流早期断连均带重试

        Args:
            messages: 消息列表
            tools: 可用工具列表

        Yields:
            StreamChunk: 流式输出块
        """
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        for stream_attempt in range(self._MAX_STREAM_RETRIES):
            stream = await retry_async(
                lambda: self.client.chat.completions.create(**kwargs),
                retryable_exceptions=_RETRYABLE,
                on_retry=self.on_retry,
                raise_retry_exhausted=True,
                cancel_event=self.cancel_event,
            )

            current_tool_calls: dict[int, dict] = {}
            _next_tc_index = 0
            _dsml_prefix = "<|DSML|"
            _content_buf = ""
            _dsml_detected = False
            _yielded_cursor = 0
            yielded_any = False

            try:
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    finish_reason = chunk.choices[0].finish_reason

                    reasoning_delta = self._extract_reasoning_delta(delta)
                    if reasoning_delta:
                        yielded_any = True
                        yield StreamChunk(type="reasoning", reasoning_content=reasoning_delta)

                    if delta.content:
                        _content_buf += delta.content

                        if not _dsml_detected:
                            idx = _content_buf.find(_dsml_prefix)
                            if idx != -1:
                                _dsml_detected = True
                                if idx > _yielded_cursor:
                                    yielded_any = True
                                    yield StreamChunk(
                                        type="content",
                                        content=_content_buf[_yielded_cursor:idx],
                                    )
                                _yielded_cursor = len(_content_buf)
                            else:
                                safe_end = len(_content_buf)
                                for i in range(1, min(len(_dsml_prefix), len(_content_buf) + 1)):
                                    if _dsml_prefix.startswith(_content_buf[-i:]):
                                        safe_end = len(_content_buf) - i
                                        break
                                if safe_end > _yielded_cursor:
                                    yielded_any = True
                                    yield StreamChunk(
                                        type="content",
                                        content=_content_buf[_yielded_cursor:safe_end],
                                    )
                                    _yielded_cursor = safe_end

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            tc_index = tc.index

                            if tc_index not in current_tool_calls:
                                if tc.id and tc_index != _next_tc_index:
                                    pass
                                elif not tc.id and tc_index in current_tool_calls and current_tool_calls[tc_index]["arguments"].rstrip().endswith("}"):
                                    _next_tc_index += 1
                                    tc_index = _next_tc_index
                                else:
                                    _next_tc_index = max(_next_tc_index, tc_index)

                                current_tool_calls[tc_index] = {
                                    "id": tc.id or "",
                                    "name": "",
                                    "arguments": "",
                                }
                                _next_tc_index = max(_next_tc_index, tc_index)
                            elif tc.id:
                                current_tool_calls[tc_index]["id"] = tc.id

                            if tc.function:
                                if tc.function.name:
                                    current_tool_calls[tc_index]["name"] = tc.function.name
                                if tc.function.arguments:
                                    existing = current_tool_calls[tc_index]["arguments"]
                                    if existing.rstrip().endswith("}") and tc.function.arguments.lstrip().startswith("{"):
                                        _next_tc_index += 1
                                        new_idx = _next_tc_index
                                        current_tool_calls[new_idx] = {
                                            "id": tc.id or "",
                                            "name": tc.function.name or current_tool_calls[tc_index]["name"],
                                            "arguments": tc.function.arguments,
                                        }
                                        tc_index = new_idx
                                    else:
                                        current_tool_calls[tc_index]["arguments"] += tc.function.arguments

                    if finish_reason:
                        has_structured_tc = bool(current_tool_calls)

                        if has_structured_tc:
                            yield StreamChunk(
                                type="tool_calls",
                                tool_calls=self._build_structured_tool_calls(current_tool_calls),
                                finish_reason=finish_reason,
                            )
                        elif _dsml_detected:
                            result = parse_dsml_tool_calls(_content_buf)
                            if result.tool_calls:
                                yield StreamChunk(
                                    type="tool_calls",
                                    tool_calls=result.tool_calls,
                                    finish_reason=finish_reason,
                                )
                            else:
                                remaining = _content_buf[_yielded_cursor:]
                                if remaining:
                                    yield StreamChunk(type="content", content=remaining)
                                yield StreamChunk(type="done", finish_reason=finish_reason)
                        else:
                            remaining = _content_buf[_yielded_cursor:]
                            if remaining:
                                yield StreamChunk(type="content", content=remaining)
                            yield StreamChunk(type="done", finish_reason=finish_reason)

                        return
            except Exception as e:
                if not yielded_any and stream_attempt < self._MAX_STREAM_RETRIES - 1:
                    logger.warning(
                        "OpenAI 流式连接中断 (attempt %d/%d), 重试: %s",
                        stream_attempt + 1,
                        self._MAX_STREAM_RETRIES,
                        e,
                    )
                    continue
                logger.error("OpenAI 流式读取失败: %s", e)
                yield StreamChunk(type="error", error=str(e))
                return

    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.model

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """将内部消息格式转换为 OpenAI 格式"""
        openai_messages = []

        for msg in messages:
            openai_msg: dict[str, Any] = {"role": msg.role}

            if msg.content is not None:
                openai_msg["content"] = msg.content
            elif msg.role == "tool":
                openai_msg["content"] = ""

            if msg.tool_calls:
                openai_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ]

            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id

            openai_messages.append(openai_msg)

        return openai_messages

    def _convert_tools(self, tools: list[LLMToolDefinition]) -> list[dict[str, Any]]:
        """将内部工具定义转换为 OpenAI 格式"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    @staticmethod
    def _split_concatenated_json(raw: str) -> list[str]:
        """Split concatenated JSON objects like }{ or }\\s*{ that some LLM
        providers emit when multiple tool_calls share the same streaming index.

        Uses a simple brace-depth scanner so it works even when inner strings
        contain nested braces (as long as they are properly quoted/escaped).
        """
        results: list[str] = []
        depth = 0
        start = -1
        in_string = False
        escape = False

        for i, ch in enumerate(raw):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    results.append(raw[start:i + 1])
                    start = -1

        if depth != 0:
            results.append(raw)

        return results or [raw]

    def _build_structured_tool_calls(
        self, current_tool_calls: dict[int, dict]
    ) -> list[LLMToolCall]:
        """Aggregate streaming tool_call deltas into LLMToolCall list."""
        tool_calls = []
        next_idx = max(current_tool_calls.keys()) + 1 if current_tool_calls else 0

        for idx in sorted(current_tool_calls.keys()):
            tc_data = current_tool_calls[idx]
            raw_args = tc_data["arguments"]

            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                fragments = self._split_concatenated_json(raw_args)
                if len(fragments) > 1:
                    parsed = []
                    for frag in fragments:
                        try:
                            parsed.append(json.loads(frag))
                        except json.JSONDecodeError:
                            parsed.append(None)

                    if parsed[0] is not None:
                        args = parsed[0]
                        for extra_idx, extra_args in enumerate(parsed[1:], start=1):
                            if extra_args is not None:
                                tool_calls.append(
                                    LLMToolCall(
                                        id=tc_data["id"] or f"call_{next_idx}",
                                        name=tc_data["name"],
                                        arguments=extra_args,
                                    )
                                )
                                next_idx += 1
                    else:
                        raw_fragment = raw_args[:200] if raw_args else ""
                        logger.warning(
                            "Streaming tool arguments JSON parse failed for tool=%s, raw fragment: %s",
                            tc_data["name"], raw_fragment,
                        )
                        args = {
                            "__reflexion_parse_error": "Tool arguments JSON parse failed — the model output was malformed. "
                                            "Please retry the tool call with valid parameters.",
                            "__reflexion_raw_arguments": raw_fragment,
                        }
                else:
                    raw_fragment = raw_args[:200] if raw_args else ""
                    logger.warning(
                        "Streaming tool arguments JSON parse failed for tool=%s, raw fragment: %s",
                        tc_data["name"], raw_fragment,
                    )
                    args = {
                        "__reflexion_parse_error": "Tool arguments JSON parse failed — the model output was malformed. "
                                        "Please retry the tool call with valid parameters.",
                        "__reflexion_raw_arguments": raw_fragment,
                    }

            tool_calls.append(
                LLMToolCall(
                    id=tc_data["id"] or f"call_{idx}",
                    name=tc_data["name"],
                    arguments=args,
                )
            )
        return tool_calls

    def _parse_response(self, response) -> LLMResponse:
        """解析 OpenAI 响应为内部格式"""
        choice = response.choices[0]
        message = choice.message

        # 解析 tool_calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    raw_fragment = tc.function.arguments[:200] if tc.function.arguments else ""
                    logger.warning(
                        "Non-streaming tool arguments JSON parse failed for tool=%s, raw fragment: %s",
                        tc.function.name, raw_fragment,
                    )
                    args = {
                        "_parse_error": "Tool arguments JSON parse failed — the model output was malformed. "
                                        "Please retry the tool call with valid parameters.",
                        "_raw_arguments": raw_fragment,
                    }

                tool_calls.append(LLMToolCall(id=tc.id, name=tc.function.name, arguments=args))

        content = message.content or ""
        reasoning_content = self._extract_reasoning_message(message)

        # 无结构化 tool_calls 时，检查文本中的 DSML 工具调用
        if not tool_calls and content and contains_dsml(content):
            result = parse_dsml_tool_calls(content)
            if result.tool_calls:
                tool_calls = result.tool_calls
                content = result.clean_content

        # 确定 finish_reason
        finish_reason = choice.finish_reason or "stop"
        if tool_calls:
            finish_reason = "tool_calls"

        if not content and not tool_calls:
            logger.warning(
                "OpenAI 返回空响应, model=%s, finish_reason=%s, message_role=%s, "
                "可能是: 1) 模型不支持工具调用但被强制使用 2) max_tokens 不足 3) 代理服务异常",
                response.model,
                choice.finish_reason,
                message.role,
            )
            if choice.finish_reason == "length":
                logger.warning(
                    "finish_reason=length: 模型输出被截断，建议增大 max_tokens (当前: %s)",
                    self.config.max_tokens,
                )

        return LLMResponse(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            if response.usage
            else {},
        )

    @staticmethod
    def _extract_reasoning_delta(delta: Any) -> str:
        for attr in ("reasoning_content", "reason_content", "reasoning"):
            value = getattr(delta, attr, None)
            text = OpenAIAdapter._coerce_reasoning_text(value)
            if text:
                return text
        return ""

    @staticmethod
    def _extract_reasoning_message(message: Any) -> str:
        for attr in ("reasoning_content", "reason_content", "reasoning"):
            value = getattr(message, attr, None)
            text = OpenAIAdapter._coerce_reasoning_text(value)
            if text:
                return text
        return ""

    @staticmethod
    def _coerce_reasoning_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
                    continue
                content = getattr(item, "content", None)
                if isinstance(content, str):
                    parts.append(content)
            return "".join(parts)
        return ""
