import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.llm.openai_adapter import OpenAIAdapter
from app.llm.base import Message
from app.models.llm_config import LLMConfig, LLMProvider


class TestOpenAIAdapter:
    
    @pytest.fixture
    def llm_config(self):
        return LLMConfig(
            provider=LLMProvider.OPENAI,
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
            Message(role="user", content="Hello")
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
        
        with patch.object(openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            
            response = await openai_adapter.complete(messages)
            
            assert response.content == "Hi there!"
            assert response.model == "gpt-4-turbo-preview"
            assert response.usage["total_tokens"] == 50

    @pytest.mark.asyncio
    async def test_complete_with_none_content_returns_empty_string(self, openai_adapter):
        messages = [
            Message(role="user", content="Hello")
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

        with patch.object(openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            response = await openai_adapter.complete(messages)

            assert response.content == ""
            assert response.model == "gpt-4-turbo-preview"
            assert response.usage["total_tokens"] == 50
