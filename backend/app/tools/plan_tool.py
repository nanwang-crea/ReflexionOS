import logging
from typing import Any

from app.execution.plan_engine import Plan, PlanStep
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PlanTool(BaseTool):

    def __init__(self):
        self._plan: Plan | None = None

    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        return (
            "Create and manage execution plans for multi-step tasks. "
            "Call once to create, then call again to update step statuses as you work. "
            "Skip for simple tasks that need fewer than 3 steps."
        )

    def get_schema(self) -> dict[str, Any]:
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
        self._plan = plan

    def get_plan(self) -> Plan | None:
        return self._plan

    async def execute(self, args: dict[str, Any]) -> ToolResult:
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
            output_parts.append(f"[Current] {current.content}")
        elif plan.is_complete:
            output_parts.append("All steps completed.")

        logger.info("Plan updated: %s (%d/%d done)", plan.goal, completed, len(plan.steps))

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
