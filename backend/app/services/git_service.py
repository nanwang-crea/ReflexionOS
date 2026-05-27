import asyncio
import contextlib
import logging
import os

from app.errors import ValidationError
from app.security.path_security import PathSecurity
from app.services.project_service import project_service

logger = logging.getLogger(__name__)


class GitService:

    def _get_project_path(self, project_id: str) -> str:
        project = project_service.get_project_or_raise(project_id)
        return project.path

    def _make_security(self, project_path: str) -> PathSecurity:
        return PathSecurity(allowed_base_paths=[project_path], base_dir=project_path)

    async def _run_git(self, *args: str, cwd: str, timeout: float = 120) -> tuple[int, str, str]:
        try:
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
            result.kill()
            raise ValidationError(
                f"git {' '.join(args)} 超时（{timeout}s）"
            ) from None

    def _validate_paths(self, paths: list[str], project_path: str) -> list[str]:
        security = self._make_security(project_path)
        validated = []
        for p in paths:
            try:
                validated.append(security.validate_path(p))
            except Exception as exc:
                raise ValidationError(str(exc)) from exc
        return validated

    async def get_status(self, project_id: str) -> dict:
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
        return {"M": "M", "A": "A", "D": "D", "R": "R", "C": "A"}.get(code, "M")

    async def stage_files(self, project_id: str, paths: list[str]) -> dict:
        project_path = self._get_project_path(project_id)
        validated = self._validate_paths(paths, project_path)
        rel_paths = [os.path.relpath(p, os.path.realpath(project_path)) for p in validated]
        rc, _, stderr = await self._run_git("add", *rel_paths, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git add 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def unstage_files(self, project_id: str, paths: list[str]) -> dict:
        project_path = self._get_project_path(project_id)
        validated = self._validate_paths(paths, project_path)
        rel_paths = [os.path.relpath(p, os.path.realpath(project_path)) for p in validated]
        rc, _, stderr = await self._run_git("reset", "HEAD", "--", *rel_paths, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git reset 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def commit(self, project_id: str, message: str, amend: bool = False) -> dict:
        project_path = self._get_project_path(project_id)
        args = ["commit", "-m", message]
        if amend:
            args.append("--amend")
        rc, _, stderr = await self._run_git(*args, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git commit 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def fetch(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("fetch", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip() or stdout.strip()}
        return {"success": True, "error": None}

    async def list_branches(self, project_id: str) -> dict:
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
        project_path = self._get_project_path(project_id)
        if checkout:
            rc, _, stderr = await self._run_git("checkout", "-b", name, cwd=project_path)
        else:
            rc, _, stderr = await self._run_git("branch", name, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"创建分支失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def delete_branch(self, project_id: str, name: str, force: bool = False) -> dict:
        project_path = self._get_project_path(project_id)
        flag = "-D" if force else "-d"
        rc, _, stderr = await self._run_git("branch", flag, name, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"删除分支失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def switch_branch(self, project_id: str, name: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc, _, stderr = await self._run_git("checkout", name, cwd=project_path)
        if rc != 0:
            raise ValidationError(f"切换分支失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def log(self, project_id: str, max_count: int = 50) -> dict:
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
        project_path = self._get_project_path(project_id)
        rc, _, stderr = await self._run_git("add", "-A", cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git add -A 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def unstage_all(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc, _, stderr = await self._run_git("reset", "HEAD", cwd=project_path)
        if rc != 0:
            raise ValidationError(f"git reset HEAD 失败: {stderr.strip()}")
        return {"success": True, "error": None}

    async def discard_all(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc1, _, _ = await self._run_git("checkout", "--", ".", cwd=project_path)
        rc2, _, _ = await self._run_git("clean", "-fd", cwd=project_path)
        if rc1 != 0 and rc2 != 0:
            raise ValidationError("丢弃所有变更失败")
        return {"success": True, "error": None}

    async def push(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("push", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip() or stdout.strip()}
        return {"success": True, "error": None}

    async def pull(self, project_id: str) -> dict:
        project_path = self._get_project_path(project_id)
        rc, stdout, stderr = await self._run_git("pull", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip() or stdout.strip()}
        output = stdout.strip()
        return {"success": True, "error": None, "output": output if output else None}

    async def stash(self, project_id: str, action: str = "push") -> dict:
        project_path = self._get_project_path(project_id)
        if action == "pop":
            rc, _, stderr = await self._run_git("stash", "pop", cwd=project_path)
        else:
            rc, _, stderr = await self._run_git("stash", cwd=project_path)
        if rc != 0:
            return {"success": False, "error": stderr.strip()}
        return {"success": True, "error": None}

    async def discard_changes(self, project_id: str, paths: list[str]) -> dict:
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

        for rp in to_delete:
            abs_path = os.path.join(project_path, rp)
            with contextlib.suppress(OSError):
                os.remove(abs_path)

        return {"success": True, "error": None}


git_service = GitService()
