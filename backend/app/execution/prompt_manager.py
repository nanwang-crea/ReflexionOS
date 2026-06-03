import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from string import Template

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class PromptFamily(str, Enum):
    DEFAULT = "default"
    CN_COMPATIBLE = "cn_compatible"


def classify_prompt_family(model_name: str) -> PromptFamily:
    lower = (model_name or "").lower()
    cn_keywords = ["qwen", "deepseek", "glm-", "chatglm", "yi-", "baichuan", "minimax", "moonshot", "kimi"]
    if any(kw in lower for kw in cn_keywords):
        return PromptFamily.CN_COMPATIBLE
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
        "file": "system_{family}.txt",
        "variables": ["working_directory", "platform", "date", "is_git_repo"],
    },
    {
        "name": "plan_mode",
        "file": "plan_mode.txt",
        "variables": ["working_directory", "platform", "date", "is_git_repo"],
    },
    {
        "name": "initial_plan",
        "file": "initial_plan.txt",
        "variables": [],
    },
    {
        "name": "final_response",
        "file": "final_response.txt",
        "variables": ["task"],
    },
    {
        "name": "error",
        "file": "error.txt",
        "variables": ["tool", "error", "original_args_section", "available_actions_section"],
    },
    {
        "name": "continuation_compress_system",
        "file": "continuation_compress_system.txt",
        "variables": [],
    },
    {
        "name": "continuation_compress_input",
        "file": "continuation_compress_input.txt",
        "variables": ["task", "transcript"],
    },
    {
        "name": "midrun_compress_system",
        "file": "midrun_compress_system.txt",
        "variables": [],
    },
    {
        "name": "midrun_compress_input",
        "file": "midrun_compress_input.txt",
        "variables": ["task", "transcript", "existing_summary_block"],
    },
]


def _read_prompt_file(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


class PromptManager:
    """Prompt 管理器 — 从 prompts/ 目录加载 .txt 模板文件"""

    def __init__(self, model_name: str = ""):
        self.templates: dict[str, PromptTemplate] = {}
        self.prompt_family = classify_prompt_family(model_name)
        self._load_templates()

    def _load_templates(self) -> None:
        family_value = self.prompt_family.value
        for entry in TEMPLATES_MANIFEST:
            filename = entry["file"].format(family=family_value)
            try:
                content = _read_prompt_file(filename)
            except FileNotFoundError:
                if "{family}" in entry["file"]:
                    fallback = entry["file"].format(family="default")
                    logger.warning(
                        "Prompt file %s not found, falling back to %s",
                        filename, fallback,
                    )
                    content = _read_prompt_file(fallback)
                else:
                    raise
            self.register_template(
                name=entry["name"],
                template=content,
                variables=entry["variables"],
            )

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
    ) -> str:
        return self.get_template("system").render(
            working_directory=working_directory,
            platform=platform,
            date=datetime.now().strftime("%Y-%m-%d"),
            is_git_repo=str(is_git_repo),
        )

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
            args_lines = [f"  - {k}: {v!r}" for k, v in original_args.items() if v is not None]
            original_args_section = "- Arguments you used:\n" + "\n".join(args_lines) if args_lines else ""
        else:
            original_args_section = ""

        if available_actions:
            available_actions_section = f"- Available actions for {tool}: {', '.join(available_actions)}"
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

    def get_initial_plan_prompt(self) -> str:
        return self.get_template("initial_plan").render()

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
            existing_summary_block = f"[Existing summary]\n{existing_summary}\n\n[New conversation]"
        else:
            existing_summary_block = ""
        return self.get_template("midrun_compress_input").render(
            task=task or "",
            transcript=transcript or "",
            existing_summary_block=existing_summary_block,
        )

    def get_continuation_compression_prompt(self, *, task: str, transcript: str) -> str:
        return self.get_template("continuation_compress_input").render(
            task=task or "",
            transcript=transcript or "",
        )

    def get_continuation_compression_system_prompt(self) -> str:
        return self.get_template("continuation_compress_system").render()
