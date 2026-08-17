"""
文件功能：单个工具调用的执行器
文件描述：负责把 LLM 发出的一次 LLMToolCall 落地为实际工具执行，并把结果归一化为
         主循环（rapid_loop.py）可以直接处理的 LoopStep（成功/失败/等待审批三种终态）。
         同时提供只读工具批次的去重与数量限制，避免 LLM 在一轮里发起过多重复的探索性调用。
核心逻辑：execute() 是单个工具调用的完整生命周期：发送 tool:start 事件 → 校验工具存在性
         和必需参数 → （若是 WorkingMemoryTool）注入依赖 → 通过 ContextVar 让工具感知当前
         call_id → 调用工具的 execute → 按返回结果分三路处理（需要审批 / 成功 / 失败），
         每一路都会更新对话历史（context.update_history / add_message）并在成功路径发送
         tool:result 事件；异常统一被捕获转为 FAILED 步骤，保证主循环不会因单个工具异常
         而整体崩溃。plan 工具的特殊之处在于：每次调用后若产出了新计划，会立即同步落盘，
         保证计划在崩溃/取消/PLAN 模式下也不丢失。
"""

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from app.execution.context_manager import LoopContext
from app.execution.models import LoopStep, StepStatus
from app.execution.plan_file_sync import PlanFileSync
from app.llm.base import LLMToolCall
from app.tools.registry import ToolRegistry
from app.tools.working_memory_tool import WorkingMemoryTool

logger = logging.getLogger(__name__)

# 当前正在执行的工具调用 ID，由 ToolCallExecutor 在每次 execute 前设置
# 供需要感知 call_id 的工具（如 DelegateTool）读取
_current_tool_call_id: ContextVar[str] = ContextVar(
    "_current_tool_call_id", default=""
)

# Read-only tools are the only ones we batch in a single planning pass. We
# cap the batch size so the agent cannot get stuck issuing an unbounded number
# of exploratory calls before it reflects on the results.
READ_ONLY_TOOL_NAMES = frozenset({"grep", "glob", "session_recall"})
READ_ONLY_FILE_ACTIONS = frozenset({"read", "search", "list"})
MAX_READ_ONLY_CALLS_PER_BATCH = 4


class ToolCallExecutor:
    """Execute model tool calls and feed the result back into loop context.

    This layer emits lifecycle events, delegates to the concrete tool, and
    normalizes success / approval / failure into a LoopStep that the main loop
    can reason about.
    """

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        emit: Callable[[str, dict], Awaitable[None]],
    ):
        """
        函数名：__init__
        入参：
          - tool_registry (ToolRegistry)：工具注册表，用于按名称查找工具实例
          - emit：事件发射回调，用于发送 tool:start/tool:result/approval:required 等事件
        功能：初始化工具调用执行器
        运行逻辑：直接保存 tool_registry 与 emit 回调引用
        出参：无
        """
        self.tool_registry = tool_registry
        self.emit = emit

    def _is_read_only_call(self, tool_call: LLMToolCall) -> bool:
        """
        函数名：_is_read_only_call
        入参：
          - tool_call (LLMToolCall)：待判断的工具调用
        功能：判断一次工具调用是否为只读调用（无副作用，可安全并行执行）
        运行逻辑：工具名在 READ_ONLY_TOOL_NAMES 白名单中直接判定为只读；若是 file 工具，
                 则进一步看其 action 参数是否属于只读动作集合（read/search/list）；
                 其余情况一律视为写操作
        出参：bool - True 表示该调用是只读调用
        """
        if tool_call.name in READ_ONLY_TOOL_NAMES:
            return True
        if tool_call.name == "file":
            action = tool_call.arguments.get("action", "")
            return action in READ_ONLY_FILE_ACTIONS
        return False

    def prepare_read_only_batch(
        self, tool_calls: list[LLMToolCall]
    ) -> list[LLMToolCall]:
        """
        函数名：prepare_read_only_batch
        入参：
          - tool_calls (list[LLMToolCall])：本轮 LLM 请求的只读工具调用列表
        功能：对只读工具调用批次做去重和数量限制，避免一轮内重复/过多的探索性调用
             浪费执行轮次
        运行逻辑：
          Deduplicate read-only calls by normalized signature so repeated model
          probes like glob/grep do not waste a full loop iteration.
          遍历调用列表，对每个调用计算归一化签名（工具名+参数），签名已出现过则跳过；
          未出现则加入结果列表，达到 MAX_READ_ONLY_CALLS_PER_BATCH 上限后停止收集
        出参：list[LLMToolCall] - 去重且数量受限后的只读调用列表
        """
        # Deduplicate read-only calls by normalized signature so repeated model
        # probes like glob/grep do not waste a full loop iteration.
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
        """
        函数名：_read_only_signature
        入参：
          - tool_call (LLMToolCall)：待计算签名的工具调用
        功能：为一次只读工具调用生成可哈希、忽略参数顺序的归一化签名，用于去重比较
        运行逻辑：把参数字典的每一项转成 (key字符串, value的repr字符串) 元组，按此排序后
                 与工具名一起组成签名元组
        出参：tuple - (工具名, 排序后的参数键值对元组)，可直接放入 set 做去重判断
        """
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
        """
        函数名：execute
        入参：
          - tool_call (LLMToolCall)：LLM 发出的一次工具调用（含工具名、参数、调用 ID）
          - context (LoopContext)：当前执行上下文，用于回填对话历史、计划状态等
          - step_number (int)：本次调用在整轮 Loop 中的步骤序号
        功能：执行单个工具调用的完整生命周期，并将结果归一化为 LoopStep 返回给主循环
        运行逻辑：
          1. 构造初始状态为 RUNNING 的 LoopStep，发送 tool:start 事件
          2. 校验工具是否存在；若参数解析阶段已标记错误（__reflexion_parse_error），
             直接标记步骤失败并回填错误信息到上下文，提前返回
          3. 若目标工具是 WorkingMemoryTool，注入当前上下文的 working_memory 实例
          4. 校验必需参数是否齐全，缺失则抛出 ValueError
          5. 通过 ContextVar 设置当前 tool_call_id（供 DelegateTool 等需要感知调用 ID
             的工具读取），执行完毕后无论成功失败都重置该变量
          6. 根据工具执行结果分三路处理：
             a) 需要审批（approval_required）：若审批元数据缺失则标记失败；否则将步骤
                置为 WAITING_FOR_APPROVAL，记录 approval_id，发送 approval:required 事件，
                提前返回（交由主循环的 _handle_approval 处理后续）
             b) 正常返回（成功或失败）：整理输出文本（拼接进程返回码信息、附加白名单内
                的结构化 data 字段并截断超长 content），回填对话历史，尝试做 Working
                Memory 自动提取（失败不影响主流程），发送 tool:result 事件；若目标工具
                是 PlanTool 且产出了新计划，立即将计划同步到 context 并落盘（首次写入用
                write，后续用 sync）
          7. 执行过程中任何异常都被捕获，统一转为 FAILED 状态的步骤，记录错误日志并回填
             错误信息到对话历史，不向上抛出，保证主循环不因单个工具异常而中断
        出参：LoopStep - 执行完毕（或等待审批）的步骤记录
        """
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

        # Every tool invocation emits a start/result pair so the runtime
        # adapter can build a stable tool_trace lifecycle for the UI.
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

            # 参数解析失败时直接返回错误，无需注入 WorkingMemory
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

            # 注入 WorkingMemory 实例到 WorkingMemoryTool（仅在真正执行前注入）
            if isinstance(tool, WorkingMemoryTool):
                tool.set_working_memory(context.working_memory)

            missing = self._validate_required_args(tool, tool_call.arguments)
            if missing:
                raise ValueError(f"缺少必需参数: {', '.join(missing)}")

            # 设置当前 tool_call_id 到上下文变量，供需要感知 call_id 的工具读取
            _call_id_token = _current_tool_call_id.set(tool_call.id)
            try:
                result = await tool.execute(tool_call.arguments)
            finally:
                _current_tool_call_id.reset(_call_id_token)

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

                # Approval is modeled as a paused step instead of an error:
                # the run remains resumable and the frontend gets an approval_id
                # that maps back to this exact tool call.
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
                        # run_id 供子 agent 场景下前端关联审批到具体的 delegate 调用
                        # （DelegateToolCall.tsx / SubAgentDetailPanel.tsx 需要 run_id 才能提交审批结果）
                        "run_id": context.run_id,
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

            # Working Memory 自动提取：从 tool 结果中提取关键信息
            # 同时记录文件访问和工具调用到 SessionTracker
            # 不影响主流程，提取失败仅 debug 日志
            try:
                context.memory_extractor.extract(
                    tool_name=tool_call.name,
                    tool_args=tool_call.arguments,
                    tool_result=tool_output,
                    step=step_number,
                )
            except Exception as me:
                logger.debug("Memory extraction failed for %s: %s", tool_call.name, me)

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
        """
        函数名：_validate_required_args
        入参：
          - tool：目标工具实例（需提供 get_schema() 方法）
          - arguments (dict[str, Any])：本次调用实际传入的参数
        功能：校验调用参数是否满足工具 schema 中声明的必需参数
        运行逻辑：从工具 schema 的 parameters.required 中取出必需参数名列表；
                 逐个检查是否存在于 arguments 中且值不为 None，缺失的收集到列表
        出参：list[str] - 缺失的必需参数名列表，全部满足时为空列表
        """
        schema = tool.get_schema()
        required = schema.get("parameters", {}).get("required", [])
        if not required:
            return []
        missing = []
        for key in required:
            if key not in arguments or arguments[key] is None:
                missing.append(key)
        return missing


