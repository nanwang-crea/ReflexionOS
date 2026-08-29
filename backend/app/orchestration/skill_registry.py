"""
技能注册表模块。

统一管理来自不同来源（项目本地、项目 .reflexion 目录、全局安装目录、
插件、兼容目录、配置额外目录）的技能：扫描发现、解析、注册、启用/禁用、
按需懒加载正文内容，供 Agent 运行时查询和加载可用技能。
"""

import logging
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from app.orchestration.skill_parser import parse_skill_md

logger = logging.getLogger(__name__)


class SkillSource(str, Enum):
    """技能来源类型，决定扫描路径和展示优先级"""

    PROJECT = "project"                    # 项目根目录下 skills/
    PROJECT_REFLEXION = "project_reflexion"  # 项目 .reflexion/skills/
    GLOBAL = "global"                      # 全局安装目录
    PLUGIN = "plugin"                      # 插件包附带的技能目录
    COMPAT = "compat"                      # 兼容旧版路径的目录
    CONFIG = "config"                      # 配置中额外指定的扫描目录


class SkillMetadata(BaseModel):
    """技能元数据：描述一个技能的来源、路径、启用状态等"""

    name: str
    description: str
    category: str = ""
    required_skills: list[str] = []
    file_path: str = ""
    source: str = ""
    source_type: SkillSource = SkillSource.PROJECT
    install_path: str = ""
    plugin_name: str = ""
    enabled: bool = True
    content_loaded: bool = False
    version: str = ""


class SkillRegistry:
    """技能注册表：扫描、注册、查询、启停技能"""

    def __init__(self):
        """初始化空注册表及正文内容缓存"""
        self.skills: dict[str, SkillMetadata] = {}
        self._content_cache: dict[str, str] = {}
        logger.info("SkillRegistry initialized")

    def scan_directory(self, dir_path: Path | str, source_type: SkillSource = SkillSource.PROJECT, plugin_name: str = "") -> int:
        """扫描一层子目录，注册其中的技能（每个子目录对应一个技能）

        仅遍历 dir_path 的直接子目录，子目录下存在 SKILL.md 才视为一个
        技能；解析失败的技能会记录异常日志并跳过，不中断整体扫描。

        Args:
            dir_path: 待扫描目录（其子目录即技能目录）
            source_type: 标记这批技能的来源类型
            plugin_name: 所属插件名（非插件来源可为空）

        Returns:
            int: 本次扫描新注册的技能数量
        """
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            logger.warning("Scan directory does not exist: %s", dir_path)
            return 0

        count = 0
        for child in sorted(dir_path.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                parsed = parse_skill_md(skill_file)
                fm = parsed.frontmatter
                meta = SkillMetadata(
                    name=fm.name,
                    description=fm.description,
                    category=fm.category,
                    required_skills=fm.required_skills,
                    file_path=parsed.file_path,
                    source=fm.source,
                    source_type=source_type,
                    install_path=str(child),
                    plugin_name=plugin_name,
                    enabled=True,
                    content_loaded=True,
                )
                self.skills[meta.name] = meta
                self._content_cache[meta.name] = parsed.body
                count += 1
                logger.info("Scanned skill: %s", meta.name)
            except Exception:
                logger.exception("Failed to parse skill: %s", skill_file)

        return count

    def scan_recursive(self, dir_path: Path | str, source_type: SkillSource = SkillSource.PLUGIN, plugin_name: str = "") -> int:
        """递归扫描目录树，注册所有找到的 SKILL.md 技能

        与 scan_directory 不同，此方法用 rglob 递归查找任意深度的
        SKILL.md，适用于插件包/全局目录这类层级不固定的场景。

        Args:
            dir_path: 待递归扫描的根目录
            source_type: 标记这批技能的来源类型
            plugin_name: 所属插件名（非插件来源可为空）

        Returns:
            int: 本次扫描新注册的技能数量
        """
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            logger.warning("Scan directory does not exist: %s", dir_path)
            return 0

        count = 0
        for skill_file in sorted(dir_path.rglob("SKILL.md")):
            try:
                parsed = parse_skill_md(skill_file)
                fm = parsed.frontmatter
                meta = SkillMetadata(
                    name=fm.name,
                    description=fm.description,
                    category=fm.category,
                    required_skills=fm.required_skills,
                    file_path=parsed.file_path,
                    source=fm.source,
                    source_type=source_type,
                    install_path=str(skill_file.parent),
                    plugin_name=plugin_name,
                    enabled=True,
                    content_loaded=True,
                )
                self.skills[meta.name] = meta
                self._content_cache[meta.name] = parsed.body
                count += 1
                logger.info("Scanned skill (recursive): %s", meta.name)
            except Exception:
                logger.exception("Failed to parse skill: %s", skill_file)

        return count

    def scan_all(self, plugin_skill_dirs: list[tuple[str, str]] | None = None, project_path: str | None = None) -> int:
        """全量重新扫描所有技能来源，重建整个注册表

        扫描顺序（后扫描的同名技能会覆盖先扫描的）：
            1. 项目 skills/ 目录（一层，PROJECT）
            2. 项目 .reflexion/skills/ 目录（一层，PROJECT_REFLEXION）
            3. 配置中的全局安装目录（递归，GLOBAL）
            4. 传入的插件技能目录列表（递归，PLUGIN，逐插件标记来源名）
            5. 配置中的兼容目录列表（一层，COMPAT）
            6. 配置中的额外扫描目录列表（一层，CONFIG）

        Args:
            plugin_skill_dirs: (插件名, 技能目录路径) 元组列表，通常来自
                PluginLoader.get_all_skill_dirs()
            project_path: 项目根路径，缺省使用当前工作目录

        Returns:
            int: 全部来源汇总的新注册技能总数
        """
        self.skills.clear()
        self._content_cache.clear()
        from app.config.settings import config_manager

        skill_settings = config_manager.settings.skill
        total = 0

        proj = Path(project_path) if project_path else Path.cwd()

        project_skills = proj / "skills"
        if project_skills.exists():
            total += self.scan_directory(project_skills, SkillSource.PROJECT)

        project_reflexion_skills = proj / ".reflexion" / "skills"
        if project_reflexion_skills.exists():
            total += self.scan_directory(project_reflexion_skills, SkillSource.PROJECT_REFLEXION)

        global_skills = Path(skill_settings.install_dir)
        if global_skills.exists():
            total += self.scan_recursive(global_skills, SkillSource.GLOBAL)

        if plugin_skill_dirs:
            for plugin_name, skill_dir in plugin_skill_dirs:
                p = Path(skill_dir)
                if p.exists():
                    total += self.scan_recursive(p, SkillSource.PLUGIN, plugin_name=plugin_name)

        for compat_dir in skill_settings.compat_dirs:
            p = Path(compat_dir)
            if p.exists():
                total += self.scan_directory(p, SkillSource.COMPAT)

        for extra_dir in skill_settings.scan_dirs:
            p = Path(extra_dir)
            if p.exists():
                total += self.scan_directory(p, SkillSource.CONFIG)

        return total

    def register_skill(self, skill: SkillMetadata) -> None:
        """直接注册（或覆盖）一个技能元数据

        Args:
            skill: 待注册的技能元数据

        Returns:
            None
        """
        self.skills[skill.name] = skill
        logger.info("Registered skill: %s", skill.name)

    def unregister_skill(self, name: str) -> bool:
        """注销一个已注册技能，同时清理其正文缓存

        Args:
            name: 技能名称

        Returns:
            bool: 是否存在并成功注销
        """
        if name in self.skills:
            del self.skills[name]
            self._content_cache.pop(name, None)
            logger.info("Unregistered skill: %s", name)
            return True
        return False

    def get_skill(self, name: str) -> SkillMetadata | None:
        """按名称获取技能元数据

        Args:
            name: 技能名称

        Returns:
            SkillMetadata | None: 对应元数据，不存在则返回 None
        """
        return self.skills.get(name)

    def get_skill_content(self, name: str) -> str | None:
        """获取技能正文内容，按需懒加载

        优先读取内存缓存；未命中缓存时根据元数据中的 file_path 重新解析
        SKILL.md 文件补全缓存（用于扫描阶段未加载正文的场景）。

        Args:
            name: 技能名称

        Returns:
            str | None: 技能正文（frontmatter 之后的部分），技能不存在、
                无 file_path 或解析失败时返回 None
        """
        if name not in self.skills:
            return None

        if name in self._content_cache:
            return self._content_cache[name]

        skill = self.skills[name]
        if skill.file_path:
            try:
                parsed = parse_skill_md(skill.file_path)
                self._content_cache[name] = parsed.body
                skill.content_loaded = True
                return parsed.body
            except Exception:
                logger.exception("Failed to lazy-load skill content: %s", name)
                return None

        return None

    def list_skills(self) -> list[SkillMetadata]:
        """列出所有已注册技能（不论是否启用）

        Returns:
            list[SkillMetadata]: 全部技能元数据列表
        """
        return list(self.skills.values())

    def list_enabled_skills(self) -> list[SkillMetadata]:
        """列出所有已启用的技能

        Returns:
            list[SkillMetadata]: enabled=True 的技能元数据列表
        """
        return [s for s in self.skills.values() if s.enabled]

    def list_skills_by_category(self, category: str) -> list[SkillMetadata]:
        """按分类筛选技能

        Args:
            category: 技能分类名

        Returns:
            list[SkillMetadata]: 该分类下的技能元数据列表
        """
        return [s for s in self.skills.values() if s.category == category]

    def enable_skill(self, name: str) -> bool:
        """启用指定技能

        Args:
            name: 技能名称

        Returns:
            bool: 技能是否存在并已启用
        """
        skill = self.get_skill(name)
        if skill:
            skill.enabled = True
            logger.info("Enabled skill: %s", name)
            return True
        return False

    def disable_skill(self, name: str) -> bool:
        """禁用指定技能

        Args:
            name: 技能名称

        Returns:
            bool: 技能是否存在并已禁用
        """
        skill = self.get_skill(name)
        if skill:
            skill.enabled = False
            logger.info("Disabled skill: %s", name)
            return True
        return False

    def refresh(self, plugin_skill_dirs: list[str] | None = None, project_path: str | None = None) -> int:
        """刷新注册表，等价于重新调用 scan_all

        Args:
            plugin_skill_dirs: 透传给 scan_all 的插件技能目录列表
            project_path: 透传给 scan_all 的项目根路径

        Returns:
            int: 刷新后注册的技能总数
        """
        return self.scan_all(plugin_skill_dirs=plugin_skill_dirs, project_path=project_path)


skill_registry = SkillRegistry()
