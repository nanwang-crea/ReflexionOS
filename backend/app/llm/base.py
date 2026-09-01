"""LLM 适配层的核心数据结构与统一接口定义。

本模块定义了与具体 LLM 提供商（OpenAI/Claude/Ollama 等）无关的通用数据模型
（消息、工具调用、响应、流式输出块）以及所有适配器必须实现的抽象接口
UniversalLLMInterface，用于屏蔽不同厂商 API 格式差异，让上层业务代码
只需面向统一结构编程。
"""

import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """消息角色枚举，对齐主流 Chat Completion API 的角色定义"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMToolCall(BaseModel):
    """统一的工具调用结构

    id: 工具调用唯一标识，未提供时自动生成随机 id（用于关联后续 tool 角色的返回结果）
    name: 被调用的工具名称
    arguments: 调用参数，已解析为字典（而非原始 JSON 字符串）
    """

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMToolDefinition(BaseModel):
    """统一的工具定义结构，用于向 LLM 声明可用工具

    name: 工具名称
    description: 工具功能描述（供模型理解何时调用）
    parameters: JSON Schema 格式的参数定义
    """

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class LLMMessage(BaseModel):
    """统一的消息结构，对应对话历史中的一条消息

    role: 消息角色（system/user/assistant/tool）
    content: 消息内容，支持纯文本或多模态内容块列表（如文本+图片）
    tool_calls: 当该消息是 assistant 发起的工具调用时，携带的工具调用列表
    tool_call_id: 用于 tool 角色消息，标识该结果对应哪次工具调用
    """

    role: str
    content: str | list[dict] | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # 用于 tool 角色消息

    def to_dict(self) -> dict[str, Any]:
        """将消息序列化为字典，仅包含非空字段

        输入: 无（使用实例自身字段）
        逻辑: 依次判断 content/tool_calls/tool_call_id 是否有值，有值才写入结果字典，
              避免向下游 API 传递空字段
        返回: 可直接用于构造具体厂商请求体的字典
        """
        result = {"role": self.role}
        if self.content:
            result["content"] = self.content
        if self.tool_calls:
            result["tool_calls"] = [tc.model_dump() for tc in self.tool_calls]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result


class LLMResponse(BaseModel):
    """统一的 LLM 响应结构（非流式，或流式收集完成后的聚合结果）

    content: 正文内容
    reasoning_content: 推理/思维链内容（部分推理模型会单独返回）
    tool_calls: 本次响应触发的工具调用列表
    finish_reason: 结束原因，stop=正常结束，tool_calls=因工具调用而结束，length=因长度截断
    model: 实际使用的模型名称
    usage: token 用量统计（prompt_tokens/completion_tokens/total_tokens 等）
    """

    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"  # stop, tool_calls, length
    model: str = ""
    usage: dict[str, int] = Field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        """是否包含工具调用"""
        return len(self.tool_calls) > 0

    @property
    def has_content(self) -> bool:
        """是否包含非空正文内容"""
        return bool(self.content)


class StreamChunk(BaseModel):
    """流式输出块，stream_complete 逐块产出的最小单元

    type: 块类型，content=正文片段/reasoning=推理片段/tool_calls=工具调用（终止块）/
          done=正常结束（终止块）/error=出错（终止块）
    content: type=content 时的文本片段
    reasoning_content: type=reasoning 时的推理文本片段
    tool_calls: type=tool_calls 时携带的完整工具调用列表
    finish_reason: 结束原因（仅终止类型的块携带）
    error: type=error 时的错误信息
    """

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
        """获取当前使用的模型名称

        返回: 模型名称字符串
        """
        pass

    async def stream_collect(
        self,
        messages: list[LLMMessage],
        tools: list[LLMToolDefinition] | None = None,
        *,
        on_content: Callable[[str], Awaitable[None]] | None = None,
        on_reasoning: Callable[[str], Awaitable[None]] | None = None,
        max_empty_retries: int = 3,
        track_first_chunk_latency: bool = False,
    ) -> tuple[LLMResponse, float | None]:
        """
        流式调用并收集完整响应

        封装了流式收集和空响应重试逻辑，调用方只需关心结果。

        Args:
            messages: 消息列表
            tools: 工具定义列表
            on_content: 内容回调（用于实时推送）
            on_reasoning: 推理内容回调
            max_empty_retries: 空响应最大重试次数
            track_first_chunk_latency: 是否追踪首 chunk 延迟（秒）

        Returns:
            (LLMResponse, first_chunk_latency) 元组；
            first_chunk_latency 在 track_first_chunk_latency=False 时为 None。
        """
        # 是否需要记录首个 chunk 到达延迟（用于监控/日志），不需要时不启动计时
        call_started_at = time.perf_counter() if track_first_chunk_latency else 0.0
        first_chunk_latency: float | None = None
        first_chunk_received = False

        # 外层循环：处理"模型返回空响应"的情况，最多重试 max_empty_retries 次
        for attempt in range(max_empty_retries + 1):
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            tool_calls: list[LLMToolCall] = []
            finish_reason = "stop"

            stream = self.stream_complete(messages, tools)
            try:
                # 逐块消费流式输出，按 chunk.type 分派处理
                async for chunk in stream:
                    if chunk.type == "content" and chunk.content:
                        # 正文片段：拼接并可选地实时推送给调用方
                        content_parts.append(chunk.content)
                        if on_content:
                            await on_content(chunk.content)
                        if (
                            track_first_chunk_latency
                            and not first_chunk_received
                        ):
                            first_chunk_latency = time.perf_counter() - call_started_at
                            first_chunk_received = True
                    elif chunk.type == "reasoning" and chunk.reasoning_content:
                        # 推理/思维链片段：拼接并可选地实时推送
                        reasoning_parts.append(chunk.reasoning_content)
                        if on_reasoning:
                            await on_reasoning(chunk.reasoning_content)
                        if (
                            track_first_chunk_latency
                            and not first_chunk_received
                        ):
                            first_chunk_latency = time.perf_counter() - call_started_at
                            first_chunk_received = True
                    elif chunk.type == "tool_calls":
                        # 工具调用为终止块，直接拿到完整的工具调用列表，结束本轮流式读取
                        tool_calls = chunk.tool_calls
                        finish_reason = chunk.finish_reason or "tool_calls"
                        break
                    elif chunk.type == "done":
                        # 正常结束的终止块
                        finish_reason = chunk.finish_reason or "stop"
                        break
                    elif chunk.type == "error":
                        # 出错：若还有空响应重试机会则先跳出内层循环走外层重试，
                        # 否则直接把错误抛给调用方
                        if attempt < max_empty_retries:
                            break
                        raise RuntimeError(chunk.error or "LLM 流式调用失败")
            finally:
                # 显式关闭异步生成器，避免 break 后生成器未清理导致 StopIteration
                if hasattr(stream, "aclose"):
                    await stream.aclose()

            response = LLMResponse(
                content="".join(content_parts),
                reasoning_content="".join(reasoning_parts) or None,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                model=self.get_model_name(),
            )

            # 有内容或工具调用，直接返回
            if response.has_content or response.has_tool_calls:
                return response, first_chunk_latency

            # 空响应（既无正文也无工具调用）：还有重试次数则重新发起一轮流式调用
            if attempt < max_empty_retries:
                continue

        # 重试耗尽仍为空响应，把最后一次的空结果原样返回给调用方自行处理
        return response, first_chunk_latency
