import json
import logging
from typing import List, AsyncIterator, Dict, Any, Optional

from openai import AsyncOpenAI

from app.llm.base import (
    UniversalLLMInterface,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDefinition,
    StreamChunk
)
from app.models.llm_config import LLMConfig

logger = logging.getLogger(__name__)


class OpenAIAdapter(UniversalLLMInterface):
    """OpenAI API 适配器 - 支持原生工具调用和流式输出"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.model = config.model
        
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url if config.base_url else None
        )
        
        logger.info(f"OpenAI 适配器初始化完成, 模型: {self.model}")
    
    async def complete(
        self, 
        messages: List[LLMMessage],
        tools: List[LLMToolDefinition] = None
    ) -> LLMResponse:
        """
        同步补全（支持工具调用）
        
        Args:
            messages: 消息列表
            tools: 可用工具列表
            
        Returns:
            LLMResponse: 响应结果
        """
        try:
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
            
            response = await self.client.chat.completions.create(**kwargs)
            
            return self._parse_response(response)
            
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {str(e)}")
            raise
    
    async def stream_complete(
        self, 
        messages: List[LLMMessage],
        tools: List[LLMToolDefinition] = None
    ) -> AsyncIterator[StreamChunk]:
        """
        流式补全（支持工具调用）
        
        Args:
            messages: 消息列表
            tools: 可用工具列表
            
        Yields:
            StreamChunk: 流式输出块
        """
        try:
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
            
            stream = await self.client.chat.completions.create(**kwargs)
            
            # 收集 tool_calls（流式时需要聚合）
            current_tool_calls: Dict[int, Dict] = {}
            
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
            logger.error(f"OpenAI 流式 API 调用失败: {str(e)}")
            yield StreamChunk(type="error", error=str(e))
            raise
    
    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.model
    
    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """将内部消息格式转换为 OpenAI 格式"""
        openai_messages = []
        
        for msg in messages:
            openai_msg: Dict[str, Any] = {"role": msg.role}
            
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
    
    def _convert_tools(self, tools: List[LLMToolDefinition]) -> List[Dict[str, Any]]:
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
                    logger.warning(f"工具参数解析失败: {tc.function.arguments}")
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
                f"OpenAI 返回空响应, model={response.model}, finish_reason={choice.finish_reason}"
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
