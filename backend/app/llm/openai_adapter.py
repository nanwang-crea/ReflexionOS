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
            base_url=config.base_url if config.base_url else None
        )
        
        logger.info("OpenAI 适配器初始化完成, 模型: %s", self.model)
    
    async def complete(
        self,
        messages: list[LLMMessage],
        tools: list[LLMToolDefinition] = None
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
        self,
        messages: list[LLMMessage],
        tools: list[LLMToolDefinition] = None
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

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # 流式输出 content
                if delta.content:
                    yield StreamChunk(type="content", content=delta.content)

                # 处理 tool_calls（流式）
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": ""
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
                    # 如果有 tool_calls，聚合后发送
                    if current_tool_calls:
                        tool_calls = []
                        for idx in sorted(current_tool_calls.keys()):
                            tc_data = current_tool_calls[idx]
                            try:
                                args = json.loads(tc_data["arguments"])
                            except json.JSONDecodeError:
                                args = {}

                            tool_calls.append(LLMToolCall(
                                id=tc_data["id"] or f"call_{idx}",
                                name=tc_data["name"],
                                arguments=args
                            ))

                        yield StreamChunk(
                            type="tool_calls",
                            tool_calls=tool_calls,
                            finish_reason=finish_reason
                        )
                    else:
                        yield StreamChunk(
                            type="done",
                            finish_reason=finish_reason
                        )

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
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
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
                    "parameters": tool.parameters
                }
            }
            for tool in tools
        ]
    
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
                
                tool_calls.append(LLMToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args
                ))
        
        # 确定 finish_reason
        finish_reason = choice.finish_reason or "stop"
        if tool_calls:
            finish_reason = "tool_calls"
        
        content = message.content or ""
        
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
                "total_tokens": response.usage.total_tokens
            } if response.usage else {}
        )
