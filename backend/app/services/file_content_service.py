import asyncio
import logging
import os
from pathlib import Path

from app.errors import NotFoundValueError, SecurityError, ValidationError
from app.security.path_security import PathSecurity
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

    def _get_project_path(self, project_id: str) -> str:
        project = project_service.get_project_or_raise(project_id)
        return project.path

    def _make_security(self, project_path: str) -> PathSecurity:
        return PathSecurity(allowed_base_paths=[project_path], base_dir=project_path)

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
