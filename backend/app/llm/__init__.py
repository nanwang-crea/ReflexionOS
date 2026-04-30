import logging

from app.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    MessageRole,
    StreamChunk,
    UniversalLLMInterface,
)
from app.llm.openai_adapter import OpenAIAdapter
from app.models.llm_config import ProviderType, ResolvedLLMConfig

logger = logging.getLogger(__name__)


class LLMAdapterFactory:
    """LLM 适配器工厂"""

    @staticmethod
    def create(config: ResolvedLLMConfig, *, on_retry=None) -> UniversalLLMInterface:
        """
        根据配置创建 LLM 适配器

        Args:
            config: LLM 配置
            on_retry: 重试回调 (exception, attempt, delay) -> None

        Returns:
            UniversalLLMInterface: LLM 适配器实例

        Raises:
            ValueError: 不支持的 LLM 提供商
        """
        if config.provider_type == ProviderType.OPENAI_COMPATIBLE:
            logger.info("创建 OpenAI 适配器")
            return OpenAIAdapter(config, on_retry=on_retry)

        elif config.provider_type == ProviderType.ANTHROPIC:
            raise ValueError("Claude 适配器将在第二阶段实现")

        elif config.provider_type == ProviderType.OLLAMA:
            raise ValueError("Ollama 适配器将在第二阶段实现")

        else:
            raise ValueError(f"不支持的 LLM 提供商: {config.provider_type}")


__all__ = [
    "UniversalLLMInterface",
    "LLMMessage",
    "LLMResponse",
    "LLMToolCall",
    "LLMToolDefinition",
    "StreamChunk",
    "OpenAIAdapter",
    "LLMAdapterFactory",
    "MessageRole",
]
