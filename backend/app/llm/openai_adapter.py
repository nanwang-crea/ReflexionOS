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
from app.llm.dsml_tool_parser import contains_dsml, parse_dsml_tool_calls
from app.llm.retry import retry_async
from app.models.llm_config import ResolvedLLMConfig

logger = logging.getLogger(__name__)

# Exceptions that warrant a retry (transient / server-side failures).
_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


class OpenAIAdapter(UniversalLLMInterface):
    """OpenAI API 适配器 - 支持原生工具调用和流式输出"""

    def __init__(self, config: ResolvedLLMConfig, *, on_retry=None):
        self.config = config
        self.model = config.model
        self.on_retry = on_retry

        self.client = AsyncOpenAI(
            api_key=config.api_key or "reflexion-placeholder-key",
            base_url=config.base_url if config.base_url else None,
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
        )

        return self._parse_response(response)

    async def stream_complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> AsyncIterator[StreamChunk]:
        """
        流式补全（支持工具调用），连接阶段带指数退避重试

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

        # Retry at connection-establishment level only.
        # Once the stream is opened, transient errors within the stream
        # cannot be safely retried (partial output already yielded).
        stream = await retry_async(
            lambda: self.client.chat.completions.create(**kwargs),
            retryable_exceptions=_RETRYABLE,
            on_retry=self.on_retry,
            raise_retry_exhausted=True,
        )

        # 收集 tool_calls（流式时需要聚合）
        current_tool_calls: dict[int, dict] = {}

        # DSML detection state
        _dsml_prefix = "<|DSML|"
        _content_buf = ""
        _dsml_detected = False
        _yielded_cursor = 0

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # 流式输出 content（含 DSML 检测）
                if delta.content:
                    _content_buf += delta.content

                    if not _dsml_detected:
                        idx = _content_buf.find(_dsml_prefix)
                        if idx != -1:
                            _dsml_detected = True
                            if idx > _yielded_cursor:
                                yield StreamChunk(
                                    type="content",
                                    content=_content_buf[_yielded_cursor:idx],
                                )
                            _yielded_cursor = len(_content_buf)
                        else:
                            # Hold back tail that could be a partial <|DSML| prefix
                            safe_end = len(_content_buf)
                            for i in range(1, min(len(_dsml_prefix), len(_content_buf) + 1)):
                                if _dsml_prefix.startswith(_content_buf[-i:]):
                                    safe_end = len(_content_buf) - i
                                    break
                            if safe_end > _yielded_cursor:
                                yield StreamChunk(
                                    type="content",
                                    content=_content_buf[_yielded_cursor:safe_end],
                                )
                                _yielded_cursor = safe_end

                # 处理 tool_calls（流式，结构化路径）
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        elif tc.id:
                            current_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                current_tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                current_tool_calls[idx]["arguments"] += tc.function.arguments

                # 流式结束时处理
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

                    break
        except Exception as e:
            logger.error("OpenAI 流式读取失败: %s", e)
            yield StreamChunk(type="error", error=str(e))

    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.model

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """将内部消息格式转换为 OpenAI 格式"""
        openai_messages = []

        for msg in messages:
            openai_msg: dict[str, Any] = {"role": msg.role}

            if msg.content:
                openai_msg["content"] = msg.content

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

    def _build_structured_tool_calls(
        self, current_tool_calls: dict[int, dict]
    ) -> list[LLMToolCall]:
        """Aggregate streaming tool_call deltas into LLMToolCall list."""
        tool_calls = []
        for idx in sorted(current_tool_calls.keys()):
            tc_data = current_tool_calls[idx]
            try:
                args = json.loads(tc_data["arguments"])
            except json.JSONDecodeError:
                args = {}

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
                    logger.warning("工具参数解析失败: %s", tc.function.arguments)
                    args = {}

                tool_calls.append(LLMToolCall(id=tc.id, name=tc.function.name, arguments=args))

        content = message.content or ""

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
                "OpenAI 返回空响应, model=%s, finish_reason=%s",
                response.model,
                choice.finish_reason,
            )

        return LLMResponse(
            content=content,
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
