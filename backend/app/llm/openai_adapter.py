from typing import List, AsyncIterator
from openai import AsyncOpenAI
from app.llm.base import UniversalLLMInterface, Message, LLMResponse
from app.models.llm_config import LLMConfig
import logging

logger = logging.getLogger(__name__)


class OpenAIAdapter(UniversalLLMInterface):
    """OpenAI API 适配器"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.model = config.model
        
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url if config.base_url else None
        )
        
        logger.info(f"OpenAI 适配器初始化完成,模型: {self.model}")
    
    async def complete(self, messages: List[Message]) -> LLMResponse:
        """
        同步补全
        
        Args:
            messages: 消息列表
            
        Returns:
            LLMResponse: 响应结果
        """
        try:
            message_dicts = [msg.to_dict() for msg in messages]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=message_dicts,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )

            choice = response.choices[0]
            content = choice.message.content or ""

            if choice.message.content is None:
                logger.warning(
                    "OpenAI 返回了空文本内容, model=%s, finish_reason=%s",
                    response.model,
                    choice.finish_reason
                )
            
            return LLMResponse(
                content=content,
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                finish_reason=choice.finish_reason
            )
            
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {str(e)}")
            raise
    
    async def stream_complete(self, messages: List[Message]) -> AsyncIterator[str]:
        """
        流式补全
        
        Args:
            messages: 消息列表
            
        Yields:
            str: 文本片段
        """
        try:
            message_dicts = [msg.to_dict() for msg in messages]
            
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=message_dicts,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"OpenAI 流式 API 调用失败: {str(e)}")
            raise
    
    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.model
