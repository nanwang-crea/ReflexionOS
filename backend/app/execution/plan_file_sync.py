import logging
import os
import re
import time
from datetime import datetime

from app.execution.plan_engine import Plan

logger = logging.getLogger(__name__)


class PlanFileSync:
    """Bidirectional sync between Plan objects and .reflexion/plans/ markdown files."""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir

    def _resolve_base_dir(self, project_path: str | None = None) -> str:
        if self.base_dir:
            return self.base_dir
        root = project_path or os.getcwd()
        return os.path.join(root, ".reflexion", "plans")

    def _make_filename(self, slug: str) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_slug = re.sub(r'[^\w-]', '', slug.replace(" ", "-").lower())[:40]
        return f"{date_str}-{safe_slug}.md"

    def write(self, plan: Plan, slug: str = "task", project_path: str | None = None) -> str:
        base = self._resolve_base_dir(project_path)
        os.makedirs(base, exist_ok=True)
        filename = self._make_filename(slug)
        path = os.path.join(base, filename)
        content = plan.render_to_markdown()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("计划文件已写入: %s", path)
        return path

    def sync(self, plan: Plan, path: str, project_path: str | None = None) -> None:
        resolved = self._validate_plan_path(path, project_path)
        content = plan.render_to_markdown()
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug("计划文件已同步: %s", resolved)

    def read(self, path: str) -> Plan | None:
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return Plan.parse_from_markdown(content)

    def _validate_plan_path(self, path: str, project_path: str | None = None) -> str:
        base = self._resolve_base_dir(project_path)
        resolved = os.path.realpath(path)
        base_resolved = os.path.realpath(base)
        if not resolved.startswith(base_resolved + os.sep) and resolved != base_resolved:
            raise ValueError(f"路径超出计划目录: {path}")
        return resolved

    def delete(self, path: str, project_path: str | None = None) -> None:
        resolved = self._validate_plan_path(path, project_path)
        if os.path.exists(resolved):
            os.remove(resolved)
            logger.info("计划文件已删除: %s", resolved)

    def find_recovery_plan(
        self,
        project_path: str | None = None,
        max_age_hours: int = 24,
    ) -> str | None:
        base = self._resolve_base_dir(project_path)
        if not os.path.isdir(base):
            return None
        max_age_seconds = max_age_hours * 3600
        now = time.time()
        md_files = sorted(
            [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".md")],
            key=lambda p: os.path.getmtime(p),
            reverse=True,
        )
        for path in md_files:
            file_age = now - os.path.getmtime(path)
            if file_age > max_age_seconds:
                logger.debug("跳过过期计划文件 (%.1fh > %dh): %s", file_age / 3600, max_age_hours, path)
                continue
            plan = self.read(path)
            if plan and not plan.is_complete:
                return path
        return None
