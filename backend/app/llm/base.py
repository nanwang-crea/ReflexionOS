from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncIterator
from enum import Enum


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    role: str
    content: str
    
    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: Dict[str, int] = {}
    finish_reason: Optional[str] = None


class UniversalLLMInterface(ABC):
    """统一的 LLM 接口,所有 LLM 适配器必须实现此接口"""
    
    @abstractmethod
    async def complete(self, messages: List[Message]) -> LLMResponse:
        """
        同步补全接口
        
        Args:
            messages: 消息列表
            
        Returns:
            LLMResponse: LLM 响应结果
        """
        pass
    
    @abstractmethod
    async def stream_complete(self, messages: List[Message]) -> AsyncIterator[str]:
        """
        流式补全接口
        
        Args:
            messages: 消息列表
            
        Yields:
            str: 流式返回的文本片段
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """获取当前使用的模型名称"""
        pass
