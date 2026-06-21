import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.execution.context_manager import LoopContext
from app.execution.models import LoopStep, StepStatus
from app.execution.plan_file_sync import PlanFileSync
from app.llm.base import LLMToolCall
from app.tools.edit_tool import EditTool
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

READ_ONLY_TOOL_NAMES = frozenset({"grep", "glob", "session_recall"})
READ_ONLY_FILE_ACTIONS = frozenset({"read", "search", "list"})
MAX_READ_ONLY_CALLS_PER_BATCH = 4


class ToolCallExecutor:
    """Execute model tool calls and project the result back into loop context."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        emit: Callable[[str, dict], Awaitable[None]],
    ):
        self.tool_registry = tool_registry
        self.emit = emit

    def _is_read_only_call(self, tool_call: LLMToolCall) -> bool:
        if tool_call.name in READ_ONLY_TOOL_NAMES:
            return True
        if tool_call.name == "file":
            action = tool_call.arguments.get("action", "")
            return action in READ_ONLY_FILE_ACTIONS
        return False

    def prepare_read_only_batch(
        self, tool_calls: list[LLMToolCall]
    ) -> list[LLMToolCall]:
        deduped: list[LLMToolCall] = []
        seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()

        for tool_call in tool_calls:
            signature = self._read_only_signature(tool_call)
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(tool_call)
            if len(deduped) >= MAX_READ_ONLY_CALLS_PER_BATCH:
                break

        return deduped

    def _read_only_signature(
        self, tool_call: LLMToolCall
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        normalized_args = tuple(
            sorted(
                (str(key), repr(value)) for key, value in tool_call.arguments.items()
            )
        )
        return tool_call.name, normalized_args

    async def execute(
        self,
        tool_call: LLMToolCall,
        context: LoopContext,
        step_number: int,
    ) -> LoopStep:
        from app.tools.plan_tool import PlanTool

        step = LoopStep(
            id=f"step-{uuid.uuid4().hex[:8]}",
            step_number=step_number,
            tool=tool_call.name,
            tool_call_id=tool_call.id,
            args=tool_call.arguments,
            status=StepStatus.RUNNING,
        )

        start_time = time.time()

        await self.emit(
            "tool:start",
            {
                "tool_name": tool_call.name,
                "arguments": tool_call.arguments,
                "tool_call_id": tool_call.id,
                "step_number": step_number,
            },
        )

        try:
            tool = self.tool_registry.get(tool_call.name)
            if not tool:
                raise ValueError(f"工具不存在: {tool_call.name}")

            if tool_call.arguments.get("__reflexion_parse_error"):
                error_msg = tool_call.arguments["__reflexion_parse_error"]
                raw = tool_call.arguments.get("__reflexion_raw_arguments", "")
                if raw:
                    error_msg += f" Raw fragment received: {raw}"
                step.status = StepStatus.FAILED
                step.error = error_msg
                step.duration = 0.0
                context.update_history(tool_call, error_msg)
                context.add_message(
                    "tool", content=error_msg, tool_call_id=tool_call.id
                )
                return step

            missing = self._validate_required_args(tool, tool_call.arguments)
            if missing:
                raise ValueError(f"缺少必需参数: {', '.join(missing)}")

            result = await tool.execute(tool_call.arguments)

            if result.approval_required:
                approval = result.approval
                if approval is None:
                    step.status = StepStatus.FAILED
                    step.error = "approval_required result missing approval metadata"
                    step.duration = time.time() - start_time
                    context.update_history(tool_call, step.error)
                    context.add_message(
                        "tool",
                        content=step.error,
                        tool_call_id=tool_call.id,
                    )
                    return step

                step.status = StepStatus.WAITING_FOR_APPROVAL
                step.approval_id = approval.approval_id
                step.output = approval.summary
                step.duration = time.time() - start_time

                await self.emit(
                    "approval:required",
                    {
                        "tool_name": tool_call.name,
                        "arguments": tool_call.arguments,
                        "tool_call_id": tool_call.id,
                        "approval_id": approval.approval_id,
                        "step_number": step_number,
                        "approval": approval.model_dump(),
                    },
                )

                logger.info("工具 %s 等待审批", tool_call.name)
                return step

            step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
            step.output = result.output
            step.error = result.error
            step.duration = time.time() - start_time

            tool_output = result.output or result.error or ""
            if not result.success and result.data and "return_code" in result.data:
                rc_info = f"\n[进程返回码: {result.data['return_code']}]"
                if not result.error:
                    tool_output = tool_output + rc_info
                else:
                    tool_output = (
                        tool_output + rc_info
                        if not tool_output.endswith(rc_info)
                        else tool_output
                    )
            _VISIBLE_DATA_KEYS = {
                "content",
                "result",
                "path",
                "url",
                "title",
                "tab_id",
                "tabs",
                "active_tab_id",
                "width",
                "height",
            }
            _MAX_CONTENT_LEN = 8000
            if result.data:
                visible = {
                    k: v for k, v in result.data.items() if k in _VISIBLE_DATA_KEYS
                }
                if (
                    "content" in visible
                    and isinstance(visible["content"], str)
                    and len(visible["content"]) > _MAX_CONTENT_LEN
                ):
                    visible["content"] = (
                        visible["content"][:_MAX_CONTENT_LEN] + "\n...[truncated]"
                    )
                if visible:
                    tool_output = (
                        tool_output + "\n" + json.dumps(visible, ensure_ascii=False)
                    )
            context.update_history(tool_call, tool_output)
            context.add_message(
                "tool",
                content=tool_output,
                tool_call_id=tool_call.id,
            )

            await self.emit(
                "tool:result",
                {
                    "tool_name": tool_call.name,
                    "tool_call_id": tool_call.id,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "duration": step.duration,
                    **(result.data or {}),
                },
            )

            if isinstance(tool, PlanTool) and tool.get_plan() is not None:
                context.plan = tool.get_plan()
                # Persist plan to disk immediately after each plan tool call.
                # This ensures plan survives crashes, cancellations, and plan-mode runs.
                if not context.plan_file_path:
                    plan_sync = PlanFileSync()
                    context.plan_file_path = plan_sync.write(
                        context.plan,
                        session_id=context.session_id,
                        project_path=context.project_path,
                    )
                else:
                    plan_sync = PlanFileSync()
                    plan_sync.sync(
                        context.plan,
                        context.plan_file_path,
                        project_path=context.project_path,
                    )
                await self.emit("plan:updated", context.plan.to_dict())

            # Refresh memory-related system_sections after editing .reflexion/*.md files.
            # Without this, the LLM won't see its own memory changes until the next run.
            if isinstance(tool, EditTool) and result.success:
                edited_path = args.get("path", "")
                if ".reflexion/" in edited_path and edited_path.endswith(".md"):
                    await self._refresh_memory_sections(context)

            logger.info(
                "工具 %s 执行%s",
                tool_call.name,
                "成功" if result.success else "失败",
            )

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.duration = time.time() - start_time
            logger.error("工具执行异常: %s", e)

            context.update_history(tool_call, str(e))
            context.add_message(
                "tool",
                content=str(e),
                tool_call_id=tool_call.id,
            )

        return step

    @staticmethod
    def _validate_required_args(tool, arguments: dict[str, Any]) -> list[str]:
        schema = tool.get_schema()
        required = schema.get("parameters", {}).get("required", [])
        if not required:
            return []
        missing = []
        for key in required:
            if key not in arguments or arguments[key] is None:
                missing.append(key)
        return missing

    @staticmethod
    async def _refresh_memory_sections(context: LoopContext) -> None:
        """Re-read .reflexion/*.md from disk and rebuild memory-related system_sections.

        Called after EditTool writes to .reflexion/*.md so the LLM sees its own
        memory changes in the very next turn, without waiting for a new run.
        """
        if not context.project_path:
            return

        from pathlib import Path

        reflexion_dir = Path(context.project_path) / ".reflexion"
        refreshed_sections: list[dict[str, str]] = []
        for filename, title in [("USER.md", "USER"), ("MEMORY.md", "MEMORY")]:
            md_path = reflexion_dir / filename
            if md_path.exists() and md_path.is_file():
                content = md_path.read_text(encoding="utf-8").strip()
                if content:
                    refreshed_sections.append({"title": title, "content": content})

        # Replace only memory-related sections, preserve all others
        memory_titles = {"USER", "MEMORY"}
        other_sections = [
            s for s in context.system_sections if s.get("title", "") not in memory_titles
        ]
        context.system_sections = other_sections + refreshed_sections
