import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from app.errors import LLMRetryExhaustedError
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
from app.llm.observability import (
    LLMCallObservabilityContext,
    get_llm_observability_context,
)
from app.llm.retry import retry_async
from app.models.llm_config import ResolvedLLMConfig
from app.models.observability import ObservabilityEventCreate
from app.observability.pricing import ProviderRequestCostCalculator

logger = logging.getLogger(__name__)

# Exceptions that warrant a retry (transient / server-side failures).
_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


class OpenAIAdapter(UniversalLLMInterface):
    """OpenAI API 适配器 - 支持原生工具调用和流式输出"""

    def __init__(
        self,
        config: ResolvedLLMConfig,
        *,
        on_retry=None,
        cancel_event: asyncio.Event | None = None,
        observability_collector=None,
        observability_base_context: LLMCallObservabilityContext | None = None,
    ):
        self.config = config
        self.model = config.model
        self.on_retry = on_retry
        self.cancel_event = cancel_event
        self.observability_collector = observability_collector
        self.observability_base_context = observability_base_context
        self._cost_calculator = None

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

        observability = self._resolve_observability_context()
        logical_call_id = self._new_id("logical")
        logical_started_at = self._utc_now()
        self._record_logical_event(
            logical_call_id,
            status="running",
            occurred_at=logical_started_at,
            started_at=logical_started_at,
            observability=observability,
        )

        attempt_index = -1

        async def create_with_observability():
            nonlocal attempt_index
            attempt_index += 1
            request_metric_id = self._new_id("request")
            request_started_at = self._utc_now()
            self._record_provider_event(
                request_metric_id,
                logical_call_id=logical_call_id,
                request_attempt_index=attempt_index,
                status="running",
                occurred_at=request_started_at,
                started_at=request_started_at,
                observability=observability,
            )
            try:
                response = await self.client.chat.completions.create(**kwargs)
            except BaseException as exc:
                self._record_provider_event(
                    request_metric_id,
                    logical_call_id=logical_call_id,
                    request_attempt_index=attempt_index,
                    status=self._terminal_status_for_error(exc),
                    occurred_at=self._utc_now(),
                    started_at=request_started_at,
                    error=exc if isinstance(exc, Exception) else None,
                    observability=observability,
                )
                raise

            self._record_provider_event(
                request_metric_id,
                logical_call_id=logical_call_id,
                request_attempt_index=attempt_index,
                status="completed",
                occurred_at=self._utc_now(),
                started_at=request_started_at,
                response=response,
                finish_reason=self._extract_finish_reason(response),
                observability=observability,
            )
            return response

        try:
            response = await retry_async(
                create_with_observability,
                retryable_exceptions=_RETRYABLE,
                on_retry=self.on_retry,
                raise_retry_exhausted=True,
                cancel_event=self.cancel_event,
            )
            parsed = self._parse_response(response)
        except BaseException as exc:
            self._record_logical_event(
                logical_call_id,
                status=self._terminal_status_for_error(exc),
                occurred_at=self._utc_now(),
                started_at=logical_started_at,
                error=(
                    self._unwrap_retry_error(exc)
                    if isinstance(exc, Exception)
                    else None
                ),
                observability=observability,
            )
            raise

        self._record_logical_event(
            logical_call_id,
            status="completed",
            occurred_at=self._utc_now(),
            started_at=logical_started_at,
            observability=observability,
        )
        return parsed

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
            "stream_options": {"include_usage": True},
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        observability = self._resolve_observability_context()
        logical_call_id = self._new_id("logical")
        logical_started_at = self._utc_now()
        self._record_logical_event(
            logical_call_id,
            status="running",
            occurred_at=logical_started_at,
            started_at=logical_started_at,
            observability=observability,
        )

        attempt_index = -1

        for stream_attempt in range(self._MAX_STREAM_RETRIES):
            active_request: dict[str, Any] | None = None

            async def create_stream_with_observability():
                nonlocal attempt_index, active_request
                attempt_index += 1
                request_metric_id = self._new_id("request")
                request_started_at = self._utc_now()
                active_request = {
                    "metric_id": request_metric_id,
                    "started_at": request_started_at,
                    "attempt_index": attempt_index,
                }
                self._record_provider_event(
                    request_metric_id,
                    logical_call_id=logical_call_id,
                    request_attempt_index=attempt_index,
                    status="running",
                    occurred_at=request_started_at,
                    started_at=request_started_at,
                    observability=observability,
                )
                try:
                    stream = await self.client.chat.completions.create(**kwargs)
                except BaseException as exc:
                    self._record_provider_event(
                        request_metric_id,
                        logical_call_id=logical_call_id,
                        request_attempt_index=attempt_index,
                        status=self._terminal_status_for_error(exc),
                        occurred_at=self._utc_now(),
                        started_at=request_started_at,
                        error=exc if isinstance(exc, Exception) else None,
                        observability=observability,
                    )
                    active_request = None
                    raise

                active_request["provider_request_id"] = self._extract_provider_request_id(stream)
                return stream

            try:
                stream = await retry_async(
                    create_stream_with_observability,
                    retryable_exceptions=_RETRYABLE,
                    on_retry=self.on_retry,
                    raise_retry_exhausted=True,
                    cancel_event=self.cancel_event,
                )
            except BaseException as exc:
                self._record_logical_event(
                    logical_call_id,
                    status=self._terminal_status_for_error(exc),
                    occurred_at=self._utc_now(),
                    started_at=logical_started_at,
                    error=(
                        self._unwrap_retry_error(exc)
                        if isinstance(exc, Exception)
                        else None
                    ),
                    observability=observability,
                )
                raise

            current_tool_calls: dict[int, dict] = {}
            _next_tc_index = 0
            _dsml_prefix = "<|DSML|"
            _content_buf = ""
            _dsml_detected = False
            _yielded_cursor = 0
            yielded_any = False
            usage_payload: dict[str, Any] = {}

            final_finish_reason: str | None = None

            try:
                async for chunk in stream:
                    usage_payload = self._extract_usage_payload(getattr(chunk, "usage", None))
                    if not getattr(chunk, "choices", None):
                        continue

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
                        final_finish_reason = finish_reason
                        continue
            except BaseException as e:
                terminal_status = self._terminal_status_for_error(e)
                if active_request is not None:
                    self._record_provider_event(
                        active_request["metric_id"],
                        logical_call_id=logical_call_id,
                        request_attempt_index=active_request["attempt_index"],
                        status=terminal_status,
                        occurred_at=self._utc_now(),
                        started_at=active_request["started_at"],
                        provider_request_id=active_request.get("provider_request_id"),
                        usage_payload=usage_payload,
                        error=e if isinstance(e, Exception) else None,
                        observability=observability,
                    )
                if self._is_cancellation_error(e):
                    self._record_logical_event(
                        logical_call_id,
                        status=terminal_status,
                        occurred_at=self._utc_now(),
                        started_at=logical_started_at,
                        error=e if isinstance(e, Exception) else None,
                        observability=observability,
                    )
                    raise
                if not yielded_any and stream_attempt < self._MAX_STREAM_RETRIES - 1:
                    logger.warning(
                        "OpenAI 流式连接中断 (attempt %d/%d), 重试: %s",
                        stream_attempt + 1,
                        self._MAX_STREAM_RETRIES,
                        e,
                    )
                    continue
                logger.error("OpenAI 流式读取失败: %s", e)
                self._record_logical_event(
                    logical_call_id,
                    status=terminal_status,
                    occurred_at=self._utc_now(),
                    started_at=logical_started_at,
                    error=e if isinstance(e, Exception) else None,
                    observability=observability,
                )
                yield StreamChunk(type="error", error=str(e))
                return

            if final_finish_reason is not None:
                has_structured_tc = bool(current_tool_calls)
                if active_request is not None:
                    self._record_provider_event(
                        active_request["metric_id"],
                        logical_call_id=logical_call_id,
                        request_attempt_index=active_request["attempt_index"],
                        status="completed",
                        occurred_at=self._utc_now(),
                        started_at=active_request["started_at"],
                        provider_request_id=active_request.get("provider_request_id"),
                        usage_payload=usage_payload,
                        finish_reason=final_finish_reason,
                        observability=observability,
                    )
                self._record_logical_event(
                    logical_call_id,
                    status="completed",
                    occurred_at=self._utc_now(),
                    started_at=logical_started_at,
                    observability=observability,
                )

                if has_structured_tc:
                    yield StreamChunk(
                        type="tool_calls",
                        tool_calls=self._build_structured_tool_calls(current_tool_calls),
                        finish_reason=final_finish_reason,
                    )
                elif _dsml_detected:
                    result = parse_dsml_tool_calls(_content_buf)
                    if result.tool_calls:
                        yield StreamChunk(
                            type="tool_calls",
                            tool_calls=result.tool_calls,
                            finish_reason=final_finish_reason,
                        )
                    else:
                        remaining = _content_buf[_yielded_cursor:]
                        if remaining:
                            yield StreamChunk(type="content", content=remaining)
                        yield StreamChunk(type="done", finish_reason=final_finish_reason)
                else:
                    remaining = _content_buf[_yielded_cursor:]
                    if remaining:
                        yield StreamChunk(type="content", content=remaining)
                    yield StreamChunk(type="done", finish_reason=final_finish_reason)
                return

            unexpected_end = RuntimeError("stream ended before finish_reason")
            if active_request is not None:
                self._record_provider_event(
                    active_request["metric_id"],
                    logical_call_id=logical_call_id,
                    request_attempt_index=active_request["attempt_index"],
                    status="failed",
                    occurred_at=self._utc_now(),
                    started_at=active_request["started_at"],
                    provider_request_id=active_request.get("provider_request_id"),
                    usage_payload=usage_payload,
                    error=unexpected_end,
                    observability=observability,
                )
            if not yielded_any and stream_attempt < self._MAX_STREAM_RETRIES - 1:
                logger.warning(
                    "OpenAI 流式输出提前结束 (attempt %d/%d)，准备重试",
                    stream_attempt + 1,
                    self._MAX_STREAM_RETRIES,
                )
                continue
            self._record_logical_event(
                logical_call_id,
                status="failed",
                occurred_at=self._utc_now(),
                started_at=logical_started_at,
                error=unexpected_end,
                observability=observability,
            )
            yield StreamChunk(type="error", error=str(unexpected_end))
            return

    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.model

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """将内部消息格式转换为 OpenAI 格式"""
        openai_messages = []

        for msg in messages:
            openai_msg: dict[str, Any] = {"role": msg.role}

            if isinstance(msg.content, list):
                openai_msg["content"] = [
                    self._convert_content_part(part) for part in msg.content
                ]
            elif msg.content is not None:
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

    def _convert_content_part(self, part: dict) -> dict:
        """将内部格式的内容部分转换为 OpenAI API 格式"""
        part_type = part.get("type")
        if part_type == "text":
            return {"type": "text", "text": part.get("text", "")}
        elif part_type == "image_url":
            # 内部格式: {"type": "image_url", "url": "..."} → OpenAI: {"type": "image_url", "image_url": {"url": "..."}}
            url = part.get("url") or part.get("image_url", {}).get("url")
            return {"type": "image_url", "image_url": {"url": url}}
        else:
            raise ValueError(f"未知的内容类型: {part_type}")

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

    def _resolve_observability_context(self) -> LLMCallObservabilityContext | None:
        override = get_llm_observability_context()
        if self.observability_base_context is None:
            return override
        return self.observability_base_context.merged(override)

    def _record_logical_event(
        self,
        logical_call_id: str,
        *,
        status: str,
        occurred_at: datetime,
        started_at: datetime,
        observability: LLMCallObservabilityContext | None,
        error: Exception | None = None,
    ) -> None:
        collector = self._resolve_observability_collector()
        if collector is None or observability is None:
            return

        payload = {
            "status": status,
            "call_kind": observability.call_kind or "main",
            "provider_id": self.config.provider_id,
            "model_id": self.config.model_id,
            "duration_ms": (
                self._duration_ms(started_at, occurred_at) if status != "running" else None
            ),
            "turn_id": observability.turn_id,
            "loop_iteration": observability.loop_iteration,
            "project_name_snapshot": observability.project_name_snapshot,
            "session_title_snapshot": observability.session_title_snapshot,
        }
        if error is not None:
            payload.update(self._error_payload(error))

        collector.record(
            ObservabilityEventCreate(
                entity_type="logical_call",
                entity_id=logical_call_id,
                event_type=f"logical.{status}",
                payload_json={key: value for key, value in payload.items() if value is not None},
                subject_project_id=observability.project_id,
                subject_session_id=observability.session_id,
                subject_run_id=observability.run_id,
                occurred_at=occurred_at,
            )
        )

    def _record_provider_event(
        self,
        request_metric_id: str,
        *,
        logical_call_id: str,
        request_attempt_index: int,
        status: str,
        occurred_at: datetime,
        started_at: datetime,
        observability: LLMCallObservabilityContext | None,
        response: Any | None = None,
        usage_payload: dict[str, Any] | None = None,
        finish_reason: str | None = None,
        error: Exception | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        collector = self._resolve_observability_collector()
        if collector is None or observability is None:
            return

        provider_request_id = provider_request_id or self._extract_provider_request_id(response)
        usage_data = usage_payload or self._extract_usage_payload(getattr(response, "usage", None))
        payload = {
            "logical_call_id": logical_call_id,
            "request_attempt_index": request_attempt_index,
            "provider_request_id": provider_request_id,
            "provider_id": self.config.provider_id,
            "model_id": self.config.model_id,
            "status": status,
            "duration_ms": (
                self._duration_ms(started_at, occurred_at) if status != "running" else None
            ),
            "finish_reason": finish_reason,
            **usage_data,
        }
        if status != "running":
            payload.update(
                self._pricing_payload(
                    provider_id=self.config.provider_id,
                    model_id=self.config.model_id,
                    started_at=started_at,
                    input_tokens=payload.get("input_tokens"),
                    output_tokens=payload.get("output_tokens"),
                    cached_input_tokens=payload.get("cached_input_tokens"),
                    estimated_input_tokens=payload.get("estimated_input_tokens"),
                    estimated_output_tokens=payload.get("estimated_output_tokens"),
                    input_usage_source=payload.get("input_usage_source", "unavailable"),
                    output_usage_source=payload.get("output_usage_source", "unavailable"),
                    cached_usage_source=payload.get("cached_usage_source", "unavailable"),
                )
            )
        if error is not None:
            payload.update(self._error_payload(error))

        collector.record(
            ObservabilityEventCreate(
                entity_type="provider_request",
                entity_id=request_metric_id,
                event_type=f"request.{status}",
                payload_json={key: value for key, value in payload.items() if value is not None},
                subject_project_id=observability.project_id,
                subject_session_id=observability.session_id,
                subject_run_id=observability.run_id,
                occurred_at=occurred_at,
            )
        )

    def _resolve_observability_collector(self):
        if self.observability_collector is not None:
            return self.observability_collector
        try:
            from app.app_services import observability_collector

            return observability_collector
        except Exception:
            return None

    def _pricing_payload(
        self,
        *,
        provider_id: str,
        model_id: str,
        started_at: datetime,
        input_tokens: int | None,
        output_tokens: int | None,
        cached_input_tokens: int | None,
        estimated_input_tokens: int | None,
        estimated_output_tokens: int | None,
        input_usage_source: str,
        output_usage_source: str,
        cached_usage_source: str,
    ) -> dict[str, Any]:
        collector = self._resolve_observability_collector()
        if collector is None:
            return {"cost_status": "unpriced"}

        if self._cost_calculator is None:
            self._cost_calculator = ProviderRequestCostCalculator(collector.db)

        cost = self._cost_calculator.compute(
            provider_id=provider_id,
            model_id=model_id,
            started_at=started_at,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            input_usage_source=input_usage_source,
            output_usage_source=output_usage_source,
            cached_usage_source=cached_usage_source,
        )
        return {
            "pricing_id": cost.pricing_id,
            "pricing_match_rule": cost.pricing_match_rule,
            "pricing_version": cost.pricing_version,
            "input_price_nano_usd_per_million": cost.input_price_nano_usd_per_million,
            "output_price_nano_usd_per_million": cost.output_price_nano_usd_per_million,
            "cached_input_price_nano_usd_per_million": (
                cost.cached_input_price_nano_usd_per_million
            ),
            "input_cost_nano_usd": cost.input_cost_nano_usd,
            "output_cost_nano_usd": cost.output_cost_nano_usd,
            "cached_input_cost_nano_usd": cost.cached_input_cost_nano_usd,
            "total_cost_nano_usd": cost.total_cost_nano_usd,
            "cost_status": cost.cost_status,
        }

    @staticmethod
    def _is_cancellation_error(error: BaseException) -> bool:
        return isinstance(error, (asyncio.CancelledError, GeneratorExit))

    def _terminal_status_for_error(self, error: BaseException) -> str:
        if self._is_cancellation_error(error):
            return "interrupted"
        return "failed"

    @staticmethod
    def _unwrap_retry_error(error: Exception) -> Exception:
        if isinstance(error, LLMRetryExhaustedError):
            return error.last_exception
        return error

    @staticmethod
    def _extract_usage_payload(usage: Any) -> dict[str, Any]:
        if usage is None:
            return {
                "input_usage_source": "unavailable",
                "output_usage_source": "unavailable",
                "cached_usage_source": "unavailable",
            }

        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        cached_tokens = getattr(prompt_details, "cached_tokens", None) if prompt_details else None

        return {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "cached_input_tokens": cached_tokens,
            "input_usage_source": "provider" if prompt_tokens is not None else "unavailable",
            "output_usage_source": "provider" if completion_tokens is not None else "unavailable",
            "cached_usage_source": "provider" if cached_tokens is not None else "unavailable",
        }

    @staticmethod
    def _extract_provider_request_id(response: Any) -> str | None:
        if response is None:
            return None

        for attr in ("_request_id", "request_id"):
            value = getattr(response, attr, None)
            if isinstance(value, str) and value:
                return value

        raw_response = getattr(response, "response", None)
        headers = getattr(raw_response, "headers", None)
        if headers is not None:
            for key in ("x-request-id", "request-id"):
                value = headers.get(key)
                if value:
                    return value
        return None

    @staticmethod
    def _extract_finish_reason(response: Any) -> str | None:
        try:
            return response.choices[0].finish_reason or "stop"
        except Exception:
            return None

    @staticmethod
    def _error_payload(error: Exception) -> dict[str, str]:
        return {
            "error_code": type(error).__name__,
            "error_message": str(error),
        }

    @staticmethod
    def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
        return max(0, int((finished_at - started_at).total_seconds() * 1000))

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12]}"

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
