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
            "Do NOT modify the content of completed steps.\n\n"
            "## When to Use\n"
            "Use this tool proactively for:\n"
            "1. Complex multistep tasks — when a task requires 3 or more distinct steps\n"
            "2. Non-trivial tasks — tasks requiring careful planning or multiple operations\n"
            "3. After receiving new instructions — capture requirements as plan steps\n"
            "4. After completing a task — mark it completed with findings and start the next step\n\n"
            "## When NOT to Use\n"
            "Skip for simple tasks that need fewer than 3 steps or are purely conversational.\n\n"
            "## Example: Progressive Plan Updates\n"
            "User: Refactor the auth module and add tests\n"
            "Assistant creates plan:\n"
            "  steps: [\n"
            '    {content: "Analyze current auth module structure", status: "in_progress"},\n'
            '    {content: "Refactor auth module", status: "pending"},\n'
            '    {content: "Write unit tests for auth", status: "pending"},\n'
            '    {content: "Run tests and fix failures", status: "pending"}\n'
            "  ]\n"
            "Assistant analyzes the code...\n"
            "Assistant updates plan:\n"
            "  steps: [\n"
            '    {content: "Analyze current auth module structure", status: "completed", findings: "Found 3 files, token logic in auth.py:42"},\n'
            '    {content: "Refactor auth module", status: "in_progress"},\n'
            '    {content: "Write unit tests for auth", status: "pending"},\n'
            '    {content: "Run tests and fix failures", status: "pending"}\n'
            "  ]\n"
            "Assistant refactors...\n"
            "Assistant updates plan:\n"
            "  steps: [\n"
            '    {content: "Analyze current auth module structure", status: "completed", findings: "Found 3 files, token logic in auth.py:42"},\n'
            '    {content: "Refactor auth module", status: "completed", findings: "Extracted TokenService, reduced coupling"},\n'
            '    {content: "Write unit tests for auth", status: "in_progress"},\n'
            '    {content: "Run tests and fix failures", status: "pending"}\n'
            "  ]\n"
            "and so on until all steps are completed.\n\n"
            "IMPORTANT: Always use this tool to plan and track tasks throughout the conversation."
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
            output_parts.append(f"\n[NOW] Work on: {current.content}")
            output_parts.append("Focus entirely on this step. When done, call plan to mark it completed and start the next step.")
        elif plan.is_complete:
            output_parts.append("\nAll steps completed. Provide a summary to the user.")

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
