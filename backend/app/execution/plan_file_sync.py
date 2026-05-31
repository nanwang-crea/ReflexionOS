import logging
import os
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
        safe_slug = slug.replace(" ", "-").lower()[:40]
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

    def sync(self, plan: Plan, path: str) -> None:
        content = plan.render_to_markdown()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug("计划文件已同步: %s", path)

    def read(self, path: str) -> Plan | None:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return Plan.parse_from_markdown(content)

    def delete(self, path: str) -> None:
        if os.path.exists(path):
            os.remove(path)
            logger.info("计划文件已删除: %s", path)

    def find_recovery_plan(self, project_path: str | None = None) -> str | None:
        base = self._resolve_base_dir(project_path)
        if not os.path.isdir(base):
            return None
        md_files = sorted(
            [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".md")],
            key=lambda p: os.path.getmtime(p),
            reverse=True,
        )
        for path in md_files:
            plan = self.read(path)
            if plan and not plan.is_complete:
                return path
        return None
