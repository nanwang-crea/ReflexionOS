from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, AsyncIterator
from enum import Enum
import uuid


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMToolCall(BaseModel):
    """统一的工具调用结构"""
    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class LLMToolDefinition(BaseModel):
    """统一的工具定义结构"""
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class LLMMessage(BaseModel):
    """统一的消息结构"""
    role: str
    content: Optional[str] = None
    tool_calls: List[LLMToolCall] = Field(default_factory=list)
    tool_call_id: Optional[str] = None  # 用于 tool 角色消息
    
    def to_dict(self) -> Dict[str, Any]:
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
    content: Optional[str] = None
    tool_calls: List[LLMToolCall] = Field(default_factory=list)
    finish_reason: str = "stop"  # stop, tool_calls, length
    model: str = ""
    usage: Dict[str, int] = Field(default_factory=dict)
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
    
    @property
    def has_content(self) -> bool:
        return bool(self.content)


class StreamChunk(BaseModel):
    """流式输出块"""
    type: str  # content, tool_calls, done, error
    content: Optional[str] = None
    tool_calls: List[LLMToolCall] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    error: Optional[str] = None


class UniversalLLMInterface(ABC):
    """统一的 LLM 接口，所有 LLM 适配器必须实现此接口"""
    
    @abstractmethod
    async def complete(
        self, 
        messages: List[LLMMessage],
        tools: List[LLMToolDefinition] = None
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
        self, 
        messages: List[LLMMessage],
        tools: List[LLMToolDefinition] = None
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
