"""文件内容读写服务：为前端代码编辑器提供文件读取、写入、diff 对比和目录树浏览能力，
所有路径操作均经过 PathSecurity 校验以防止路径穿越到项目目录之外。
跨平台说明：git 子进程调用在 Windows 上因 uvicorn --reload 强制使用 WindowsSelectorEventLoopPolicy
（不支持 asyncio.create_subprocess_exec），需回退为线程池 + 同步 subprocess.run。"""
import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from app.errors import SecurityError, ValidationError
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
    """根据文件扩展名推断代码高亮所用的语言标识。
    输入：path（文件路径）
    输出：语言标识字符串，未知扩展名返回 "plaintext"
    """
    ext = Path(path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(ext, "plaintext")


class FileContentService:
    """文件内容读取与写入服务"""

    TREE_CACHE_TTL = 5.0

    def __init__(self) -> None:
        """初始化服务，准备目录树缓存（按 project_id 缓存，避免频繁遍历磁盘）。"""
        self._tree_cache: dict[str, tuple[float, dict]] = {}

    EXCLUDED_DIRS = frozenset({
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".ruff_cache", ".pytest_cache", "dist", "build", ".mypy_cache",
        ".tox", ".eggs", ".idea", ".vscode",
    })

    def _get_project_path(self, project_id: str) -> str:
        """根据 project_id 获取项目根目录绝对路径。
        输入：project_id
        输出：项目根目录字符串
        """
        return project_service.get_project_path(project_id)

    def _make_security(self, project_path: str) -> PathSecurity:
        """为指定项目目录创建路径安全校验器。
        输入：project_path（项目根目录）
        输出：PathSecurity 实例
        """
        return create_project_security(project_path)

    async def _run_git(self, argv: list[str], cwd: str, timeout: float) -> tuple[int, bytes, bytes]:
        """
        执行 git 子进程，返回 (returncode, stdout, stderr)。

        Windows 下 uvicorn --reload 会强制切换到 WindowsSelectorEventLoopPolicy，
        该事件循环不支持 asyncio.create_subprocess_exec（直接抛 NotImplementedError），
        因此 Windows 平台改用线程池 + 同步 subprocess.run 绕过限制（与 shell_tool.py 一致）。
        """
        if sys.platform == "win32":
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._run_git_sync, argv, cwd, timeout)

        process = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return process.returncode, stdout, stderr

    def _run_git_sync(self, argv: list[str], cwd: str, timeout: float) -> tuple[int, bytes, bytes]:
        """同步执行 git 子进程，仅在线程池中被 Windows 分支调用。"""
        result = subprocess.run(
            argv, cwd=cwd, capture_output=True, timeout=timeout, check=False,
        )
        return result.returncode, result.stdout, result.stderr

    async def get_file_content(self, project_id: str, path: str) -> dict:
        """读取项目内指定文件的完整文本内容。
        输入：project_id、path（相对项目根目录的文件路径）
        逻辑：校验路径合法性 -> 文件不存在返回 exists=False -> 按 UTF-8 读取文本内容
        输出：{content: str, language: str, exists: bool}
        异常：ValidationError（路径越界 / 编码不支持 / 读取失败）
        """
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
        except UnicodeDecodeError as exc:
            # 保留原始异常链（from exc），便于排查具体是哪一步解码失败
            raise ValidationError("文件编码不支持，仅支持 UTF-8 文本文件") from exc
        except OSError as exc:
            raise ValidationError(f"读取文件失败: {exc}") from exc

        return {
            "content": content,
            "language": _infer_language(path),
            "exists": True,
        }

    async def get_diff_content(self, project_id: str, path: str) -> dict:
        """获取文件相对 HEAD 提交的 diff 用两侧内容（原始版本 + 当前工作区版本）。
        输入：project_id、path（相对项目根目录的文件路径）
        逻辑：
          1. 用 git show HEAD:<path> 取该文件在 HEAD 的内容作为 original（新增文件等情况取不到则为空字符串）；
          2. 读取工作区当前文件内容作为 modified（文件已被删除则为空字符串）。
        输出：{original: str, modified: str, language: str}
        异常：ValidationError（路径越界 / git 不可用或超时 / 文件编码不支持）
        """
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
            returncode, stdout, stderr = await self._run_git(
                ["git", "show", f"HEAD:{relative_path}"], cwd=project_path, timeout=10,
            )
            if returncode == 0:
                original = stdout.decode("utf-8", errors="replace")
            else:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.debug("git show HEAD:%s failed: %s", relative_path, err_msg)
                original = ""
        except FileNotFoundError as exc:
            raise ValidationError("git 命令不可用，无法获取 diff") from exc
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise ValidationError("获取 diff 超时") from exc

        if abs_path.exists() and abs_path.is_file():
            try:
                modified = abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValidationError("文件编码不支持，仅支持 UTF-8 文本文件") from exc
            except OSError as exc:
                raise ValidationError(f"读取文件失败: {exc}") from exc

        return {
            "original": original,
            "modified": modified,
            "language": _infer_language(path),
        }

    async def get_file_tree(self, project_id: str) -> dict:
        """获取项目目录树（含每个文件的 git 状态标记），带短时缓存以降低磁盘遍历频率。
        输入：project_id
        逻辑：命中 TREE_CACHE_TTL 秒内的缓存直接返回；否则查询 git 状态并重新构建整棵树，写入缓存
        输出：{tree: [目录树节点...]}
        """
        project_path = self._get_project_path(project_id)
        now = time.monotonic()
        cached = self._tree_cache.get(project_id)
        if cached and (now - cached[0]) < self.TREE_CACHE_TTL:
            return cached[1]

        git_status_map = await self._get_git_status_map(project_path)
        tree = self._build_tree(project_path, project_path, git_status_map)
        result = {"tree": tree}
        self._tree_cache[project_id] = (now, result)
        return result

    async def _get_git_status_map(self, project_path: str) -> dict[str, str]:
        """执行 git status --porcelain 并解析为文件路径到状态的映射，供目录树标注变更状态。
        输入：project_path（项目根目录）
        逻辑：解析 porcelain 输出的双字符状态码（索引区/工作区），暂存优先于未暂存判定，
              R（重命名）归一化为 M，C（复制）归一化为 A，?? 表示未跟踪(U)，!! 表示被忽略（跳过不记录）
        输出：{相对路径: 状态字符(M/A/D/U)}；git 不可用/超时/失败时返回空字典
        """
        status_map: dict[str, str] = {}

        try:
            returncode, stdout, _ = await self._run_git(
                ["git", "status", "--porcelain"], cwd=project_path, timeout=10,
            )
            if returncode != 0:
                return {}
        except (FileNotFoundError, TimeoutError, subprocess.TimeoutExpired):
            return {}

        for line in stdout.decode("utf-8", errors="replace").splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            path = line[3:].strip()
            if not path:
                continue
            x, y = xy[0], xy[1]
            if x in ("M", "A", "D", "R", "C"):
                status_map[path] = {"M": "M", "A": "A", "D": "D", "R": "M", "C": "A"}.get(x, "M")
            elif y in ("M", "A", "D"):
                status_map[path] = {"M": "M", "A": "A", "D": "D"}.get(y, "M")
            elif xy == "??":
                status_map[path] = "U"
            elif xy == "!!":
                pass

        return status_map

    def _build_tree(self, root_path: str, current_path: str, git_status_map: dict[str, str]) -> list[dict]:
        """递归构建目录树结构，跳过隐藏文件（.env 除外）和 EXCLUDED_DIRS 中的目录。
        输入：root_path（项目根目录，用于计算相对路径）、current_path（当前递归到的目录）、
              git_status_map（文件路径到 git 状态的映射，用于标注文件节点）
        输出：[{name, type("directory"/"file"), path, git_status, children}, ...]
              目录节点无 git_status（None）且递归包含 children；文件节点 children 为 None
        """
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
        """将内容写入项目内指定文件，父目录不存在时自动创建。
        输入：project_id、path（相对项目根目录的文件路径）、content（待写入的文本内容）
        输出：{success: bool, error: str|None}
        异常：ValidationError（路径越界，写入权限校验失败）
        """
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
