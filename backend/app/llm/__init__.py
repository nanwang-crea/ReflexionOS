from app.llm.base import (
    UniversalLLMInterface,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    StreamChunk,
    Message  # 兼容别名
)
from app.llm.openai_adapter import OpenAIAdapter
from app.models.llm_config import LLMConfig, LLMProvider
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class LLMAdapterFactory:
    """LLM 适配器工厂"""
    
    @staticmethod
    def create(config: LLMConfig) -> UniversalLLMInterface:
        """
        根据配置创建 LLM 适配器
        
        Args:
            config: LLM 配置
            
        Returns:
            UniversalLLMInterface: LLM 适配器实例
            
        Raises:
            ValueError: 不支持的 LLM 提供商
        """
        if config.provider == LLMProvider.OPENAI:
            logger.info("创建 OpenAI 适配器")
            return OpenAIAdapter(config)
        
        elif config.provider == LLMProvider.CLAUDE:
            raise ValueError("Claude 适配器将在第二阶段实现")
        
        elif config.provider == LLMProvider.OLLAMA:
            raise ValueError("Ollama 适配器将在第二阶段实现")
        
        else:
            raise ValueError(f"不支持的 LLM 提供商: {config.provider}")


__all__ = [
    "UniversalLLMInterface",
    "LLMMessage",
    "LLMResponse",
    "LLMToolCall",
    "LLMToolDefinition",
    "StreamChunk",
    "Message",
    "OpenAIAdapter",
    "LLMAdapterFactory",
]
