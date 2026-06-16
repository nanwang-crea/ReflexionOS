import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMToolCall(BaseModel):
    """统一的工具调用结构"""

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMToolDefinition(BaseModel):
    """统一的工具定义结构"""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class LLMMessage(BaseModel):
    """统一的消息结构"""

    role: str
    content: str | list[dict] | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # 用于 tool 角色消息

    def to_dict(self) -> dict[str, Any]:
        result = {"role": self.role}
        if self.content:
            result["content"] = self.content
        if self.tool_calls:
            result["tool_calls"] = [tc.model_dump() for tc in self.tool_calls]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result


class LLMResponse(BaseModel):
    """统一的 LLM 响应结构"""

    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"  # stop, tool_calls, length
    model: str = ""
    usage: dict[str, int] = Field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def has_content(self) -> bool:
        return bool(self.content)


class StreamChunk(BaseModel):
    """流式输出块"""

    type: str  # content, reasoning, tool_calls, done, error
    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    error: str | None = None


class UniversalLLMInterface(ABC):
    """统一的 LLM 接口，所有 LLM 适配器必须实现此接口"""

    @abstractmethod
    async def complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> LLMResponse:
        """
        同步补全接口

        Args:
            messages: 消息列表
            tools: 可用工具列表

        Returns:
            LLMResponse: LLM 响应结果
        """
        pass

    @abstractmethod
    async def stream_complete(
        self, messages: list[LLMMessage], tools: list[LLMToolDefinition] = None
    ) -> AsyncIterator[StreamChunk]:
        """
        流式补全接口（支持工具调用）

        Args:
            messages: 消息列表
            tools: 可用工具列表

        Yields:
            StreamChunk: 流式输出块
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """获取当前使用的模型名称"""
        pass

    async def stream_collect(
        self,
        messages: list[LLMMessage],
        tools: list[LLMToolDefinition] | None = None,
        *,
        on_content: Callable[[str], Awaitable[None]] | None = None,
        on_reasoning: Callable[[str], Awaitable[None]] | None = None,
        max_empty_retries: int = 3,
    ) -> LLMResponse:
        """
        流式调用并收集完整响应

        封装了流式收集和空响应重试逻辑，调用方只需关心结果。

        Args:
            messages: 消息列表
            tools: 工具定义列表
            on_content: 内容回调（用于实时推送）
            on_reasoning: 推理内容回调
            max_empty_retries: 空响应最大重试次数

        Returns:
            LLMResponse: 完整响应
        """
        for attempt in range(max_empty_retries + 1):
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls: list[LLMToolCall] = []
            finish_reason = "stop"

            async for chunk in self.stream_complete(messages, tools):
                if chunk.type == "content" and chunk.content:
                    content_parts.append(chunk.content)
                    if on_content:
                        await on_content(chunk.content)
                elif chunk.type == "reasoning" and chunk.reasoning_content:
                    reasoning_parts.append(chunk.reasoning_content)
                    if on_reasoning:
                        await on_reasoning(chunk.reasoning_content)
                elif chunk.type == "tool_calls":
                    tool_calls = chunk.tool_calls
                    finish_reason = chunk.finish_reason or "tool_calls"
                    break
                elif chunk.type == "done":
                    finish_reason = chunk.finish_reason or "stop"
                    break
                elif chunk.type == "error":
                    if attempt < max_empty_retries:
                        break
                    raise RuntimeError(chunk.error or "LLM 流式调用失败")

            response = LLMResponse(
                content="".join(content_parts),
                reasoning_content="".join(reasoning_parts) or None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                model=self.get_model_name(),
            )

            # 有内容或工具调用，直接返回
            if response.has_content or response.has_tool_calls:
                return response

            # 空响应重试
            if attempt < max_empty_retries:
                continue

        return response
