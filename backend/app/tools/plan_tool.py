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
            "Manage execution plans for multi-step tasks. "
            "Send the FULL step list every call — NEVER omit completed steps, always keep them with status=completed and findings. "
            "Keep exactly one step in_progress at a time. "
            "To mark a step done: keep it in the list with status=completed and add findings, then set the next step to in_progress. "
            "Do NOT modify the content of completed steps. "
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
                                    "description": "What needs to be done (imperative form)",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed", "blocked"],
                                    "description": "Step status",
                                },
                                "findings": {
                                    "type": "string",
                                    "description": "Brief result summary when completed (required when status=completed, keep under 100 chars)",
                                },
                            },
                            "required": ["content", "status"],
                        },
                        "minItems": 1,
                        "maxItems": 12,
                        "description": "The complete step list. Send ALL steps every time. NEVER remove completed steps — keep them with status=completed and findings filled in. To advance: mark current step completed+findings, set next step in_progress.",
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

        in_progress_count = sum(1 for s in steps if s.status == "in_progress")
        if in_progress_count > 1:
            return ToolResult(success=False, error="Only one step can be in_progress at a time")

        for s in steps:
            if s.status == "completed" and not s.findings:
                return ToolResult(
                    success=False,
                    error=f"Completed step requires findings: {s.content}",
                )

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
        pending = sum(1 for s in plan.steps if s.status == "pending")
        in_prog = sum(1 for s in plan.steps if s.status == "in_progress")
        completed = sum(1 for s in plan.steps if s.status == "completed")
        blocked = sum(1 for s in plan.steps if s.status == "blocked")

        output_parts = [
            f"Plan updated ({completed}/{len(plan.steps)} done). {pending} pending, {in_prog} in_progress, {completed} completed, {blocked} blocked.",
        ]
        for s in plan.steps:
            mark = {"pending": "○", "in_progress": "►", "completed": "✓", "blocked": "✗"}[s.status]
            output_parts.append(f"  {mark} {s.content}")
            if s.status == "completed" and s.findings:
                output_parts.append(f"    → {s.findings}")
        if current:
            output_parts.append(f"[Current] {current.content}")
            output_parts.append("Continue executing this step with your tools. Do NOT stop — the plan is not yet complete.")
        elif plan.is_complete:
            output_parts.append("All steps completed! You may now stop and provide the final answer to the user.")
        else:
            output_parts.append("Ensure you use the plan to track your progress. Proceed with the current step.")

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
        if len(steps) > 12:
            return "steps cannot exceed 12"
        return steps
