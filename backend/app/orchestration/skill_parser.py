import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)(?:\n)?---\s*\n", re.DOTALL)


class SkillFrontmatter(BaseModel):
    name: str
    description: str
    category: str = ""
    required_skills: list[str] = []
    source: str = ""


class ParsedSkill(BaseModel):
    frontmatter: SkillFrontmatter
    body: str
    file_path: str


def parse_skill_md(path: Path | str) -> ParsedSkill:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")

    content = file_path.read_text(encoding="utf-8")
    parent_dir_name = file_path.parent.name

    match = _FRONTMATTER_RE.match(content)
    if match:
        raw_yaml = match.group(1)
        try:
            data = yaml.safe_load(raw_yaml)
        except yaml.YAMLError:
            data = None

        if isinstance(data, dict) and data.get("name"):
            frontmatter = SkillFrontmatter(
                name=data.get("name", parent_dir_name),
                description=data.get("description", ""),
                category=data.get("category", ""),
                required_skills=data.get("required_skills", []),
                source=data.get("source", ""),
            )
        else:
            frontmatter = SkillFrontmatter(
                name=parent_dir_name,
                description="",
            )
        body = content[match.end():]
    else:
        frontmatter = SkillFrontmatter(
            name=parent_dir_name,
            description="",
        )
        body = content

    return ParsedSkill(
        frontmatter=frontmatter,
        body=body,
        file_path=str(file_path),
    )
