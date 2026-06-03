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
        assert "Never restart investigation from scratch unless a concrete prior finding was disproven." in prompt

    def test_get_error_prompt(self, manager):
        prompt = manager.get_error_prompt(
            error="File not found", tool="file", code_snippet="def test(): pass"
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
            code_snippet="",
        )
        assert "Unknown action: load" in prompt
        assert "How to fix" in prompt

    def test_error_prompt_includes_original_arguments(self, manager):
        prompt = manager.get_error_prompt(
            error="Missing required parameter: path",
            tool="file",
            code_snippet="",
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
            code_snippet="",
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

    def test_cn_compatible_for_qwen(self):
        assert classify_prompt_family("qwen-plus") == PromptFamily.CN_COMPATIBLE

    def test_cn_compatible_for_deepseek(self):
        assert classify_prompt_family("deepseek-chat") == PromptFamily.CN_COMPATIBLE

    def test_cn_compatible_for_glm(self):
        assert classify_prompt_family("glm-4-plus") == PromptFamily.CN_COMPATIBLE

    def test_cn_compatible_for_chatglm(self):
        assert classify_prompt_family("chatglm3-turbo") == PromptFamily.CN_COMPATIBLE

    def test_cn_compatible_for_yi(self):
        assert classify_prompt_family("yi-34b-chat") == PromptFamily.CN_COMPATIBLE

    def test_cn_compatible_for_baichuan(self):
        assert classify_prompt_family("baichuan2-7b") == PromptFamily.CN_COMPATIBLE

    def test_cn_compatible_for_minimax(self):
        assert classify_prompt_family("minimax-abab5") == PromptFamily.CN_COMPATIBLE

    def test_cn_compatible_for_moonshot(self):
        assert classify_prompt_family("moonshot-v1") == PromptFamily.CN_COMPATIBLE

    def test_cn_compatible_for_kimi(self):
        assert classify_prompt_family("kimi-latest") == PromptFamily.CN_COMPATIBLE

    def test_case_insensitive(self):
        assert classify_prompt_family("Qwen-Plus") == PromptFamily.CN_COMPATIBLE
        assert classify_prompt_family("DeepSeek-V2") == PromptFamily.CN_COMPATIBLE


class TestPromptFamilySelection:
    def test_default_family_for_unknown_model(self):
        manager = PromptManager(model_name="gpt-4o")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
        assert "You MUST continue using tools until the task is fully complete" in prompt

    def test_cn_compatible_family_for_qwen(self):
        manager = PromptManager(model_name="qwen-plus")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
        assert "你必须持续使用工具" in prompt or "You MUST continue" in prompt

    def test_cn_compatible_family_for_deepseek(self):
        manager = PromptManager(model_name="deepseek-chat")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
        assert "仔细阅读错误信息" in prompt

    def test_cn_compatible_family_for_glm(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_system_prompt(working_directory="/p", platform="darwin", is_git_repo=True)
        assert "autonomous coding agent" in prompt
        assert "只使用工具 schema 中定义的参数名" in prompt
