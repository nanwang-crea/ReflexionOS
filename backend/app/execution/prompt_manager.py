"""
文件功能：Prompt 模板的加载、组装与渲染管理
文件描述：从 prompts/ 目录读取 .md 模板文件（system/plan_mode/error/final_response/
         midrun_compress 等），模板统一使用中文，适配 GLM/DeepSeek/Qwen 等中文模型；
         同时负责组装最终 system prompt——拼接基础模板、全局与项目级的人格/行为/记忆 overlay
         （soul.md / agent.md / memory.md）、编码模式附录、以及可用 Skills 元数据。
核心逻辑：模板清单（TEMPLATES_MANIFEST）声明式描述每个模板文件名和所需变量，加载时
         若模板标记为 family_specific 且当前模型族非默认，优先尝试加载模型族子目录下的
         同名文件，找不到再回退默认版本（当前已统一为中文单版本，glm/ 子目录已移除，
         family_specific 字段保留用于后续按需扩展）。system prompt 的最终文本由多个 section
         按固定顺序拼接而成：基础模板 → overlay（全局在前、项目级在后，同层内 soul→agent→memory）
         → 编码模式附录 → Skills 元数据；overlay 文件不存在时静默跳过，不影响主流程。
"""

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
    """Prompt 模板所属的模型族：DEFAULT 为通用模板（当前统一中文），GLM 枚举保留用于向后兼容"""

    DEFAULT = "default"
    GLM = "glm"


def classify_prompt_family(model_name: str) -> PromptFamily:
    """
    函数名：classify_prompt_family
    入参：
      - model_name (str)：当前使用的模型名称
    功能：根据模型名称判断应使用哪个 Prompt 模型族的模板
    运行逻辑：将模型名转小写后匹配关键字（"glm-"、"chatglm"），命中则归为 GLM 族，
             否则归为默认族。当前所有模板已统一为中文单版本，glm/ 子目录已移除，
             故 GLM 族命中后也会回退到默认中文版，仅保留枚举用于向后兼容与后续扩展。
    出参：PromptFamily - 识别出的模型族枚举值
    """
    lower = (model_name or "").lower()
    if any(kw in lower for kw in ["glm-", "chatglm"]):
        return PromptFamily.GLM
    return PromptFamily.DEFAULT


class PromptTemplate:
    """Prompt 模板"""

    def __init__(self, name: str, template: str, variables: list[str]):
        """
        函数名：__init__
        入参：
          - name (str)：模板名称，用于在 PromptManager 中索引
          - template (str)：模板原始文本，使用 $变量名 占位
          - variables (list[str])：模板声明所需的变量名列表（仅作元数据记录）
        功能：初始化一个 Prompt 模板对象
        运行逻辑：将 template 文本包装为 string.Template 对象，供 render() 渲染使用
        出参：无
        """
        self.name = name
        self.template = Template(template)
        self.variables = variables

    def render(self, **kwargs) -> str:
        """
        函数名：render
        入参：
          - **kwargs：渲染模板所需的变量键值对
        功能：将模板中的 $变量名 占位符替换为实际值，生成最终文本
        运行逻辑：调用 Template.safe_substitute，缺失的变量保持原占位符不报错
        出参：str - 渲染后的文本
        """
        return self.template.safe_substitute(**kwargs)


TEMPLATES_MANIFEST: list[dict] = [
    {
        "name": "system",
        "file": "system.md",
        "variables": ["working_directory", "platform", "date", "is_git_repo"],
        "family_specific": True,
    },
    {
        "name": "coding_appendix",
        "file": "coding_appendix.md",
        "variables": [],
        "family_specific": True,
    },
    {
        "name": "plan_mode",
        "file": "plan_mode.md",
        "variables": ["working_directory", "platform", "date", "is_git_repo"],
        "family_specific": True,
    },
    {
        "name": "final_response",
        "file": "final_response.md",
        "variables": ["task"],
        "family_specific": True,
    },
    {
        "name": "error",
        "file": "error.md",
        "variables": [
            "tool",
            "error",
            "original_args_section",
            "available_actions_section",
        ],
        "family_specific": True,
    },
    {
        "name": "approval_rejected",
        "file": "approval_rejected.md",
        "variables": [
            "tool",
            "original_args_section",
            "reason_section",
            "risk_level_section",
        ],
        "family_specific": True,
    },
    {
        "name": "midrun_compress_system",
        "file": "midrun_compress_system.md",
        "variables": [],
        "family_specific": True,
    },
    {
        "name": "midrun_compress_input",
        "file": "midrun_compress_input.md",
        "variables": ["task", "transcript", "existing_summary_block"],
        "family_specific": True,
    },
]


def _read_prompt_file(filename: str) -> str:
    """
    函数名：_read_prompt_file
    入参：
      - filename (str)：相对于 PROMPTS_DIR 的模板文件名（可含子目录，如 "glm/system.md"）
    功能：读取指定的 Prompt 模板文件内容
    运行逻辑：拼出完整路径，文件不存在则抛出 FileNotFoundError；存在则读取全文并去除首尾空白
    出参：str - 模板文件的文本内容
    """
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


class PromptManager:
    """Prompt 管理器 — 从 prompts/ 目录加载 .md 模板文件，支持模型族子目录"""

    def __init__(self, model_name: str = "", skill_registry: SkillRegistry | None = None):
        """
        函数名：__init__
        入参：
          - model_name (str)：当前使用的模型名称，用于判定 Prompt 模型族
          - skill_registry (SkillRegistry | None)：技能注册表，用于生成 Skills 元数据 section
        功能：初始化 PromptManager，并立即加载全部模板清单中的模板
        运行逻辑：识别模型族 → 记录 skill_registry → 调用 _load_templates 完成模板加载
        出参：无
        """
        self.templates: dict[str, PromptTemplate] = {}
        self.prompt_family = classify_prompt_family(model_name)
        self.skill_registry = skill_registry
        self._load_templates()

    def _resolve_file(self, entry: dict) -> str:
        """
        函数名：_resolve_file
        入参：
          - entry (dict)：TEMPLATES_MANIFEST 中的一条模板清单条目
        功能：解析某个模板条目实际应该读取的文件路径（决定是否走模型族子目录）
        运行逻辑：
          1. 若条目标记为 family_specific 且当前模型族不是 DEFAULT，先尝试拼出
             "{模型族目录}/{文件名}" 并试读
          2. 试读成功则直接返回该模型族专属路径
          3. 试读失败（文件不存在）记录警告并回退到默认文件名
          4. 非 family_specific 或模型族为 DEFAULT，直接返回默认文件名
        出参：str - 最终应读取的模板文件相对路径
        """
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
        """
        函数名：_load_templates
        入参：无
        功能：按 TEMPLATES_MANIFEST 清单批量加载全部模板到 self.templates
        运行逻辑：遍历清单每一条，先经 _resolve_file 确定实际文件路径，读取内容后
                 通过 register_template 注册为可用模板
        出参：无
        """
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
        ## 身份

        你是一个务实的协作型智能体，与用户在同一个项目中共同推进工作。

        ## 工作风格

        - 直接、基于证据。
        - 动手前先理解代码库。
        - 工作未真正完成时，不要假装已完成。

        ## 沟通

        - 更新简短、有用。
        - 证据充分时，直接回答真正的问题。
        - 进度更新应当传递信息，而不是把显而易见的下一步动作变成征求许可的提问。

        ## 质量品味

        - 优先选择最小且正确的改动。
        - 尊重既有代码模式，除非它们阻碍了任务。
    """
    )

    _DEFAULT_AGENT_MD = textwrap.dedent(
        """\
        ## 指令优先级

        - 首先遵循用户的明确指令。
        - 其次遵循内置安全与运行时协议。
        - 再次遵循当前运行时模式规则。
        - 然后遵循项目级 overlay。
        - 然后遵循全局 overlay。
        - 其余系统规则作为默认值。

        ## 证据优先

        - 如果代码、测试或仓库状态能回答问题，先去查看它们。
        - 不确定不是阻塞项。先调查。

        ## 技能与模式选择

        - 当某个技能可能适用时，先加载它再行动。
        - 把代码编辑工作视为编码模式，持续执行直到完成或真正被阻塞。

        ## 澄清门

        - 默认行动，而非确认。
        - 如果答案可以通过读代码、搜文件、查测试或使用可用工具获得，先去做这些。
        - 只有当缺失的信息只能来自用户意图、业务偏好、凭据、审批或不可获得的外部上下文时，才询问用户。
        - 当仓库模式已经给出明显的默认方案时，遵循该默认并简述假设，而不是停下来询问。

        ## 完成规则

        - 进度汇报不是完成。
        - 如果还有工作且没有真正的阻塞，继续执行。

        ## 停止规则

        - 当计划处于活动状态且有未完成步骤时，继续执行直到计划完全完成，除非当前步骤被仅用户能提供的信息阻塞。
        - 当计划处于活动状态时，停止前先更新计划。
        - 避免重复不产生新信息的工具调用。
        - 对同一动作失败 2 次后，解释问题并询问用户，而不是无限重试。
        - 如果上一批工具调用没有产生新事实，停止探索，直接回答或请求澄清。

        ## 错误处理

        - 工具调用失败时，先诊断为什么失败，再重试。
        - 修复具体失败后，继续当前计划步骤，除非该失败已证明步骤被阻塞。
        - 不要因为一次工具调用失败就切换实现路径。
        - 不要在没有证据的情况下做投机性的大改动。
        - 不要用相同参数盲目重试。

        ## 覆盖语义

        - 项目级 `.reflexion` 规则在本仓库中覆盖全局默认值。
    """
    )

    def _read_optional_text(self, path: Path) -> str:
        """
        函数名：_read_optional_text
        入参：
          - path (Path)：可选存在的文本文件路径（如某个 overlay 文件）
        功能：安全读取一个可能不存在的文本文件，读取失败不抛异常
        运行逻辑：文件存在且是普通文件才读取并去除首尾空白；不存在则返回空字符串；
                 读取过程中出现 OSError（如权限问题）记录警告日志后同样返回空字符串
        出参：str - 文件内容（去除首尾空白），不存在或读取失败时为空字符串
        """
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
        """
        函数名：_join_sections
        入参：
          - sections (list[str])：待拼接的文本片段列表（可能包含空字符串）
        功能：将多个文本片段拼接为最终 prompt 文本
        运行逻辑：先过滤掉空白/None 片段并去除各片段首尾空白，再用两个换行符连接
        出参：str - 拼接后的完整文本
        """
        normalized = [
            section.strip() for section in sections if str(section or "").strip()
        ]
        return "\n\n".join(normalized)

    def register_template(self, name: str, template: str, variables: list[str]):
        """
        函数名：register_template
        入参：
          - name (str)：模板名称，作为索引键
          - template (str)：模板原始文本
          - variables (list[str])：模板声明所需变量名列表
        功能：注册一个新模板到 self.templates
        运行逻辑：直接构造 PromptTemplate 并存入字典，若同名已存在则覆盖
        出参：无
        """
        self.templates[name] = PromptTemplate(name, template, variables)

    def get_template(self, name: str) -> PromptTemplate:
        """
        函数名：get_template
        入参：
          - name (str)：模板名称
        功能：按名称获取已注册的模板
        运行逻辑：直接从 self.templates 字典查找，找不到抛出 ValueError
        出参：PromptTemplate - 对应的模板对象
        """
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
        """
        函数名：get_system_prompt
        入参：
          - working_directory (str)：当前工作目录，注入基础模板变量
          - platform (str)：运行平台标识（如 Windows/macOS），注入基础模板变量
          - is_git_repo (bool)：当前目录是否为 Git 仓库
          - project_root (str | None)：项目根目录，用于定位项目级 overlay 文件
          - coding_mode (bool)：是否处于编码模式，为 True 时追加编码模式附录模板
        功能：组装完整的 system prompt 文本，是整个 Agent 系统提示词的最终入口
        运行逻辑：
          1. 渲染基础 system 模板（含工作目录、平台、日期、是否 git 仓库）
          2. 依次读取全局与项目级的 soul/agent/memory overlay 文件内容（不存在则跳过）
          3. coding_mode 为真时追加编码模式附录
          4. 追加 Skills 元数据 section（若有已启用的技能）
          5. 用 _join_sections 将所有非空片段用空行拼接为最终文本
        出参：str - 完整的 system prompt 文本
        """
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

        函数名：_build_skill_section
        入参：无（使用 self.skill_registry）
        功能：生成描述当前可用 Skills 的说明文本段落
        运行逻辑：
          1. 若未配置 skill_registry 或没有已启用的技能，返回空字符串（不注入该 section）
          2. 否则拼出固定的 Skills 使用指引文本
          3. 逐个列出已启用技能的名称、描述及依赖的其他技能（如有）
        出参：str - Skills 元数据文本，无可用技能时为空字符串
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
        """
        函数名：get_plan_mode_prompt
        入参：
          - working_directory (str)：当前工作目录
          - platform (str)：运行平台标识
          - is_git_repo (bool)：当前目录是否为 Git 仓库
        功能：生成 PLAN 模式（只规划不落地改动）下使用的提示词
        运行逻辑：直接渲染 plan_mode 模板，注入工作目录/平台/日期/是否 git 仓库四个变量
        出参：str - PLAN 模式提示词文本
        """
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
        """
        函数名：get_error_prompt
        入参：
          - error (str)：工具调用失败时的错误信息
          - tool (str)：出错的工具名称
          - original_args (dict | None)：本次调用使用的原始参数，用于回显给 LLM 参考
          - available_actions (list[str] | None)：该工具支持的可用 action 列表，用于提示可选修复方向
        功能：生成工具调用失败后反馈给 LLM 的错误提示词，引导其纠正后重试
        运行逻辑：
          1. 若提供了 original_args，过滤掉值为 None 的参数后逐行格式化为"参数: 值"列表文本
          2. 若提供了 available_actions，格式化为"该工具可用的 action 列表"提示行
          3. 两者均为可选 section，缺失则渲染为空字符串
          4. 渲染 error 模板，注入 tool/error/两个可选 section
        出参：str - 错误提示词文本
        """
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

    def get_approval_rejected_prompt(
        self,
        tool: str,
        original_args: dict | None = None,
        reason: str | None = None,
        risk_level: str | None = None,
    ) -> str:
        """
        函数名：get_approval_rejected_prompt
        入参：
          - tool (str)：被拒绝审批的工具名
          - original_args (dict | None)：本次调用使用的原始参数，用于回显给 LLM 参考
          - reason (str | None)：用户拒绝原因（来自 ApprovalResult.error；
            拒绝路径 set_approval_result(None) 会让 error 为 None，调用方需归一化兜底）
          - risk_level (str | None)：风险分级（本期不填，预留接口给
            EFFECT_DANGER_LEVEL 后续接入）
        功能：生成审批被拒后注入对话的提示词，引导 LLM 换路或降级重试
        运行逻辑：
          1. 若提供了 original_args，过滤掉值为 None 的参数后逐行格式化为"参数: 值"列表文本
          2. 若提供了 reason，格式化为"拒绝原因"提示行
          3. 若提供了 risk_level，格式化为"风险分级"提示行（本期预留，默认不填）
          4. 三个均为可选 section，缺失则渲染为空字符串
          5. 渲染 approval_rejected 模板，注入 tool/三个可选 section
        出参：str - 审批拒绝提示词文本
        """
        if original_args:
            args_lines = [
                f"  - {k}: {v!r}" for k, v in original_args.items() if v is not None
            ]
            original_args_section = (
                "- Arguments you used:\n" + "\n".join(args_lines) if args_lines else ""
            )
        else:
            original_args_section = ""

        reason_section = f"- Rejection reason: {reason}" if reason else ""
        risk_level_section = f"- Risk level: {risk_level}" if risk_level else ""

        return self.get_template("approval_rejected").render(
            tool=tool,
            original_args_section=original_args_section,
            reason_section=reason_section,
            risk_level_section=risk_level_section,
        )

    def get_final_response_prompt(self, task: str) -> str:
        """
        函数名：get_final_response_prompt
        入参：
          - task (str)：本轮执行的任务描述
        功能：生成引导 LLM 输出最终总结回复的提示词
        运行逻辑：直接渲染 final_response 模板，注入 task 变量
        出参：str - 最终回复引导提示词
        """
        return self.get_template("final_response").render(task=task)

    def get_midrun_compression_system_prompt(self) -> str:
        """
        函数名：get_midrun_compression_system_prompt
        入参：无
        功能：获取"运行中途压缩上下文"所用的 system 提示词
        运行逻辑：直接渲染 midrun_compress_system 模板（无变量）
        出参：str - 压缩任务的 system 提示词
        """
        return self.get_template("midrun_compress_system").render()

    def get_midrun_compression_prompt(
        self,
        *,
        task: str,
        transcript: str,
        existing_summary: str | None = None,
    ) -> str:
        """
        函数名：get_midrun_compression_prompt
        入参：
          - task (str)：当前执行的任务描述
          - transcript (str)：待压缩的对话/工具调用记录原文
          - existing_summary (str | None)：此前已生成的压缩摘要（若存在，用于增量压缩）
        功能：生成中途压缩上下文时使用的用户侧输入提示词
        运行逻辑：
          1. 若存在 existing_summary，构造"[已有摘要] ... [新对话]"的引导片段，
             提示 LLM 在已有摘要基础上做增量总结
          2. 否则该片段为空（首次压缩）
          3. 渲染 midrun_compress_input 模板，注入 task/transcript/existing_summary_block
        出参：str - 压缩任务的用户侧提示词
        """
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


