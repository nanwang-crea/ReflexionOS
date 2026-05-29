import asyncio
import logging
import os
from pathlib import Path

from app.errors import NotFoundValueError, SecurityError, ValidationError
from app.security.path_security import PathSecurity, create_project_security
from app.services.project_service import project_service

logger = logging.getLogger(__name__)

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".sh": "shell",
    ".sql": "sql",
    ".xml": "xml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".lua": "lua",
    ".r": "r",
    ".dart": "dart",
}


def _infer_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, "plaintext")


class FileContentService:
    """文件内容读取与写入服务"""

    def __init__(self) -> None:
        pass

    EXCLUDED_DIRS = frozenset({
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".mypy_cache",
        ".tox", ".eggs", ".idea", ".vscode",
    })

    def _get_project_path(self, project_id: str) -> str:
        return project_service.get_project_path(project_id)

    def _make_security(self, project_path: str) -> PathSecurity:
        return create_project_security(project_path)

    async def get_file_content(self, project_id: str, path: str) -> dict:
        project_path = self._get_project_path(project_id)
        security = self._make_security(project_path)

        try:
            validated_path = security.validate_path(path)
        except SecurityError as exc:
            raise ValidationError(str(exc)) from exc

        abs_path = Path(validated_path)
        if not abs_path.exists() or not abs_path.is_file():
            return {
                "content": "",
                "language": _infer_language(path),
                "exists": False,
            }

        try:
            content = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValidationError("文件编码不支持，仅支持 UTF-8 文本文件")
        except OSError as exc:
            raise ValidationError(f"读取文件失败: {exc}")

        return {
            "content": content,
            "language": _infer_language(path),
            "exists": True,
        }

    async def get_diff_content(self, project_id: str, path: str) -> dict:
        project_path = self._get_project_path(project_id)
        security = self._make_security(project_path)

        try:
            validated_path = security.validate_path(path)
        except SecurityError as exc:
            raise ValidationError(str(exc)) from exc

        abs_path = Path(validated_path)
        original = ""
        modified = ""

        resolved_project_path = os.path.realpath(project_path)
        relative_path = os.path.relpath(validated_path, resolved_project_path)
        try:
            result = await asyncio.create_subprocess_exec(
                "git", "show", f"HEAD:{relative_path}",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
            if result.returncode == 0:
                original = stdout.decode("utf-8", errors="replace")
            else:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.debug("git show HEAD:%s failed: %s", relative_path, err_msg)
                original = ""
        except FileNotFoundError:
            raise ValidationError("git 命令不可用，无法获取 diff")

        if abs_path.exists() and abs_path.is_file():
            try:
                modified = abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise ValidationError("文件编码不支持，仅支持 UTF-8 文本文件")
            except OSError as exc:
                raise ValidationError(f"读取文件失败: {exc}")

        return {
            "original": original,
            "modified": modified,
            "language": _infer_language(path),
        }

    async def get_file_tree(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        git_status_map = await self._get_git_status_map(project_path)
        tree = self._build_tree(project_path, project_path, git_status_map)
        return {"tree": tree}

    async def _get_git_status_map(self, project_path: str) -> dict[str, str]:
        status_map: dict[str, str] = {}

        for args, status in [
            (["diff", "--name-status"], "M"),
            (["diff", "--cached", "--name-status"], None),
        ]:
            try:
                result = await asyncio.create_subprocess_exec(
                    "git", *args,
                    cwd=project_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await result.communicate()
                if result.returncode != 0:
                    continue
                for line in stdout.decode("utf-8", errors="replace").splitlines():
                    parts = line.split("\t")
                    if len(parts) < 2:
                        continue
                    code = parts[0][0]
                    path = parts[-1]
                    mapped = {"M": "M", "A": "A", "D": "D", "R": "M", "C": "A"}.get(
                        code, "M"
                    )
                    status_map[path] = status or mapped
            except FileNotFoundError:
                return {}

        try:
            result = await asyncio.create_subprocess_exec(
                "git", "ls-files", "--others", "--exclude-standard",
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                for line in stdout.decode("utf-8", errors="replace").splitlines():
                    if line:
                        status_map[line] = "U"
        except FileNotFoundError:
            return {}

        return status_map

    def _build_tree(self, root_path: str, current_path: str, git_status_map: dict[str, str]) -> list[dict]:
        try:
            entries = sorted(os.listdir(current_path))
        except PermissionError:
            return []

        dirs = []
        files = []

        for entry in entries:
            if entry.startswith(".") and entry not in (".env", ".env.local"):
                continue

            full_path = os.path.join(current_path, entry)

            if os.path.isdir(full_path):
                if entry in self.EXCLUDED_DIRS:
                    continue
                dirs.append(entry)
            elif os.path.isfile(full_path):
                files.append(entry)

        result = []

        for d in dirs:
            full_path = os.path.join(current_path, d)
            rel_path = os.path.relpath(full_path, root_path)
            children = self._build_tree(root_path, full_path, git_status_map)
            result.append({
                "name": d,
                "type": "directory",
                "path": rel_path,
                "git_status": None,
                "children": children,
            })

        for f in files:
            full_path = os.path.join(current_path, f)
            rel_path = os.path.relpath(full_path, root_path)
            result.append({
                "name": f,
                "type": "file",
                "path": rel_path,
                "git_status": git_status_map.get(rel_path),
                "children": None,
            })

        return result

    async def write_file_content(self, project_id: str, path: str, content: str) -> dict:
        project_path = self._get_project_path(project_id)
        security = self._make_security(project_path)

        try:
            validated_path = security.validate_write_path(path)
        except SecurityError as exc:
            raise ValidationError(str(exc)) from exc

        abs_path = Path(validated_path)
        dir_path = abs_path.parent
        if dir_path and not dir_path.exists():
            os.makedirs(dir_path, exist_ok=True)

        try:
            abs_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return {"success": False, "error": f"写入文件失败: {exc}"}

        logger.info("写入文件: %s", validated_path)
        return {"success": True, "error": None}


file_content_service = FileContentService()
