import logging
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from app.orchestration.skill_parser import parse_skill_md

logger = logging.getLogger(__name__)


class SkillSource(str, Enum):
    PROJECT = "project"
    PROJECT_REFLEXION = "project_reflexion"
    GLOBAL = "global"
    PLUGIN = "plugin"
    COMPAT = "compat"
    CONFIG = "config"


class SkillMetadata(BaseModel):
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

    def __init__(self):
        self.skills: dict[str, SkillMetadata] = {}
        self._content_cache: dict[str, str] = {}
        logger.info("SkillRegistry initialized")

    def scan_directory(self, dir_path: Path | str, source_type: SkillSource = SkillSource.PROJECT, plugin_name: str = "") -> int:
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
        self.skills[skill.name] = skill
        logger.info("Registered skill: %s", skill.name)

    def unregister_skill(self, name: str) -> bool:
        if name in self.skills:
            del self.skills[name]
            self._content_cache.pop(name, None)
            logger.info("Unregistered skill: %s", name)
            return True
        return False

    def get_skill(self, name: str) -> SkillMetadata | None:
        return self.skills.get(name)

    def get_skill_content(self, name: str) -> str | None:
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
        return list(self.skills.values())

    def list_enabled_skills(self) -> list[SkillMetadata]:
        return [s for s in self.skills.values() if s.enabled]

    def list_skills_by_category(self, category: str) -> list[SkillMetadata]:
        return [s for s in self.skills.values() if s.category == category]

    def enable_skill(self, name: str) -> bool:
        skill = self.get_skill(name)
        if skill:
            skill.enabled = True
            logger.info("Enabled skill: %s", name)
            return True
        return False

    def disable_skill(self, name: str) -> bool:
        skill = self.get_skill(name)
        if skill:
            skill.enabled = False
            logger.info("Disabled skill: %s", name)
            return True
        return False

    def refresh(self, plugin_skill_dirs: list[str] | None = None, project_path: str | None = None) -> int:
        return self.scan_all(plugin_skill_dirs=plugin_skill_dirs, project_path=project_path)


skill_registry = SkillRegistry()
