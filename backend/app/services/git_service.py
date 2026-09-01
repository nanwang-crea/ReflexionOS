# Git 操作服务：封装所有 git 子进程调用（状态查询、暂存/取消暂存、提交、推送/拉取、分支管理、日志等）。
# 跨平台兼容：Windows + uvicorn --reload 强制 WindowsSelectorEventLoopPolicy，不支持 asyncio.create_subprocess_exec，
# 因此 Windows 上改用线程池 + 同步 subprocess.run，与 file_content_service / grep_tool 保持一致。

import asyncio
import contextlib
import logging
import os
import subprocess
import sys

from app.errors import ValidationError
from app.security.path_security import PathSecurity, create_project_security
from app.services.project_service import project_service

logger = logging.getLogger(__name__)


class GitService:
    """Git 操作服务类：封装项目仓库的状态查询、暂存区管理、提交、分支、远端同步等操作。"""

    def _get_project_path(self, project_id: str) -> str:
        """
        根据 project_id 获取项目根目录的绝对路径。
        输入：project_id（项目唯一标识）
        输出：项目根目录字符串
        """
        return project_service.get_project_path(project_id)

    def _make_security(self, project_path: str) -> PathSecurity:
        """
        为指定项目目录创建路径安全校验器，防止路径穿越攻击。
        输入：project_path（项目根目录）
        输出：PathSecurity 实例
        """
        return create_project_security(project_path)

    def _run_git_sync(self, args: tuple[str, ...], cwd: str, timeout: float) -> tuple[int, bytes, bytes]:
        """
        同步执行 git 命令，供 Windows 线程池分支调用。
        Windows 的 asyncio 事件循环不支持 create_subprocess_exec，必须走同步路径。
        输入：args（git 子命令及参数）、cwd（工作目录）、timeout（秒）
        输出：(returncode, stdout bytes, stderr bytes)
        """
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, timeout=timeout, check=False,
        )
        return result.returncode, result.stdout, result.stderr

    async def _run_git(self, *args: str, cwd: str, timeout: float = 120) -> tuple[int, str, str]:
        """
        异步执行 git 子进程，返回 (returncode, stdout, stderr)。

        跨平台分支逻辑：
        - Windows：uvicorn --reload 强制 WindowsSelectorEventLoopPolicy，
          该循环不支持 asyncio.create_subprocess_exec（抛 NotImplementedError），
          因此改用线程池 + 同步 subprocess.run，与 file_content_service 保持一致。
        - 非 Windows：直接使用 asyncio.create_subprocess_exec。

        输入：*args（git 子命令及参数）、cwd（工作目录）、timeout（超时秒数，默认 120）
        输出：(returncode: int, stdout: str, stderr: str)
        异常：ValidationError（git 不可用 / 超时）
        """
        try:
            if sys.platform == "win32":
                loop = asyncio.get_event_loop()
                rc, out, err = await loop.run_in_executor(
                    None, self._run_git_sync, args, cwd, timeout
                )
                return rc, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")

            result = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=timeout)
            return (
                result.returncode,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except FileNotFoundError:
            raise ValidationError("git 命令不可用") from None
        except TimeoutError:
            raise ValidationError(
                f"git {' '.join(args)} 超时（{timeout}s）"
            ) from None

    def _validate_paths(self, paths: list[str], project_path: str) -> list[str]:
        """
        校验路径列表是否在项目目录范围内，防止路径穿越。
        输入：paths（待校验路径列表）、project_path（项目根目录）
        输出：校验通过后的绝对路径列表
        异常：ValidationError（路径越界）
        """
        security = self._make_security(project_path)
        validated = []
        for p in paths:
            try:
                validated.append(security.validate_path(p))
            except Exception as exc:
                raise ValidationError(str(exc)) from exc
        return validated

    async def get_status(self, project_id: str) -> dict:
        """
        获取项目 git 状态，包括当前分支、ahead/behind 数量、暂存/未暂存/未跟踪文件列表及行数统计。
        输入：project_id
        输出：{branch, ahead, behind, staged, unstaged, untracked}
        异常：ValidationError（不是 git 仓库）
        """
        project_path = self._get_project_path(project_id)

        rc, stdout, stderr = await self._run_git(
            "rev-parse", "--abbrev-ref", "HEAD", cwd=project_path
        )
        if rc != 0:
            raise ValidationError(f"不是 git 仓库: {stderr.strip()}")
        branch = stdout.strip()

        ahead = 0
        behind = 0
        rc, stdout, _ = await self._run_git(
            "rev-list", "--left-right", "--count", "@{upstream}...HEAD",
            cwd=project_path,
        )
        if rc == 0:
            parts = stdout.strip().split("\t")
            if len(parts) == 2:
                behind = int(parts[0])
                ahead = int(parts[1])

        staged = await self._name_status_list(
            project_path, ["diff", "--cached", "--name-status"]
        )
        unstaged = await self._name_status_list(
            project_path, ["diff", "--name-status"]
        )
        untracked = await self._untracked_list(project_path)

        # 补充已暂存文件的插入/删除行数
        rc_cached, stdout_cached, _ = await self._run_git(
            "diff", "--cached", "--numstat", cwd=project_path
        )
        if rc_cached == 0:
            stat_map = self._parse_numstat(stdout_cached)
            for item in staged:
                stat = stat_map.get(item["path"])
                if stat:
                    item["insertions"] = stat[0]
                    item["deletions"] = stat[1]

        # 补充未暂存文件的插入/删除行数
        rc_uncached, stdout_uncached, _ = await self._run_git(
            "diff", "--numstat", cwd=project_path
        )
        if rc_uncached == 0:
            stat_map = self._parse_numstat(stdout_uncached)
            for item in unstaged:
                stat = stat_map.get(item["path"])
                if stat:
                    item["insertions"] = stat[0]
                    item["deletions"] = stat[1]

        return {
            "branch": branch,
            "ahead": ahead,
            "behind": behind,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
        }

    def _parse_numstat(self, output: str) -> dict[str, tuple[int, int]]:
        """
        解析 git diff --numstat 输出，构建文件路径 → (插入行数, 删除行数) 的映射。
        二进制文件的行数显示为 "-"，此类文件不计入结果。
        输入：numstat 原始输出字符串
        输出：{filepath: (insertions, deletions)}
        """
        result = {}
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                ins = int(parts[0]) if parts[0] != "-" else None
                dels = int(parts[1]) if parts[1] != "-" else None
                filepath = parts[2].strip()
                if ins is not None and dels is not None:
                    result[filepath] = (ins, dels)
        return result

    async def _name_status_list(
        self, cwd: str, args: list[str]
    ) -> list[dict]:
        """
        执行 git diff --name-status 类命令，解析结果为文件状态列表。
        输入：cwd（工作目录）、args（完整 git 参数列表）
        输出：[{path: str, status: str}]，失败时返回空列表
        """
        rc, stdout, _ = await self._run_git(*args, cwd=cwd)
        if rc != 0:
            return []
        result = []
        for line in stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            code = parts[0][0]
            path = parts[-1]
            result.append({"path": path, "status": self._map_status(code)})
        return result

    async def _untracked_list(self, cwd: str) -> list[dict]:
        """
        获取未跟踪文件列表（排除 .gitignore 中的文件）。
        输入：cwd（工作目录）
        输出：[{path: str, status: "U"}]，失败时返回空列表
        """
        rc, stdout, _ = await self._run_git(
            "ls-files", "--others", "--exclude-standard", cwd=cwd
        )
        if rc != 0:
            return []
        return [
            {"path": line, "status": "U"}
            for line in stdout.splitlines()
            if line
        ]

    @staticmethod
    def _map_status(code: str) -> str:
        """
        将 git diff --name-status 的单字母状态码映射为统一标识。
        C（复制）归为 A（新增），其余未知状态默认为 M（修改）。
        输入：code（单字母状态码）
        输出：统一状态字符串（M/A/D/R）
        """
        return {"M": "M", "A": "A", "D": "D", "R": "R", "C": "A"}.get(code, "M")

    async def stage_files(self, project_id: str, paths: list[str]) -> dict:
        """
        将指定文件添加到暂存区（git add）。
        输入：project_id、paths（相对或绝对路径列表）
        输出：{success: bool, error: str|None}
        异常：ValidationError（路径越界 / git add 失败）
        """
        project_path = self._get_project_path(project_id)
        validated = self._validate_paths(paths, project_path)
        rel_paths = [os.path.relpath(p, os.path.realpath(project_path)) for p in validated]
        rc, _, stderr = await self._run_git("add", *rel_paths, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git add 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def unstage_files(self, project_id: str, paths: list[str]) -> dict:
        """
        将指定文件从暂存区移除（git reset HEAD）。
        输入：project_id、paths（相对或绝对路径列表）
        输出：{success: bool, error: str|None}
        异常：ValidationError（路径越界 / git reset 失败）
        """
        project_path = self._get_project_path(project_id)
        validated = self._validate_paths(paths, project_path)
        rel_paths = [os.path.relpath(p, os.path.realpath(project_path)) for p in validated]
        rc, _, stderr = await self._run_git("reset", "HEAD", "--", *rel_paths, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git reset 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def commit(self, project_id: str, message: str, amend: bool = False) -> dict:
        """
        提交暂存区内容（git commit）。
        输入：project_id、message（提交信息）、amend（是否修改上一条提交，默认 False）
        输出：{success: bool, error: str|None}
        异常：ValidationError（git commit 失败）
        """
        project_path = self._get_project_path(project_id)
        args = ["commit", "-m", message]
        if amend:
            args.append("--amend")
        rc, _, stderr = await self._run_git(*args, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git commit 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def fetch(self, project_id: str) -> dict:
        """
        从远端抓取最新引用（git fetch），不合并。
        输入：project_id
        输出：{success: bool, error: str|None}
        """
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("fetch", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip() or stdout.strip()}
        return {"success": True, "error": None}

    async def list_branches(self, project_id: str) -> dict:
        """
        列出本地和远端分支，标注当前分支。
        输入：project_id
        输出：{branches: [{name, is_current, is_remote}], current: str}
        异常：ValidationError（git branch 失败）
        """
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("branch", "--no-color", cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git branch 失败: {stderr.strip()}")

        rc_head, stdout_head, _ = await self._run_git(
            "rev-parse", "--abbrev-ref", "HEAD", cwd=project_path
        )
        current = stdout_head.strip() if rc_head == 0 else ""

        branches = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            is_current = line.startswith("*")
            name = line.lstrip("* ").strip()
            branches.append({
                "name": name,
                "is_current": is_current,
                "is_remote": False,
            })

        # 追加远端分支（去重，已存在本地同名分支的跳过）
        rc_r, stdout_r, _ = await self._run_git("branch", "-r", "--no-color", cwd=project_path)
        if rc_r == 0:
            seen = {b["name"] for b in branches}
            for line in stdout_r.splitlines():
                line = line.strip()
                if not line or " -> " in line:
                    continue
                short = line.strip().removeprefix("origin/").strip()
                if short and short not in seen:
                    branches.append({
                        "name": short,
                        "is_current": short == current,
                        "is_remote": True,
                    })
                    seen.add(short)

        return {"branches": branches, "current": current}

    async def create_branch(self, project_id: str, name: str, checkout: bool = True) -> dict:
        """
        创建新分支，可选是否立即切换到该分支。
        输入：project_id、name（分支名）、checkout（是否切换，默认 True）
        输出：{success: bool, error: str|None}
        异常：ValidationError（创建失败）
        """
        project_path = self._get_project_path(project_id)
        if checkout:
            rc, _, stderr = await self._run_git("checkout", "-b", name, cwd=project_path)
        else:
            rc, _, stderr = await self._run_git("branch", name, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"创建分支失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def delete_branch(self, project_id: str, name: str, force: bool = False) -> dict:
        """
        删除本地分支。
        输入：project_id、name（分支名）、force（强制删除未合并分支，默认 False）
        输出：{success: bool, error: str|None}
        异常：ValidationError（删除失败）
        """
        project_path = self._get_project_path(project_id)
        flag = "-D" if force else "-d"
        rc, _, stderr = await self._run_git("branch", flag, name, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"删除分支失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def switch_branch(self, project_id: str, name: str) -> dict:
        """
        切换到指定分支（git checkout）。
        输入：project_id、name（目标分支名）
        输出：{success: bool, error: str|None}
        异常：ValidationError（切换失败，如有未提交变更）
        """
        project_path = self._get_project_path(project_id)
        rc, _, stderr = await self._run_git("checkout", name, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"切换分支失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def log(self, project_id: str, max_count: int = 50) -> dict:
        """
        获取提交历史记录。
        输入：project_id、max_count（最大条数，默认 50）
        输出：{commits: [{hash, short_hash, author, date, message}]}
        异常：ValidationError（git log 失败）
        """
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git(
            "log", f"--max-count={max_count}",
            "--pretty=format:%x01%H%x00%h%x00%an%x00%ai%x00%s",
            cwd=project_path,
        )
        if rc != 0:
            raise ValidationError(f"git log 失败: {stderr.strip()}")

        commits = []
        raw = stdout.strip()
        if not raw:
            return {"commits": commits}

        # 使用 \x01 分隔各条提交，\x00 分隔字段
        entries = raw.split("\x01")
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split("\x00", 4)
            if len(parts) < 5:
                continue
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "author": parts[2],
                "date": parts[3],
                "message": parts[4],
            })
        return {"commits": commits}

    async def stage_all(self, project_id: str) -> dict:
        """
        暂存全部变更（git add -A），包括新增、修改、删除。
        输入：project_id
        输出：{success: bool, error: str|None}
        异常：ValidationError（失败）
        """
        project_path = self._get_project_path(project_id)
        rc, _, stderr = await self._run_git("add", "-A", cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git add -A 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def unstage_all(self, project_id: str) -> dict:
        """
        取消暂存所有文件（git reset HEAD）。
        输入：project_id
        输出：{success: bool, error: str|None}
        异常：ValidationError（失败）
        """
        project_path = self._get_project_path(project_id)
        rc, _, stderr = await self._run_git("reset", "HEAD", cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git reset HEAD 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def discard_all(self, project_id: str) -> dict:
        """
        丢弃所有本地变更，包括未跟踪文件（git checkout -- . + git clean -fd）。
        此操作不可逆，慎用。
        输入：project_id
        输出：{success: bool, error: str|None}
        异常：ValidationError（两条命令均失败时）
        """
        project_path = self._get_project_path(project_id)
        rc1, _, _ = await self._run_git("checkout", "--", ".", cwd=project_path)
        rc2, _, _ = await self._run_git("clean", "-fd", cwd=project_path)
        if rc1 != 0 and rc2 != 0:
            raise ValidationError("丢弃所有变更失败")
        return {"success": True, "error": None}

    async def push(self, project_id: str) -> dict:
        """
        将本地提交推送到远端（git push）。
        输入：project_id
        输出：{success: bool, error: str|None}
        """
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("push", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip() or stdout.strip()}
        return {"success": True, "error": None}

    async def pull(self, project_id: str) -> dict:
        """
        从远端拉取并合并（git pull）。
        输入：project_id
        输出：{success: bool, error: str|None, output: str|None}（output 为 git 输出信息）
        """
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("pull", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip() or stdout.strip()}
        output = stdout.strip()
        return {"success": True, "error": None, "output": output if output else None}

    async def stash(self, project_id: str, action: str = "push") -> dict:
        """
        操作 git stash：push（保存工作区）或 pop（恢复最近一条 stash）。
        输入：project_id、action（"push" 或 "pop"，默认 "push"）
        输出：{success: bool, error: str|None}
        """
        project_path = self._get_project_path(project_id)
        if action == "pop":
            rc, _, stderr = await self._run_git("stash", "pop", cwd=project_path)
        else:
            rc, _, stderr = await self._run_git("stash", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip()}
        return {"success": True, "error": None}

    async def discard_changes(self, project_id: str, paths: list[str]) -> dict:
        """
        丢弃指定文件的本地变更：
        - 已跟踪文件：git checkout -- <path>
        - 未跟踪文件（新建但未 add）：直接删除
        输入：project_id、paths（相对或绝对路径列表）
        输出：{success: bool, error: str|None}
        异常：ValidationError（路径越界 / git checkout 失败）
        """
        project_path = self._get_project_path(project_id)
        validated = self._validate_paths(paths, project_path)
        rel_paths = [os.path.relpath(p, os.path.realpath(project_path)) for p in validated]

        status_data = await self.get_status(project_id)
        untracked_paths = {item["path"] for item in status_data.get("untracked", [])}

        tracked = []
        to_delete = []
        for rp in rel_paths:
            if rp in untracked_paths:
                to_delete.append(rp)
            else:
                tracked.append(rp)

        if tracked:
            rc, _, stderr = await self._run_git("checkout", "--", *tracked, cwd=project_path)
            if rc != 0:
                raise ValidationError(f"git checkout 失败: {stderr.strip()}")

        # 未跟踪文件直接删除，忽略 OSError（文件不存在等情况）
        for rp in to_delete:
            abs_path = os.path.join(project_path, rp)
            with contextlib.suppress(OSError):
                os.remove(abs_path)

        return {"success": True, "error": None}


git_service = GitService()
