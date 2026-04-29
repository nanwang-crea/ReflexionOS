import json
import logging
from typing import Any

from app.execution.plan_engine import Plan, PlanStep
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PlanTool(BaseTool):
    """执行计划管理工具 — 仅复杂任务需要"""

    def __init__(self):
        self._plan: Plan | None = None

    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        return "管理执行计划：创建、完成步骤、阻塞、调整（仅复杂任务使用）"

    def get_schema(self) -> dict[str, Any]:
        return self._build_schema([
            self._create_action_schema(),
            self._step_done_action_schema(),
            self._block_action_schema(),
            self._adjust_action_schema(),
        ])

    def get_create_schema(self) -> dict[str, Any]:
        return self._build_schema(
            [self._create_action_schema()],
            description="创建执行计划（仅任务开始前使用）",
        )

    def get_progress_schema(self) -> dict[str, Any]:
        return self._build_schema(
            [
                self._step_done_action_schema(),
                self._block_action_schema(),
                self._adjust_action_schema(),
            ],
            description="更新已有执行计划的步骤状态、阻塞原因或剩余步骤",
        )

    def _build_schema(
        self,
        action_schemas: list[dict[str, Any]],
        *,
        description: str | None = None,
    ) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": description or self.description,
            "parameters": {
                "type": "object",
                "oneOf": action_schemas,
            },
        }

    def _create_action_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "title": "create",
            "description": "创建执行计划（任务开始时调用一次）",
            "additionalProperties": False,
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create"],
                    "description": "固定为 create",
                },
                "goal": {
                    "type": "string",
                    "description": "总目标描述",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 12,
                    "description": "高层步骤描述列表",
                },
            },
            "required": ["action", "goal", "steps"],
        }

    def _step_done_action_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "title": "step_done",
            "description": "当前步骤完成，记录发现并推进到下一步",
            "additionalProperties": False,
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["step_done"],
                    "description": "固定为 step_done",
                },
                "findings": {
                    "type": "string",
                    "description": "本步骤获取到的关键信息，将传递给下一步",
                },
            },
            "required": ["action", "findings"],
        }

    def _block_action_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "title": "block",
            "description": "当前步骤阻塞",
            "additionalProperties": False,
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["block"],
                    "description": "固定为 block",
                },
                "reason": {
                    "type": "string",
                    "description": "阻塞原因",
                },
            },
            "required": ["action", "reason"],
        }

    def _adjust_action_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "title": "adjust",
            "description": "调整剩余步骤（发现计划需要修改时使用）",
            "additionalProperties": False,
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["adjust"],
                    "description": "固定为 adjust",
                },
                "remaining_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "替换当前步骤之后的所有待做步骤",
                },
            },
            "required": ["action", "remaining_steps"],
        }

    def set_plan(self, plan: Plan | None):
        self._plan = plan

    def get_plan(self) -> Plan | None:
        return self._plan

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        action = args.get("action")

        if action == "create":
            return self._create(args)
        elif action == "step_done":
            return self._step_done(args)
        elif action == "block":
            return self._block(args)
        elif action == "adjust":
            return self._adjust(args)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")

    def _create(self, args: dict[str, Any]) -> ToolResult:
        goal = args.get("goal", "")
        steps_raw = args.get("steps", [])
        steps = self._normalize_steps(steps_raw)

        if not goal or not steps:
            return ToolResult(success=False, error="需要 goal 和 steps 参数")
        if isinstance(steps, str):
            return ToolResult(success=False, error=steps)

        self._plan = Plan(
            goal=goal,
            steps=[PlanStep(id=i + 1, description=desc) for i, desc in enumerate(steps)],
        )
        self._plan.start()

        logger.info("创建执行计划: %s, %d 步骤", goal, len(self._plan.steps))
        return ToolResult(
            success=True,
            output=f"计划已创建: {goal}，共 {len(self._plan.steps)} 步",
            data=self._plan.to_dict(),
        )

    def _normalize_steps(self, steps_raw: Any) -> list[str] | str:
        if isinstance(steps_raw, str):
            stripped = steps_raw.strip()
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return "steps 必须是字符串数组"
            steps_raw = decoded

        if not isinstance(steps_raw, list):
            return "steps 必须是字符串数组"

        steps: list[str] = []
        for step in steps_raw:
            if not isinstance(step, str):
                return "steps 必须是字符串数组"
            description = step.strip()
            if description:
                steps.append(description)

        if len(steps) > 12:
            return "steps 最多只能包含 12 个高层步骤"

        return steps

    def _step_done(self, args: dict[str, Any]) -> ToolResult:
        if not self._plan:
            return ToolResult(success=False, error="尚未创建计划")
        if not self._plan.current_step:
            return ToolResult(success=False, error="没有正在执行的步骤")

        findings = args.get("findings", "")
        step_desc = self._plan.current_step.description
        self._plan.advance(findings)

        if self._plan.current_step:
            logger.info(
                "步骤完成: %s → 推进到: %s",
                step_desc,
                self._plan.current_step.description,
            )
            return ToolResult(
                success=True,
                output=f"步骤完成: {step_desc}，推进到: {self._plan.current_step.description}",
                data=self._plan.to_dict(),
            )
        else:
            logger.info("所有计划步骤已完成")
            return ToolResult(
                success=True,
                output="所有计划步骤已完成",
                data=self._plan.to_dict(),
            )

    def _block(self, args: dict[str, Any]) -> ToolResult:
        if not self._plan or not self._plan.current_step:
            return ToolResult(success=False, error="没有正在执行的步骤")

        reason = args.get("reason", "")
        step_desc = self._plan.current_step.description
        self._plan.block(reason)

        logger.warning("步骤阻塞: %s, 原因: %s", step_desc, reason)
        return ToolResult(
            success=True,
            output=f"步骤阻塞: {step_desc}",
            data=self._plan.to_dict(),
        )

    def _adjust(self, args: dict[str, Any]) -> ToolResult:
        if not self._plan:
            return ToolResult(success=False, error="尚未创建计划")

        remaining = args.get("remaining_steps", [])
        if not remaining:
            return ToolResult(success=False, error="需要 remaining_steps 参数")

        self._plan.adjust_remaining(remaining)

        logger.info("调整计划，剩余 %d 步骤", len(remaining))
        return ToolResult(
            success=True,
            output=f"计划已调整，剩余 {len(remaining)} 步骤",
            data=self._plan.to_dict(),
        )
