"""
技能 Markdown 文件解析模块。

负责解析 SKILL.md 文件：提取顶部 YAML frontmatter（元数据）与正文内容，
供 skill_registry 等模块注册技能时使用。
"""

import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 匹配文件开头的 YAML frontmatter 块（--- ... ---）
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)(?:\n)?---\s*\n", re.DOTALL)


class SkillFrontmatter(BaseModel):
    """技能 frontmatter 元数据模型"""

    name: str
    description: str
    category: str = ""
    required_skills: list[str] = []
    source: str = ""


class ParsedSkill(BaseModel):
    """解析后的技能文件：元数据 + 正文 + 来源路径"""

    frontmatter: SkillFrontmatter
    body: str
    file_path: str


def parse_skill_md(path: Path | str) -> ParsedSkill:
    """解析单个 SKILL.md 文件

    工作流程：
        1. 读取文件全文；
        2. 用正则匹配开头的 YAML frontmatter 块并尝试解析；
        3. frontmatter 缺失/解析失败/没有 name 字段时，回退为用父目录名作为
           技能名、description 为空的默认元数据；
        4. frontmatter 之后（或全文，若无 frontmatter）的部分作为正文 body。

    Args:
        path: SKILL.md 文件路径

    Returns:
        ParsedSkill: 包含 frontmatter、body、file_path 的解析结果

    Raises:
        FileNotFoundError: 文件不存在
    """
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
            # frontmatter 存在但缺少 name 或解析失败：用父目录名兜底
            frontmatter = SkillFrontmatter(
                name=parent_dir_name,
                description="",
            )
        body = content[match.end():]
    else:
        # 没有 frontmatter：全文作为正文，元数据仅用父目录名兜底
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
