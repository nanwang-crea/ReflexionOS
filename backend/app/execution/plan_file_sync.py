"""
文件功能：执行计划（Plan）与本地 Markdown 文件之间的双向同步
文件描述：负责把内存中的 Plan 对象落盘到 `.reflexion/plans/*.md`，以及从磁盘读回；
         提供原子写入、路径安全校验（防止越权访问计划目录之外的路径）、计划文件删除，
         以及进程重启后寻找可恢复的未完成计划文件的能力。
核心逻辑：写入统一走 _atomic_write（临时文件 + os.replace 原子替换，避免写入中途被
         读到半截内容）；所有对外暴露路径的操作（sync/delete）都先经过
         _validate_plan_path 校验，确保解析后的真实路径落在计划根目录内；
         find_recovery_plan 优先按 session_id 精确匹配，找不到再回退扫描目录下
         最近修改且未完成的计划文件，兼容旧会话恢复场景。
"""

import contextlib
import logging
import os
import tempfile
import time

from app.execution.plan_engine import Plan

logger = logging.getLogger(__name__)


class PlanFileSync:
    """在 Plan 对象与 .reflexion/plans/ 目录下的 Markdown 文件之间做双向同步"""

    def __init__(self, base_dir: str | None = None):
        """
        函数名：__init__
        入参：
          - base_dir (str | None)：计划文件存放的根目录，显式指定后所有操作固定使用该目录；
                                    为 None 时按 project_path 动态解析
        功能：初始化同步器，记录固定根目录（如果有）
        运行逻辑：直接保存 base_dir，不做路径存在性校验（延迟到实际读写时创建）
        出参：无
        """
        self.base_dir = base_dir

    def _resolve_base_dir(self, project_path: str | None = None) -> str:
        """
        函数名：_resolve_base_dir
        入参：
          - project_path (str | None)：项目根目录路径，为 None 时使用当前工作目录
        功能：解析出计划文件应该存放的根目录
        运行逻辑：若构造时已指定 self.base_dir 则直接返回；否则以 project_path（或
                 os.getcwd()）为基准，拼接固定的 ".reflexion/plans" 子目录
        出参：str - 计划文件根目录的路径
        """
        if self.base_dir:
            return self.base_dir
        root = project_path or os.getcwd()
        return os.path.join(root, ".reflexion", "plans")

    def write(
        self, plan: Plan, session_id: str, project_path: str | None = None
    ) -> str:
        """
        函数名：write
        入参：
          - plan (Plan)：要写入磁盘的计划对象
          - session_id (str)：会话 ID，用作计划文件名（{session_id}.md）
          - project_path (str | None)：项目根目录，用于解析计划目录位置
        功能：将计划首次写入磁盘，生成对应的 Markdown 文件
        运行逻辑：
          1. 解析计划根目录并确保目录存在（makedirs exist_ok）
          2. 按 session_id 生成文件名，拼出完整路径
          3. 将 Plan 渲染为 Markdown 文本，通过原子写入落盘
        出参：str - 写入成功后的计划文件完整路径
        """
        base = self._resolve_base_dir(project_path)
        os.makedirs(base, exist_ok=True)
        filename = f"{session_id}.md"
        path = os.path.join(base, filename)
        content = plan.render_to_markdown()
        self._atomic_write(path, content)
        logger.info("计划文件已写入: %s", path)
        return path

    def sync(self, plan: Plan, path: str, project_path: str | None = None) -> None:
        """
        函数名：sync
        入参：
          - plan (Plan)：最新的计划对象（内存中已更新的状态）
          - path (str)：要同步写入的目标文件路径（通常是 write() 返回的路径）
          - project_path (str | None)：项目根目录，用于路径安全校验
        功能：将计划的最新状态同步覆盖写入已存在的计划文件
        运行逻辑：先校验目标路径确实落在计划根目录内，再渲染为 Markdown 并原子写入覆盖
        出参：无
        """
        resolved = self._validate_plan_path(path, project_path)
        content = plan.render_to_markdown()
        self._atomic_write(resolved, content)
        logger.debug("计划文件已同步: %s", resolved)

    @staticmethod
    def _atomic_write(path: str, content: str) -> None:
        """
        函数名：_atomic_write
        入参：
          - path (str)：目标文件路径
          - content (str)：要写入的完整文本内容
        功能：原子化写入文件内容，避免并发读取时看到写入中途的半截文件
        运行逻辑：
          1. 在目标文件同目录下创建一个临时文件（tempfile.mkstemp）
          2. 把内容完整写入临时文件并关闭
          3. 用 os.replace 将临时文件原子性地改名覆盖到目标路径（同文件系统下不可能读到中间态）
          4. 任何异常发生时尝试清理临时文件（清理失败可忽略，例如已被 os.replace 取走），再重新抛出异常
        出参：无
        """
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
        """
        函数名：read
        入参：
          - path (str)：计划文件路径
        功能：从磁盘读取计划文件并解析为 Plan 对象
        运行逻辑：文件不存在时直接返回 None；否则读取全部文本内容，交给
                 Plan.parse_from_markdown 反序列化
        出参：Plan | None - 解析得到的计划对象，文件不存在时为 None
        """
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return Plan.parse_from_markdown(content)

    def _validate_plan_path(self, path: str, project_path: str | None = None) -> str:
        """
        函数名：_validate_plan_path
        入参：
          - path (str)：待校验的计划文件路径（可能来自外部调用方）
          - project_path (str | None)：项目根目录，用于解析计划根目录
        功能：校验目标路径确实落在计划根目录内，防止路径穿越访问到目录之外的文件
        运行逻辑：
          1. 解析出计划根目录，并对两者都取真实路径（os.path.realpath，解析软链接和相对路径）
          2. 校验 resolved 路径必须以 "根目录+分隔符" 为前缀，或者恰好等于根目录本身
          3. 不满足则抛出 ValueError 拒绝该路径
        出参：str - 校验通过后的真实路径（realpath 结果）
        """
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
        """
        函数名：delete
        入参：
          - path (str)：要删除的计划文件路径
          - project_path (str | None)：项目根目录，用于路径安全校验
        功能：删除指定的计划文件
        运行逻辑：先经过 _validate_plan_path 校验路径合法，文件存在时才执行删除并记录日志
        出参：无
        """
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
        """
        函数名：find_recovery_plan
        入参：
          - project_path (str | None)：项目根目录，用于解析计划目录位置
          - session_id (str | None)：优先匹配的会话 ID，提供时先尝试精确匹配该会话的计划文件
          - max_age_hours (int)：计划文件的最大有效期（小时），超过此时长视为过期不予恢复
        功能：进程重启或会话恢复时，寻找一个仍未完成、且未过期的计划文件用于续接执行
        运行逻辑：
          1. 若计划目录不存在，直接返回 None
          2. session 精确匹配：若提供了 session_id，检查对应的 {session_id}.md 是否存在、
             是否未过期；未过期且解析出的计划未完成，则直接返回该路径
          3. 回退扫描：按最后修改时间从新到旧遍历目录下所有 .md 文件（兼容没有 session_id
             或该会话没有计划文件的旧场景），跳过已过期的文件，返回第一个解析成功且未完成的计划路径
          4. 都找不到则返回 None
        出参：str | None - 可用于恢复的计划文件路径，没有可恢复计划时为 None
        """
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
