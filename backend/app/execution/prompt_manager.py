from __future__ import annotations

import logging
import os
import sys
import textwrap
from datetime import datetime
from enum import Enum
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.orchestration.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys._MEIPASS)
else:
    _BASE_DIR = Path(__file__).parent

PROMPTS_DIR = (
    _BASE_DIR / "app" / "execution" / "prompts"
    if getattr(sys, "frozen", False)
    else Path(__file__).parent / "prompts"
)


class PromptFamily(str, Enum):
    DEFAULT = "default"
    GLM = "glm"


def classify_prompt_family(model_name: str) -> PromptFamily:
    lower = (model_name or "").lower()
    if any(kw in lower for kw in ["glm-", "chatglm"]):
        return PromptFamily.GLM
    return PromptFamily.DEFAULT


class PromptTemplate:
    """Prompt 模板"""

    def __init__(self, name: str, template: str, variables: list[str]):
        self.name = name
        self.template = Template(template)
        self.variables = variables

    def render(self, **kwargs) -> str:
        """渲染模板"""
        return self.template.safe_substitute(**kwargs)


TEMPLATES_MANIFEST: list[dict] = [
    {
        "name": "system",
        "file": "system.txt",
        "variables": ["working_directory", "platform", "date", "is_git_repo"],
        "family_specific": True,
    },
    {
        "name": "coding_appendix",
        "file": "coding_appendix.txt",
        "variables": [],
        "family_specific": True,
    },
    {
        "name": "plan_mode",
        "file": "plan_mode.txt",
        "variables": ["working_directory", "platform", "date", "is_git_repo"],
        "family_specific": True,
    },
    {
        "name": "final_response",
        "file": "final_response.txt",
        "variables": ["task"],
        "family_specific": True,
    },
    {
        "name": "error",
        "file": "error.txt",
        "variables": [
            "tool",
            "error",
            "original_args_section",
            "available_actions_section",
        ],
        "family_specific": True,
    },
    {
        "name": "midrun_compress_system",
        "file": "midrun_compress_system.txt",
        "variables": [],
        "family_specific": True,
    },
    {
        "name": "midrun_compress_input",
        "file": "midrun_compress_input.txt",
        "variables": ["task", "transcript", "existing_summary_block"],
        "family_specific": True,
    },
]


def _read_prompt_file(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


class PromptManager:
    """Prompt 管理器 — 从 prompts/ 目录加载 .txt 模板文件，支持模型族子目录"""

    def __init__(self, model_name: str = "", skill_registry: SkillRegistry | None = None):
        self.templates: dict[str, PromptTemplate] = {}
        self.prompt_family = classify_prompt_family(model_name)
        self.skill_registry = skill_registry
        self._load_templates()

    def _resolve_file(self, entry: dict) -> str:
        filename = entry["file"]
        if entry.get("family_specific") and self.prompt_family != PromptFamily.DEFAULT:
            family_dir = self.prompt_family.value
            family_path = f"{family_dir}/{filename}"
            try:
                _read_prompt_file(family_path)
                return family_path
            except FileNotFoundError:
                logger.warning(
                    "Family-specific prompt %s not found, falling back to default",
                    family_path,
                )
        return filename

    def _load_templates(self) -> None:
        for entry in TEMPLATES_MANIFEST:
            resolved = self._resolve_file(entry)
            content = _read_prompt_file(resolved)
            self.register_template(
                name=entry["name"],
                template=content,
                variables=entry["variables"],
            )

    _DEFAULT_SOUL_MD = textwrap.dedent(
        """\
        ## Identity

        You are a pragmatic workspace agent collaborating with the user in the same project.

        ## Working Style

        - Be direct and evidence-based.
        - Prefer understanding the codebase before acting.
        - Do not pretend work is complete when it is not.

        ## Communication

        - Keep updates brief and useful.
        - Answer the real question once enough evidence exists.
        - Progress updates should inform, not turn obvious next actions into permission-seeking questions.

        ## Quality Taste

        - Prefer the smallest correct change.
        - Respect existing patterns unless they block the task.
    """
    )

    _DEFAULT_AGENT_MD = textwrap.dedent(
        """\
        ## Instruction Priority

        - Follow the user's explicit instructions first.
        - Then follow built-in safety and runtime protocol.
        - Then follow any active runtime mode rules.
        - Then follow project-level overlays.
        - Then follow global overlays.
        - Use the remaining system rules as defaults.

        ## Evidence First

        - If code, tests, or repository state can answer the question, inspect them first.
        - Being unsure is not a blocker. Investigate first.

        ## Skill And Mode Selection

        - Load a relevant skill before acting when one plausibly applies.
        - Treat code-editing work as coding mode and keep executing until complete or truly blocked.

        ## Clarification Gate

        - Default to action, not confirmation.
        - If the answer can be obtained by reading code, searching files, checking tests, or using available tools, do that first.
        - Only ask the user when the missing information can only come from user intent, business preference, credentials, approval, or unavailable external context.
        - When repo patterns make one option the obvious default, follow that default and state the assumption briefly instead of stopping to ask.

        ## Completion Rules

        - A progress report is not completion.
        - If work remains and no real blocker exists, continue.

        ## Stopping Rules

        - When a plan is active and has unfinished steps, continue executing until the plan is fully complete, unless the current step is blocked by information only the user can provide.
        - When a plan is active, update the plan before stopping.
        - Avoid repeated tool calls that do not produce new information.
        - After 2 failed attempts on the same action, explain the issue and ask the user instead of retrying indefinitely.
        - If the last tool batch produced no new facts, stop exploring and answer or ask for clarification.

        ## Error Handling

        - If a tool call fails, first diagnose WHY it failed before retrying.
        - Continue the current plan step after fixing the specific failure unless the failure proves the step is blocked.
        - Do not switch approaches solely because one tool call failed.
        - Do not make speculative large changes without evidence.
        - Do not blindly retry with the same parameters.

        ## Override Semantics

        - Project-level `.reflexion` rules override global defaults for this repository.
    """
    )

    def _read_optional_text(self, path: Path) -> str:
        try:
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Failed to read prompt overlay: %s", path, exc_info=True)
        return ""

    def _global_reflexion_dir(self) -> Path:
        """返回全局 Reflexion overlay 目录。

        函数名：_global_reflexion_dir
        入参：无
        功能：解析全局 `.reflexion` 目录，优先尊重测试和类 Unix 环境常用的 HOME。
        运行逻辑：
          1. Windows 的 Path.home() 优先 USERPROFILE，monkeypatch HOME 时不会生效。
          2. 这里显式读取 HOME，保证测试隔离和跨平台行为一致。
          3. HOME 未设置时退回 Path.home()，保持生产环境默认行为。
        出参：Path - 全局 `.reflexion` 目录路径
        """
        home = os.environ.get("HOME")
        if home:
            return Path(home) / ".reflexion"
        return Path.home() / ".reflexion"

    def _ensure_global_overlays(self) -> None:
        reflexion_dir = self._global_reflexion_dir()
        try:
            reflexion_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning(
                "Failed to create global .reflexion directory: %s", reflexion_dir
            )
            return

        soul_path = reflexion_dir / "soul.md"
        agent_path = reflexion_dir / "agent.md"

        if not soul_path.exists():
            try:
                soul_path.write_text(
                    self._DEFAULT_SOUL_MD.strip() + "\n", encoding="utf-8"
                )
                logger.info("Initialized global overlay: %s", soul_path)
            except OSError:
                logger.warning("Failed to create global soul.md: %s", soul_path)

        if not agent_path.exists():
            try:
                agent_path.write_text(
                    self._DEFAULT_AGENT_MD.strip() + "\n", encoding="utf-8"
                )
                logger.info("Initialized global overlay: %s", agent_path)
            except OSError:
                logger.warning("Failed to create global agent.md: %s", agent_path)

    def _overlay_paths(self, project_root: str | None) -> list[Path]:
        """返回 system prompt overlay 文件的加载路径列表（按优先级从低到高排列）。

        三个 overlay 文件的职责：
        - soul.md   — Agent 人格/性格（"你是谁"）：定义身份、沟通风格、价值观。
                       全局默认由 _ensure_global_overlays() 初始化，项目级可覆盖。
        - agent.md  — 行为规则（"你怎么做事"）：定义执行策略、停止条件、错误处理等。
                       全局默认由 _ensure_global_overlays() 初始化，项目级可覆盖。
        - memory.md — 跨会话记忆（"记住什么"）：用户偏好、项目约定、历史教训等。
                       无默认内容，由用户或 LLM（通过 edit 工具）手动写入。
                       全局级 ~/.reflexion/memory.md 适用于所有项目，
                       项目级 {project}/.reflexion/memory.md 适用于当前项目。

        加载顺序：全局 → 项目级，同层按 soul → agent → memory 排列。
        后加载的内容追加在 system prompt 末尾，等效于优先级更高。
        """
        self._ensure_global_overlays()
        global_reflexion_dir = self._global_reflexion_dir()
        paths = [
            # 全局 overlay（~/.reflexion/）
            global_reflexion_dir / "soul.md",
            global_reflexion_dir / "agent.md",
            global_reflexion_dir / "memory.md",
        ]
        if project_root:
            root = Path(project_root)
            paths.extend(
                [
                    # 项目级 overlay（{project}/.reflexion/），覆盖全局
                    root / ".reflexion" / "soul.md",
                    root / ".reflexion" / "agent.md",
                    root / ".reflexion" / "memory.md",
                ]
            )
        return paths

    @staticmethod
    def _join_sections(sections: list[str]) -> str:
        normalized = [
            section.strip() for section in sections if str(section or "").strip()
        ]
        return "\n\n".join(normalized)

    def register_template(self, name: str, template: str, variables: list[str]):
        """注册模板"""
        self.templates[name] = PromptTemplate(name, template, variables)

    def get_template(self, name: str) -> PromptTemplate:
        """获取模板"""
        if name not in self.templates:
            raise ValueError(f"Template not found: {name}")
        return self.templates[name]

    def get_system_prompt(
        self,
        *,
        working_directory: str = "",
        platform: str = "",
        is_git_repo: bool = False,
        project_root: str | None = None,
        coding_mode: bool = False,
    ) -> str:
        base_prompt = self.get_template("system").render(
            working_directory=working_directory,
            platform=platform,
            date=datetime.now().strftime("%Y-%m-%d"),
            is_git_repo=str(is_git_repo),
        )
        sections = [base_prompt]
        sections.extend(
            self._read_optional_text(path) for path in self._overlay_paths(project_root)
        )
        if coding_mode:
            sections.append(self.get_template("coding_appendix").render())

        # 注入 Skills 元数据（原 ContextAssembler.build_for_session 中的逻辑）
        skill_section = self._build_skill_section()
        if skill_section:
            sections.append(skill_section)

        return self._join_sections(sections)

    # ------------------------------------------------------------------
    # Skills 元数据注入
    # ------------------------------------------------------------------

    def _build_skill_section(self) -> str:
        """构建 Skills 元数据 section，注入到 system prompt 末尾。

        原 ContextAssembler 中的 Skills 注入逻辑迁移至此，
        由 PromptManager 统一管理所有静态上下文。
        AGENTS.md 已废弃，统一使用 agent.md overlay 机制。
        """
        if not self.skill_registry:
            return ""

        enabled_skills = self.skill_registry.list_enabled_skills()
        if not enabled_skills:
            return ""

        parts = ["""## Available Skills

When a skill clearly matches your current task, load it first using the 'skill' tool with action='load'.

### Skill usage guidelines:
1. Before starting a task, briefly consider whether an available skill matches.
2. If a skill matches, use the 'skill' tool with action='load' to read its full content.
3. Follow the loaded skill's instructions — skills provide proven workflows for complex tasks.
4. Process skills (debugging, TDD, brainstorming) help you approach a task correctly — check them when relevant.
5. Implementation skills guide execution — use them after process skills when applicable.
6. A skill's hard gates and checklists are important safeguards — respect them.

### Available skills:"""]
        for s in enabled_skills:
            req_str = ", ".join(s.required_skills)
            req = f" (requires: {req_str})" if s.required_skills else ""
            parts.append(f"- **{s.name}**: {s.description}{req}")
        return "\n".join(parts)

    def get_plan_mode_prompt(
        self,
        *,
        working_directory: str = "",
        platform: str = "",
        is_git_repo: bool = False,
    ) -> str:
        return self.get_template("plan_mode").render(
            working_directory=working_directory,
            platform=platform,
            date=datetime.now().strftime("%Y-%m-%d"),
            is_git_repo=str(is_git_repo),
        )

    def get_error_prompt(
        self,
        error: str,
        tool: str,
        original_args: dict | None = None,
        available_actions: list[str] | None = None,
    ) -> str:
        if original_args:
            args_lines = [
                f"  - {k}: {v!r}" for k, v in original_args.items() if v is not None
            ]
            original_args_section = (
                "- Arguments you used:\n" + "\n".join(args_lines) if args_lines else ""
            )
        else:
            original_args_section = ""

        if available_actions:
            available_actions_section = (
                f"- Available actions for {tool}: {', '.join(available_actions)}"
            )
        else:
            available_actions_section = ""

        return self.get_template("error").render(
            tool=tool,
            error=error,
            original_args_section=original_args_section,
            available_actions_section=available_actions_section,
        )

    def get_final_response_prompt(self, task: str) -> str:
        return self.get_template("final_response").render(task=task)

    def get_midrun_compression_system_prompt(self) -> str:
        return self.get_template("midrun_compress_system").render()

    def get_midrun_compression_prompt(
        self,
        *,
        task: str,
        transcript: str,
        existing_summary: str | None = None,
    ) -> str:
        if existing_summary:
            existing_summary_block = (
                f"[Existing summary]\n{existing_summary}\n\n[New conversation]"
            )
        else:
            existing_summary_block = ""
        return self.get_template("midrun_compress_input").render(
            task=task or "",
            transcript=transcript or "",
            existing_summary_block=existing_summary_block,
        )


