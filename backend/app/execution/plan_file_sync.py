import contextlib
import logging
import os
import tempfile
import time

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

    def write(
        self, plan: Plan, session_id: str, project_path: str | None = None
    ) -> str:
        base = self._resolve_base_dir(project_path)
        os.makedirs(base, exist_ok=True)
        filename = f"{session_id}.md"
        path = os.path.join(base, filename)
        content = plan.render_to_markdown()
        self._atomic_write(path, content)
        logger.info("计划文件已写入: %s", path)
        return path

    def sync(self, plan: Plan, path: str, project_path: str | None = None) -> None:
        resolved = self._validate_plan_path(path, project_path)
        content = plan.render_to_markdown()
        self._atomic_write(resolved, content)
        logger.debug("计划文件已同步: %s", resolved)

    @staticmethod
    def _atomic_write(path: str, content: str) -> None:
        """Write content atomically using temp file + rename."""
        dir_name = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, path)
        except BaseException:
            # 清理临时文件，删除失败可忽略（如文件已被 os.replace 取走）
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

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
        if (
            not resolved.startswith(base_resolved + os.sep)
            and resolved != base_resolved
        ):
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
        session_id: str | None = None,
        max_age_hours: int = 24,
    ) -> str | None:
        base = self._resolve_base_dir(project_path)
        if not os.path.isdir(base):
            return None
        max_age_seconds = max_age_hours * 3600
        now = time.time()

        # Session-scoped recovery: prefer the plan file for this specific session
        if session_id:
            session_path = os.path.join(base, f"{session_id}.md")
            if os.path.exists(session_path):
                file_age = now - os.path.getmtime(session_path)
                if file_age <= max_age_seconds:
                    plan = self.read(session_path)
                    if plan and not plan.is_complete:
                        logger.info("找到 session 级计划文件: %s", session_path)
                        return session_path
                    elif plan and plan.is_complete:
                        logger.debug("Session 计划已完成，跳过: %s", session_path)
                else:
                    logger.debug("Session 计划文件过期: %s", session_path)

        # Fallback: scan for any incomplete plan (backwards compatibility)
        md_files = sorted(
            [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".md")],
            key=lambda p: os.path.getmtime(p),
            reverse=True,
        )
        for path in md_files:
            file_age = now - os.path.getmtime(path)
            if file_age > max_age_seconds:
                logger.debug(
                    "跳过过期计划文件 (%.1fh > %dh): %s",
                    file_age / 3600,
                    max_age_hours,
                    path,
                )
                continue
            plan = self.read(path)
            if plan and not plan.is_complete:
                return path
        return None
