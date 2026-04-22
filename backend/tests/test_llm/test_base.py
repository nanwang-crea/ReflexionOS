from app.llm.base import LLMMessage, LLMResponse


class TestLLMMessage:
    
    def test_message_creation(self):
        message = LLMMessage(role="user", content="Hello")
        
        assert message.role == "user"
        assert message.content == "Hello"
    
    def test_message_to_dict(self):
        message = LLMMessage(role="user", content="Hello")
        msg_dict = message.to_dict()
        
        assert msg_dict == {"role": "user", "content": "Hello"}


class TestLLMResponse:
    
    def test_llm_response(self):
        response = LLMResponse(
            content="Response text",
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        assert response.content == "Response text"
        assert response.model == "gpt-4"
        assert response.usage["total_tokens"] == 100
