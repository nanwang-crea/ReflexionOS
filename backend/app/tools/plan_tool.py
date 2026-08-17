# Plan 工具：供 Agent 管理多步骤任务的执行计划（TODO List）。
# Agent 每次调用都要传入完整的步骤列表（增量更新靠对比新旧状态实现），
# 工具内部维护当前 Plan 对象并自动持久化到磁盘文件（PlanFileSync），
# 支持会话意外中断后从磁盘恢复未完成的计划（try_recover）。
import logging
from typing import Any

from app.execution.plan_engine import Plan, PlanStep
from app.execution.plan_file_sync import PlanFileSync
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PlanTool(BaseTool):
    """任务计划管理工具。

    能力边界：不执行任何实际任务，只负责维护一份步骤列表的状态机
    （pending/in_progress/completed/blocked）及其落盘持久化，供 Agent
    追踪多步骤任务的进度。
    """

    def __init__(self, file_sync: PlanFileSync | None = None):
        """初始化 PlanTool。

        入参：file_sync (PlanFileSync | None) - 计划文件持久化组件，不传则使用默认实现。
        功能：初始化内部状态——当前计划(_plan)、计划文件路径(_file_path)、
        项目路径与会话 ID（用于定位持久化文件位置）均置空，等待 set_context 设置。
        """
        self._plan: Plan | None = None
        self._file_sync = file_sync or PlanFileSync()
        self._file_path: str | None = None
        self._project_path: str | None = None
        self._session_id: str | None = None

    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        # 面向 LLM 的工具功能说明，保留英文原文：强调每次要传完整步骤列表、同一时刻只保留一个 in_progress
        return (
            "Manage execution plans for multi-step tasks. "
            "Send the FULL step list every call — keep completed steps with status=completed and findings. "
            "Keep exactly one step in_progress at a time. "
            "Skip for simple tasks that need fewer than 3 steps."
        )

    def get_schema(self) -> dict[str, Any]:
        """返回本工具的 JSON Schema 定义（供 LLM 函数调用使用）。

        入参：无
        功能：声明 plan 工具的参数结构——goal（首次调用必填，整体目标）、
        steps（必填，完整步骤数组，每项含 content/status/findings）。
        出参：dict - OpenAI/Anthropic 兼容的 tool schema 字典。
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Overall goal (required on first call, optional after)",
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "What needs to be done",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed", "blocked"],
                                    "description": "Step status",
                                },
                                "findings": {
                                    "type": "string",
                                    "description": "Brief result summary when completed (optional)",
                                },
                            },
                            "required": ["content", "status"],
                        },
                        "minItems": 1,
                        "description": "The complete step list. Send ALL steps every time.",
                    },
                },
                "required": ["steps"],
            },
        }

    def set_plan(self, plan: Plan | None):
        """直接设置当前计划对象（供外部恢复/重置场景调用）。

        入参：plan (Plan | None) - 要设置的计划对象，传 None 表示清空当前计划。
        出参：无。
        """
        self._plan = plan

    def get_plan(self) -> Plan | None:
        """获取当前计划对象。

        入参：无。
        出参：Plan | None - 当前维护的计划，尚未创建则返回 None。
        """
        return self._plan

    def set_context(self, project_path: str, session_id: str):
        """Set project and session context for file operations.

        入参：project_path (str) - 当前项目根路径；session_id (str) - 当前会话 ID。
        功能：设置持久化所需的上下文，供后续 _persist/try_recover 定位计划文件位置。
        出参：无。
        """
        self._project_path = project_path
        self._session_id = session_id

    def try_recover(self, max_age_hours: int = 24) -> Plan | None:
        """Try to recover an existing plan from disk. Returns the plan if found.

        入参：max_age_hours (int) - 只恢复该小时数以内写入的计划文件，超时视为过期不恢复。
        功能：依据当前 project_path + session_id 在磁盘上查找可恢复的计划文件；
        找到则读取并赋值给 self._plan / self._file_path。
        出参：Plan | None - 恢复成功返回计划对象，未找到或过期返回 None。
        """
        if not self._session_id:
            return None

        path = self._file_sync.find_recovery_plan(
            project_path=self._project_path,
            session_id=self._session_id,
            max_age_hours=max_age_hours,
        )
        if path:
            plan = self._file_sync.read(path)
            if plan:
                self._plan = plan
                self._file_path = path
                logger.info("恢复计划: %s", plan.goal[:80])
                return plan
        return None

    def discard(self):
        """Discard current plan and delete its file.

        入参：无。
        功能：若存在已持久化的计划文件则删除，并清空内存中的计划状态。
        出参：无。
        """
        if self._file_path:
            self._file_sync.delete(self._file_path, project_path=self._project_path)
            logger.info("丢弃计划: %s", self._file_path)
        self._plan = None
        self._file_path = None

    def _persist(self):
        """Persist current plan to disk.

        入参：无。
        功能：若尚无计划或无 session_id 则跳过；已有文件路径则同步覆写，
        否则首次调用 file_sync.write 创建计划文件并记录其路径。
        出参：无。
        """
        if not self._plan or not self._session_id:
            return

        if self._file_path:
            self._file_sync.sync(self._plan, self._file_path, project_path=self._project_path)
        else:
            self._file_path = self._file_sync.write(
                self._plan,
                session_id=self._session_id,
                project_path=self._project_path,
            )

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        """更新（或首次创建）任务执行计划。

        入参：args (dict) - 包含 steps（必填，完整步骤数组）、goal（首次调用必填，整体目标）。
        功能：
          1. 解析并校验 steps 格式（_parse_steps）；
          2. 若当前无计划（首次调用）：要求提供 goal，创建新 Plan；
          3. 若已有计划：调用 plan.replace_from 用新步骤列表整体替换，计算出
             刚完成/刚开始的步骤（用于提示 Agent 关注点变化）；
          4. 统计各状态步骤数量，拼装带图标的进度文本（○/►/✓/✗）；
          5. 自动持久化到磁盘（_persist）。
        出参：ToolResult - success + 格式化的进度文本(output) + 结构化统计数据(data)。
        """
        steps_raw = args.get("steps", [])
        goal = args.get("goal", "")

        steps_result = self._parse_steps(steps_raw)
        if isinstance(steps_result, str):
            return ToolResult(success=False, error=steps_result)
        steps = steps_result

        if not steps:
            return ToolResult(success=False, error="steps cannot be empty")

        is_new = self._plan is None
        if is_new:
            if not goal:
                return ToolResult(success=False, error="Goal is required on first call")
            self._plan = Plan(goal=goal, steps=steps)
            changes = {"just_completed": [], "just_started": None}
            if self._plan.current_step:
                changes["just_started"] = self._plan.current_step.content
        else:
            try:
                changes = self._plan.replace_from(steps, goal=goal or None)
            except ValueError as e:
                return ToolResult(success=False, error=str(e))

        plan = self._plan
        current = plan.current_step
        completed = sum(1 for s in plan.steps if s.status == "completed")
        in_prog = sum(1 for s in plan.steps if s.status == "in_progress")
        pending = sum(1 for s in plan.steps if s.status == "pending")
        blocked = sum(1 for s in plan.steps if s.status == "blocked")

        output_parts = [
            f"Plan updated ({completed}/{len(plan.steps)} done). "
            f"{pending} pending, {in_prog} in_progress, {completed} completed, {blocked} blocked.",
        ]
        for s in plan.steps:
            mark = {"pending": "○", "in_progress": "►", "completed": "✓", "blocked": "✗"}[s.status]
            output_parts.append(f"  {mark} {s.content}")
            if s.status == "completed" and s.findings:
                output_parts.append(f"    → {s.findings}")
        if current:
            output_parts.append(f"\n[NOW] Work on: {current.content}")
            output_parts.append("Focus entirely on this step. When done, call plan to mark it completed and start the next step.")
        elif plan.is_complete:
            output_parts.append("\nAll steps completed. Provide a summary to the user.")

        logger.info("Plan updated: %s (%d/%d done)", plan.goal, completed, len(plan.steps))

        # Auto-persist after update
        self._persist()

        return ToolResult(
            success=True,
            output="\n".join(output_parts),
            data={
                "is_new": is_new,
                "just_completed": changes.get("just_completed", []),
                "just_started": changes.get("just_started"),
                "completed": completed,
                "total": len(plan.steps),
                **plan.to_dict(),
            },
        )

    def _parse_steps(self, steps_raw: Any) -> list[PlanStep] | str:
        """校验并解析原始 steps 参数为 PlanStep 对象列表。

        入参：steps_raw (Any) - execute 传入的原始 steps 值，期望是对象数组。
        功能：逐项校验类型合法性——必须是 list；每项必须是 dict 且含非空 content、
        合法的 status（pending/in_progress/completed/blocked 之一）；findings 缺省为空字符串，
        非字符串时强制转字符串。任一校验失败立即返回错误提示字符串。
        出参：list[PlanStep] | str - 校验通过返回 PlanStep 列表，失败返回错误信息字符串。
        """
        if not isinstance(steps_raw, list):
            return "steps must be an array"
        steps: list[PlanStep] = []
        for item in steps_raw:
            if not isinstance(item, dict):
                return "Each step must be an object with content and status"
            content = item.get("content", "")
            if not isinstance(content, str) or not content.strip():
                return "Each step requires a non-empty content"
            status = item.get("status", "")
            valid = {"pending", "in_progress", "completed", "blocked"}
            if status not in valid:
                return f"Invalid status '{status}', must be one of {valid}"
            findings = item.get("findings", "")
            if not isinstance(findings, str):
                findings = str(findings)
            steps.append(PlanStep(content=content.strip(), status=status, findings=findings))
        return steps
