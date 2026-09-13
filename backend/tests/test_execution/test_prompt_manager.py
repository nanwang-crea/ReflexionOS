from pathlib import Path

import pytest

from app.execution.prompt_manager import (
    PromptFamily,
    PromptManager,
    classify_prompt_family,
)


PROMPTS_DIR = Path(__file__).parents[2] / "app" / "execution" / "prompts"


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

        assert "自主编程智能体" not in prompt
        assert "同一个项目中协作" in prompt
        assert "工具和 shell 规则" in prompt
        assert "/project" in prompt
        assert "darwin" in prompt
        assert "True" in prompt
        assert "计划契约" in prompt
        assert "任务规划" in prompt

    def test_get_system_prompt_merges_global_and_project_overlays(
        self, tmp_path, monkeypatch
    ):
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        (home / ".reflexion").mkdir(parents=True)
        (home / ".reflexion" / "soul.md").write_text(
            "## Identity\nGlobal soul", encoding="utf-8"
        )
        (home / ".reflexion" / "agent.md").write_text(
            "## Evidence First\nGlobal agent", encoding="utf-8"
        )

        project_root = tmp_path / "project"
        (project_root / ".reflexion").mkdir(parents=True)
        (project_root / ".reflexion" / "soul.md").write_text(
            "## Identity\nProject soul", encoding="utf-8"
        )
        (project_root / ".reflexion" / "agent.md").write_text(
            "## Completion Rules\nProject agent", encoding="utf-8"
        )

        manager = PromptManager(model_name="gpt-4o")
        prompt = manager.get_system_prompt(
            working_directory=str(project_root),
            platform="darwin",
            is_git_repo=False,
            project_root=str(project_root),
        )

        assert "Global soul" in prompt
        assert "Global agent" in prompt
        assert "Project soul" in prompt
        assert "Project agent" in prompt
        assert prompt.index("Global soul") < prompt.index("Project soul")

    def test_get_system_prompt_skips_missing_overlay_files(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        project_root = tmp_path / "project"
        project_root.mkdir()

        manager = PromptManager(model_name="gpt-4o")
        prompt = manager.get_system_prompt(
            working_directory=str(project_root),
            platform="darwin",
            is_git_repo=False,
            project_root=str(project_root),
        )

        assert "工作目录" in prompt

    def test_get_system_prompt_appends_coding_mode_rules(self):
        manager = PromptManager(model_name="gpt-4o")

        prompt = manager.get_system_prompt(
            working_directory="/project",
            platform="darwin",
            is_git_repo=True,
            coding_mode=True,
        )

        assert "编码模式停止规则" in prompt
        assert "状态汇报不是完成" in prompt
        assert "未验证的工作仍然不算完成" in prompt
        assert (
            "你必须持续使用工具直到任务完全完成" in prompt
        )

    def test_coding_appendix_prompt_assets_define_coding_mode_rules(self):
        default_appendix = PROMPTS_DIR / "coding_appendix.md"

        assert default_appendix.exists()

        assert "编码模式停止规则" in default_appendix.read_text(
            encoding="utf-8"
        )
        assert "状态汇报不是完成" in default_appendix.read_text(
            encoding="utf-8"
        )
        assert "未验证的工作仍然不算完成" in default_appendix.read_text(encoding="utf-8")

    def test_plan_mode_prompt_emphasizes_observable_evidence(self, manager):
        prompt = manager.get_plan_mode_prompt(
            working_directory="/project",
            platform="darwin",
            is_git_repo=True,
        )

        assert "澄清门" in prompt
        assert "先穷尽可观察证据，再向用户提问" in prompt
        assert "优先控制在 3-6 个步骤" in prompt


    def test_final_response_prompt_requires_no_unfinished_plan_steps(self, manager):
        prompt = manager.get_final_response_prompt(task="修复提示词栈")

        assert "修复提示词栈" in prompt
        assert (
            "如果当前计划还有未完成步骤，不要输出最终答案"
            in prompt
        )

    def test_final_response_prompt_warns_against_unverified_coding_completion(
        self, manager
    ):
        prompt = manager.get_final_response_prompt(task="实现功能 X")

        assert "验证" in prompt
        assert "不要声称工作已完成" in prompt
        assert "继续执行" in prompt

    def test_get_error_prompt(self, manager):
        prompt = manager.get_error_prompt(error="File not found", tool="file")

        assert "File not found" in prompt
        assert "file" in prompt
        assert "修复方法" in prompt

    def test_register_custom_template(self, manager):
        manager.register_template(
            name="custom", template="Custom: $content", variables=["content"]
        )

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
        assert "修复方法" in prompt
        assert "继续当前计划步骤" in prompt

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
        assert "修复方法" in prompt


class TestApprovalRejectedPrompt:
    @pytest.fixture
    def manager(self):
        return PromptManager()

    def test_includes_tool_and_reason(self, manager):
        prompt = manager.get_approval_rejected_prompt(
            tool="shell",
            reason="用户认为风险过高",
        )
        assert "shell" in prompt
        assert "用户认为风险过高" in prompt
        assert "绝不要用相同参数重试" in prompt
        assert "如何继续" in prompt

    def test_includes_original_args(self, manager):
        prompt = manager.get_approval_rejected_prompt(
            tool="shell",
            original_args={"command": "rm -rf build/", "cwd": "/project"},
            reason="破坏性操作",
        )
        assert "shell" in prompt
        assert "rm -rf build/" in prompt
        assert "/project" in prompt
        assert "破坏性操作" in prompt

    def test_without_optional_fields(self, manager):
        prompt = manager.get_approval_rejected_prompt(tool="shell")
        assert "shell" in prompt
        assert "绝不要用相同参数重试" in prompt
        # reason 缺省时不应出现裸 None
        assert "None" not in prompt

    def test_risk_level_section_optional(self, manager):
        prompt = manager.get_approval_rejected_prompt(
            tool="shell",
            reason="破坏性操作",
            risk_level="Level 6 (需审批)",
        )
        assert "Level 6" in prompt
        # 不传 risk_level 时不该出现 风险分级 行
        prompt_without = manager.get_approval_rejected_prompt(
            tool="shell", reason="x"
        )
        assert "风险分级" not in prompt_without


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
    def test_default_family_uses_chinese_prompts(self, tmp_path, monkeypatch):
        # 隔离 HOME，避免读到本机已存在的 ~/.reflexion overlay
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        manager = PromptManager(model_name="gpt-4o")
        prompt = manager.get_system_prompt(
            working_directory="/p", platform="darwin", is_git_repo=True
        )
        assert "自主编程智能体" not in prompt
        assert "同一个项目中协作" in prompt
        assert "指令优先级" in prompt

    def test_glm_family_uses_chinese_prompts(self, tmp_path, monkeypatch):
        # 所有模型族（含 GLM）现在都走统一的中文默认版；隔离 HOME 避免本机 overlay 干扰
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        # 首次构造时会把 _DEFAULT_SOUL_MD / _DEFAULT_AGENT_MD 写入 home/.reflexion
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_system_prompt(
            working_directory="/p", platform="darwin", is_git_repo=True
        )
        assert "协作" in prompt
        assert "自主编程智能体" not in prompt
        assert "计划契约" in prompt
        assert "澄清门" in prompt
        assert "指令优先级" in prompt

    def test_glm_coding_mode_prompt_adds_chinese_appendix(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_system_prompt(
            working_directory="/p",
            platform="darwin",
            is_git_repo=True,
            coding_mode=True,
        )

        assert "状态汇报不是完成" in prompt
        assert "未验证的工作仍然不算完成" in prompt
        assert "你必须持续使用工具直到任务完全完成" in prompt

    def test_glm_family_error_prompt_in_chinese(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_error_prompt(error="参数错误", tool="file")
        assert "工具调用失败" in prompt
        assert "参数错误" in prompt
        assert "继续当前计划步骤" in prompt

    def test_glm_family_final_response_in_chinese(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_final_response_prompt(task="测试任务")
        assert "最终答案" in prompt
        assert "如果当前计划还有未完成步骤，不要输出最终答案" in prompt

    def test_glm_family_plan_mode_prompt_matches_runtime_protocol(self):
        manager = PromptManager(model_name="glm-4-plus")
        prompt = manager.get_plan_mode_prompt(
            working_directory="/p", platform="darwin", is_git_repo=True
        )

        assert "澄清门" in prompt
        assert "先穷尽可观察证据，再向用户提问" in prompt

    def test_non_glm_chinese_models_use_chinese_prompts(self):
        # 国产非 GLM 模型（DeepSeek/Qwen 等）也走统一中文默认版
        manager = PromptManager(model_name="qwen-plus")
        prompt = manager.get_system_prompt(
            working_directory="/p", platform="darwin", is_git_repo=True
        )
        assert "自主编程智能体" not in prompt
        assert "同一个项目中协作" in prompt

        deepseek_manager = PromptManager(model_name="deepseek-chat")
        deepseek_prompt = deepseek_manager.get_system_prompt(
            working_directory="/p", platform="darwin", is_git_repo=True
        )
        assert "同一个项目中协作" in deepseek_prompt


def test_project_reflexion_overlay_content_is_included(tmp_path):
    project_root = tmp_path / "project"
    (project_root / ".reflexion").mkdir(parents=True)
    (project_root / ".reflexion" / "soul.md").write_text(
        "## Identity\nProject overlay identity", encoding="utf-8"
    )
    (project_root / ".reflexion" / "agent.md").write_text(
        "## Completion Rules\nProject overlay rules", encoding="utf-8"
    )

    manager = PromptManager(model_name="gpt-4o")
    prompt = manager.get_system_prompt(
        working_directory=str(project_root),
        platform="darwin",
        is_git_repo=False,
        project_root=str(project_root),
    )

    assert "Project overlay identity" in prompt
    assert "Project overlay rules" in prompt
