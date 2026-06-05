import pytest

from app.execution.prompt_manager import PromptFamily, PromptManager, classify_prompt_family


class TestPromptManager:
    @pytest.fixture
    def manager(self):
        return PromptManager()

    def test_get_system_prompt(self, manager):
        prompt = manager.get_system_prompt(
            working_directory="/project",
            platform="darwin",
            is_git_repo=True,
        )

        assert "autonomous coding agent" in prompt
        assert "Tool and shell rules" in prompt
        assert "/project" in prompt
        assert "darwin" in prompt
        assert "True" in prompt
        assert "Execution plan" in prompt
        assert "Plan overrides stopping" in prompt

    def test_get_error_prompt(self, manager):
        prompt = manager.get_error_prompt(
            error="File not found", tool="file"
        )

        assert "File not found" in prompt
        assert "file" in prompt
        assert "How to fix" in prompt

    def test_register_custom_template(self, manager):
        manager.register_template(name="custom", template="Custom: $content", variables=["content"])

        template = manager.get_template("custom")
        result = template.render(content="test")

        assert result == "Custom: test"

    def test_get_template_not_found(self, manager):
        with pytest.raises(ValueError) as exc_info:
            manager.get_template("nonexistent")

        assert "Template not found" in str(exc_info.value)


class TestEnhancedErrorPrompt:
    @pytest.fixture
    def manager(self):
        return PromptManager()

    def test_error_prompt_includes_structured_guidance(self, manager):
        prompt = manager.get_error_prompt(
            error="Unknown action: load",
            tool="file",
        )
        assert "Unknown action: load" in prompt
        assert "How to fix" in prompt

    def test_error_prompt_includes_original_arguments(self, manager):
        prompt = manager.get_error_prompt(
            error="Missing required parameter: path",
            tool="file",
            original_args={"action": "read", "name": "some_file"},
        )
        assert "action" in prompt
        assert "read" in prompt
        assert "name" in prompt
        assert "path" in prompt

    def test_error_prompt_includes_available_actions(self, manager):
        prompt = manager.get_error_prompt(
            error="Unknown action: load",
            tool="file",
            available_actions=["read", "search", "list"],
        )
        assert "read" in prompt
        assert "search" in prompt
        assert "list" in prompt
        assert "Available actions for file" in prompt

    def test_error_prompt_without_optional_fields(self, manager):
        prompt = manager.get_error_prompt(
            error="File not found",
            tool="file",
        )
        assert "File not found" in prompt
        assert "How to fix" in prompt


class TestClassifyPromptFamily:
    def test_default_for_gpt(self):
        assert classify_prompt_family("gpt-4o") == PromptFamily.DEFAULT

    def test_default_for_claude(self):
        assert classify_prompt_family("claude-3-opus") == PromptFamily.DEFAULT

    def test_default_for_empty(self):
        assert classify_prompt_family("") == PromptFamily.DEFAULT

    def test_default_for_none(self):
        assert classify_prompt_family(None) == PromptFamily.DEFAULT

    def test_default_for_qwen(self):
        assert classify_prompt_family("qwen-plus") == PromptFamily.DEFAULT

    def test_default_for_deepseek(self):
        assert classify_prompt_family("deepseek-chat") == PromptFamily.DEFAULT

    def test_glm_for_glm(self):
        assert classify_prompt_family("glm-4-plus") == PromptFamily.GLM

    def test_glm_for_chatglm(self):
        assert classify_prompt_family("chatglm3-turbo") == PromptFamily.GLM

    def test_case_insensitive(self):
        assert classify_prompt_family("GLM-4-Plus") == PromptFamily.GLM
        assert classify_prompt_family("ChatGLM3") == PromptFamily.GLM

    def test_non_glm_chinese_models_use_default(self):
        assert classify_prompt_family("qwen-max") == PromptFamily.DEFAULT
        assert classify_prompt_family("deepseek-v3") == PromptFamily.DEFAULT
        assert classify_prompt_family("yi-large") == PromptFamily.DEFAULT


class TestPromptFamilySelection:
    def test_default_family_uses_english_prompts(self):
        manager = PromptManager(model_name="gpt-4o")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
        assert "You MUST continue using tools until the task is fully complete" in prompt

    def test_glm_family_uses_chinese_prompts(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "自主编程智能体" in prompt
        assert "你必须持续使用工具直到任务完全完成" in prompt

    def test_glm_family_error_prompt_in_chinese(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_error_prompt(error="参数错误", tool="file")
        assert "工具调用失败" in prompt
        assert "参数错误" in prompt

    def test_glm_family_final_response_in_chinese(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_final_response_prompt(task="测试任务")
        assert "最终答案" in prompt

    def test_non_glm_chinese_models_fall_back_to_default(self):
        manager = PromptManager(model_name="qwen-plus")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
