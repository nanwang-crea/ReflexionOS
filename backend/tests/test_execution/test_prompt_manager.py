import pytest
from app.execution.prompt_manager import PromptManager


class TestPromptManager:
    
    @pytest.fixture
    def manager(self):
        return PromptManager()
    
    def test_get_system_prompt(self, manager):
        prompt = manager.get_system_prompt(tools=[])
        
        assert "autonomous coding agent" in prompt
        assert "JSON" in prompt
        assert "content" in prompt
        assert "tool_calls" in prompt
    
    def test_get_error_prompt(self, manager):
        prompt = manager.get_error_prompt(
            error="File not found",
            tool="file",
            code_snippet="def test(): pass"
        )
        
        assert "File not found" in prompt
        assert "file" in prompt
    
    def test_register_custom_template(self, manager):
        manager.register_template(
            name="custom",
            template="Custom: $content",
            variables=["content"]
        )
        
        template = manager.get_template("custom")
        result = template.render(content="test")
        
        assert result == "Custom: test"
    
    def test_get_template_not_found(self, manager):
        with pytest.raises(ValueError) as exc_info:
            manager.get_template("nonexistent")
        
        assert "Template not found" in str(exc_info.value)
