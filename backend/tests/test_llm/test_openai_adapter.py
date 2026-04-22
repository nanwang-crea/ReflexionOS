from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.base import LLMMessage
from app.llm.openai_adapter import OpenAIAdapter
from app.models.llm_config import ProviderType, ResolvedLLMConfig


class TestOpenAIAdapter:
    
    @pytest.fixture
    def llm_config(self):
        return ResolvedLLMConfig(
            provider_id="provider-openai",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            model_id="model-gpt4",
            model="gpt-4-turbo-preview",
            api_key="test-api-key",
            temperature=0.7,
            max_tokens=1000
        )
    
    @pytest.fixture
    def openai_adapter(self, llm_config):
        return OpenAIAdapter(llm_config)
    
    def test_adapter_initialization(self, openai_adapter, llm_config):
        assert openai_adapter.config == llm_config
        assert openai_adapter.model == "gpt-4-turbo-preview"
    
    def test_get_model_name(self, openai_adapter):
        assert openai_adapter.get_model_name() == "gpt-4-turbo-preview"
    
    @pytest.mark.asyncio
    async def test_complete_success(self, openai_adapter):
        messages = [
            LLMMessage(role="user", content="Hello")
        ]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi there!"
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 30
        mock_response.choices[0].finish_reason = "stop"
        
        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_response
            
            response = await openai_adapter.complete(messages)
            
            assert response.content == "Hi there!"
            assert response.model == "gpt-4-turbo-preview"
            assert response.usage["total_tokens"] == 50

    @pytest.mark.asyncio
    async def test_complete_with_none_content_returns_empty_string(self, openai_adapter):
        messages = [
            LLMMessage(role="user", content="Hello")
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 30
        mock_response.choices[0].finish_reason = "stop"

        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_response

            response = await openai_adapter.complete(messages)

            assert response.content == ""
            assert response.model == "gpt-4-turbo-preview"
            assert response.usage["total_tokens"] == 50

    @pytest.mark.asyncio
    async def test_stream_complete_updates_late_tool_call_id(self, openai_adapter):
        messages = [LLMMessage(role="user", content="Inspect README")]

        async def mock_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id=None,
                                function=SimpleNamespace(
                                    name="mock_tool",
                                    arguments='{"path":"README'
                                )
                            )
                        ]
                    ),
                    finish_reason=None
                )]
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="fc_test_call_id",
                                function=SimpleNamespace(
                                    name=None,
                                    arguments='.md"}'
                                )
                            )
                        ]
                    ),
                    finish_reason="tool_calls"
                )]
            )

        with patch.object(
            openai_adapter.client.chat.completions,
            'create',
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_stream()

            chunks = []
            async for chunk in openai_adapter.stream_complete(messages, tools=[]):
                chunks.append(chunk)

        tool_call_chunk = next(chunk for chunk in chunks if chunk.type == "tool_calls")
        assert tool_call_chunk.tool_calls[0].id == "fc_test_call_id"
        assert tool_call_chunk.tool_calls[0].name == "mock_tool"
        assert tool_call_chunk.tool_calls[0].arguments == {"path": "README.md"}
