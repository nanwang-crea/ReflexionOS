import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PlanExitTool(BaseTool):
    """Request switching from plan agent to build agent after planning is complete."""

    @property
    def name(self) -> str:
        return "plan_exit"

    @property
    def description(self) -> str:
        return (
            "Request switching to execution mode after planning is complete. "
            "Call this when you have created a plan and are ready for the build agent to execute it. "
            "Do NOT call this before creating a plan with plan.create. "
            "Do NOT call this if you still have questions about the implementation."
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of the plan for the build agent",
                    },
                },
                "required": [],
            },
        }

    async def execute(self, args: dict[str, Any]) -> ToolResult:
        summary = args.get("summary", "")
        logger.info("plan_exit called: %s", summary[:100] if summary else "(no summary)")
        return ToolResult(
            success=True,
            output="Plan exit requested. Waiting for user confirmation to switch to build mode.",
            data={"plan_exit_requested": True, "summary": summary},
        )
