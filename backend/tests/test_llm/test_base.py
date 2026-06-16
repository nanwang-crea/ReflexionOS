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

    def test_message_multimodal(self):
        """测试多模态消息"""
        message = LLMMessage(
            role="user",
            content=[
                {"type": "text", "text": "分析这张图片"},
                {"type": "image_url", "url": "data:image/png;base64,abc123"},
            ]
        )
        assert isinstance(message.content, list)
        assert len(message.content) == 2
        assert message.content[0]["type"] == "text"
        assert message.content[1]["type"] == "image_url"

    def test_message_multimodal_to_dict(self):
        """测试多模态消息的 to_dict 方法"""
        message = LLMMessage(
            role="user",
            content=[
                {"type": "text", "text": "Hello"},
                {"type": "image_url", "url": "data:image/png;base64,abc"},
            ]
        )
        msg_dict = message.to_dict()

        assert msg_dict["role"] == "user"
        assert isinstance(msg_dict["content"], list)
        assert len(msg_dict["content"]) == 2
        assert msg_dict["content"][0] == {"type": "text", "text": "Hello"}
        assert msg_dict["content"][1] == {
            "type": "image_url",
            "url": "data:image/png;base64,abc"
        }


class TestLLMResponse:
    def test_llm_response(self):
        response = LLMResponse(content="Response text", model="gpt-4", usage={"total_tokens": 100})

        assert response.content == "Response text"
        assert response.model == "gpt-4"
        assert response.usage["total_tokens"] == 100
