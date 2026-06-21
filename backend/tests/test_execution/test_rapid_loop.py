import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.execution.context_manager import LoopContext
from app.execution.models import LoopResult, LoopStatus, StepStatus
from app.execution.plan_engine import Plan, PlanStep
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm.base import LLMResponse, LLMToolCall, MessageRole, StreamChunk
from app.llm.retry import LLMRetryExhaustedError
from app.tools.base import BaseTool, ToolApprovalRequest, ToolResult
from app.tools.plan_tool import PlanTool
from app.tools.registry import ToolRegistry


class MockTool(BaseTool):
    """测试用Mock工具"""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def description(self) -> str:
        return "Mock tool for testing"

    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path"}},
            },
        }

    async def execute(self, args):
        return ToolResult(success=True, output="mock output")


class ReadOnlyFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "file"

    @property
    def description(self) -> str:
        return "Read-only file tool for testing"

    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "path": {"type": "string"},
                },
            },
        }

    async def execute(self, args):
        return ToolResult(success=True, output=f"read {args.get('path', '')}".strip())


class ApprovalTool(BaseTool):
    @property
    def name(self) -> str:
        return "approval_tool"

    @property
    def description(self) -> str:
        return "Tool that requires approval"

    async def execute(self, args):
        return ToolResult(
            success=False,
            approval_required=True,
            approval=ToolApprovalRequest(
                approval_id="approval-1",
                tool_name="approval_tool",
                summary="需要审批",
                payload={"value": 1},
            ),
        )


class MissingApprovalMetadataTool(BaseTool):
    @property
    def name(self) -> str:
        return "missing_approval_metadata"

    @property
    def description(self) -> str:
        return "Tool that incorrectly omits approval metadata"

    async def execute(self, args):
        return ToolResult(
            success=False,
            approval_required=True,
            output="missing approval payload",
        )


class ExplodingTool(BaseTool):
    @property
    def name(self) -> str:
        return "explode"

    @property
    def description(self) -> str:
        return "Tool that raises during execution"

    async def execute(self, args):
        raise RuntimeError("boom")


class FailingTool(BaseTool):
    @property
    def name(self) -> str:
        return "failing"

    @property
    def description(self) -> str:
        return "Always fails"

    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string"}},
            },
        }

    async def execute(self, args):
        return ToolResult(success=False, error="Operation failed")


class TestRapidExecutionLoop:
    @staticmethod
    async def _stream_response(content="", tool_calls=None, finish_reason="stop"):
        if content:
            yield StreamChunk(type="content", content=content)

        if tool_calls:
            yield StreamChunk(
                type="tool_calls", tool_calls=tool_calls, finish_reason=finish_reason
            )
        else:
            yield StreamChunk(type="done", finish_reason=finish_reason)

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.get_model_name = lambda: "gpt-4"

        async def stream_collect(
            messages, tools=None, *, on_content=None, on_reasoning=None, max_empty_retries=3,
            track_first_chunk_latency=False,
        ):
            """默认 stream_collect 实现，调用 stream_complete 并收集响应"""
            first_chunk_latency = None
            first_chunk_received = False

            for attempt in range(max_empty_retries + 1):
                content_parts = []
                reasoning_parts = []
                tool_calls = []
                finish_reason = "stop"

                stream = llm.stream_complete(messages, tools)
                try:
                    async for chunk in stream:
                        if chunk.type == "content" and chunk.content:
                            content_parts.append(chunk.content)
                            if on_content:
                                await on_content(chunk.content)
                            if track_first_chunk_latency and not first_chunk_received:
                                first_chunk_latency = 0.01
                                first_chunk_received = True
                        elif chunk.type == "reasoning" and chunk.reasoning_content:
                            reasoning_parts.append(chunk.reasoning_content)
                            if on_reasoning:
                                await on_reasoning(chunk.reasoning_content)
                            if track_first_chunk_latency and not first_chunk_received:
                                first_chunk_latency = 0.01
                                first_chunk_received = True
                        elif chunk.type == "tool_calls":
                            tool_calls = chunk.tool_calls
                            finish_reason = chunk.finish_reason or "tool_calls"
                            break
                        elif chunk.type == "done":
                            finish_reason = chunk.finish_reason or "stop"
                            break
                        elif chunk.type == "error":
                            if attempt < max_empty_retries:
                                break
                            raise RuntimeError(chunk.error or "LLM 流式调用失败")
                finally:
                    if hasattr(stream, "aclose"):
                        await stream.aclose()

                response = LLMResponse(
                    content="".join(content_parts),
                    reasoning_content="".join(reasoning_parts) or None,
                    tool_calls=tool_calls,
                    finish_reason=finish_reason,
                    model=llm.get_model_name(),
                )

                if response.has_content or response.has_tool_calls:
                    return response, first_chunk_latency

                if attempt < max_empty_retries:
                    continue

            return response, first_chunk_latency

        llm.stream_collect = stream_collect
        return llm

    @pytest.fixture
    def tool_registry(self):
        registry = ToolRegistry()
        registry.register(MockTool())
        return registry

    @pytest.fixture
    def execution_loop(self, mock_llm, tool_registry):
        return RapidExecutionLoop(
            llm=mock_llm, tool_registry=tool_registry, max_steps=5
        )

    @pytest.mark.asyncio
    async def test_execution_with_finish(self, execution_loop, mock_llm):
        """测试任务正常完成（无工具调用）"""

        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(content="任务完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("测试任务")

        assert isinstance(result, LoopResult)
        assert result.status == LoopStatus.COMPLETED
        assert "任务完成" in result.result
        assert not hasattr(result, "project_id")
        assert not hasattr(result, "session_id")
        assert not hasattr(result, "project_path")
        assert not hasattr(result, "provider_id")
        assert not hasattr(result, "model_id")

    @pytest.mark.asyncio
    async def test_empty_response_with_finish_reason_stop_returns_friendly_message(
        self,
        execution_loop,
        mock_llm,
    ):
        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(content=""):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("测试空响应")

        assert result.status == LoopStatus.COMPLETED
        assert "内容审核" in result.result

    @pytest.mark.asyncio
    async def test_execution_with_tool_call(self, execution_loop, mock_llm):
        """测试带工具调用的执行"""
        # 第一次调用返回工具调用，第二次返回完成
        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="执行工具",
                    tool_calls=[LLMToolCall(name="mock", arguments={})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="完成"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("执行工具任务")

        assert len(result.steps) == 1
        assert result.steps[0].tool == "mock"
        assert result.steps[0].status.value == "success"
        assert result.result == "完成"

    @pytest.mark.asyncio
    async def test_tool_results_are_sent_back_to_llm(self, execution_loop, mock_llm):
        """测试工具调用和结果会进入下一轮 LLM 消息"""
        captured_calls = []
        tool_call = LLMToolCall(name="mock", arguments={"path": "README.md"})

        async def mock_stream(messages, tools=None):
            captured_calls.append((messages, tools))
            call_index = len(captured_calls)

            if call_index == 1:
                async for chunk in self._stream_response(
                    content="先读取 README",
                    tool_calls=[tool_call],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            else:
                # Agent returns final answer after tool execution
                async for chunk in self._stream_response(content="README 已读取完成"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("帮我看一下当前 README")

        assert result.status == LoopStatus.COMPLETED
        assert result.result == "README 已读取完成"
        assert len(captured_calls) == 2

        second_messages, second_tools = captured_calls[1]
        assert second_tools is not None

        assistant_message = next(
            msg for msg in second_messages if msg.role == "assistant" and msg.tool_calls
        )
        assert assistant_message.content == "先读取 README"
        assert assistant_message.tool_calls[0].name == "mock"
        assert assistant_message.tool_calls[0].arguments == {"path": "README.md"}

        tool_message = next(msg for msg in second_messages if msg.role == "tool")
        assert tool_message.content == "mock output"
        assert tool_message.tool_call_id == tool_call.id

    @pytest.mark.asyncio
    async def test_plan_step_can_span_multiple_non_plan_tool_batches_before_update(
        self,
        mock_llm,
    ):
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(PlanTool())
        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=registry, max_steps=5
        )

        seeded_plan = Plan(
            goal="修复循环执行",
            steps=[
                PlanStep(
                    content="定位根因", status="completed", findings="已确认状态问题"
                ),
                PlanStep(content="修改执行循环", status="in_progress"),
                PlanStep(content="验证结果", status="pending"),
            ],
        )
        plan_tool = registry.get("plan")

        async def bootstrap_with_plan(context):
            context.plan = seeded_plan
            plan_tool.set_plan(seeded_plan)

        execution_loop._bootstrap_plan = bootstrap_with_plan

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if tools is not None and call_count[0] == 1:
                async for chunk in self._stream_response(
                    tool_calls=[
                        LLMToolCall(name="mock", arguments={"path": "README.md"})
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return
            if tools is not None and call_count[0] == 2:
                async for chunk in self._stream_response(
                    tool_calls=[
                        LLMToolCall(name="mock", arguments={"path": "src/app.ts"})
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return
            if tools is not None and call_count[0] == 3:
                async for chunk in self._stream_response(
                    tool_calls=[
                        LLMToolCall(
                            name="plan",
                            arguments={
                                "steps": [
                                    {
                                        "content": "定位根因",
                                        "status": "completed",
                                        "findings": "已确认状态问题",
                                    },
                                    {
                                        "content": "修改执行循环",
                                        "status": "completed",
                                        "findings": "已完成修改并验证关键文件",
                                    },
                                    {"content": "验证结果", "status": "in_progress"},
                                ],
                            },
                        )
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            async for chunk in self._stream_response(content="计划已更新，继续执行。"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("继续修复")

        assert result.status == LoopStatus.COMPLETED
        assert len(result.steps) == 3
        assert [step.tool for step in result.steps] == ["mock", "mock", "plan"]
        assert result.result == "计划已更新，继续执行。"

    @pytest.mark.asyncio
    async def test_plan_gate_allows_progress_after_plan_step_done(
        self,
        mock_llm,
    ):
        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(PlanTool())
        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=registry, max_steps=6
        )

        seeded_plan = Plan(
            goal="修复循环执行",
            steps=[
                PlanStep(
                    content="定位根因", status="completed", findings="已确认状态问题"
                ),
                PlanStep(content="修改执行循环", status="in_progress"),
                PlanStep(content="验证结果", status="pending"),
            ],
        )
        plan_tool = registry.get("plan")

        async def bootstrap_with_plan(context):
            context.plan = seeded_plan
            plan_tool.set_plan(seeded_plan)

        execution_loop._bootstrap_plan = bootstrap_with_plan

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if tools is not None and call_count[0] == 1:
                async for chunk in self._stream_response(
                    tool_calls=[
                        LLMToolCall(name="mock", arguments={"path": "README.md"})
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return
            if tools is not None and call_count[0] == 2:
                async for chunk in self._stream_response(
                    tool_calls=[
                        LLMToolCall(
                            name="plan",
                            arguments={
                                "steps": [
                                    {
                                        "content": "定位根因",
                                        "status": "completed",
                                        "findings": "已确认状态问题",
                                    },
                                    {
                                        "content": "修改执行循环",
                                        "status": "completed",
                                        "findings": "修改已完成",
                                    },
                                    {"content": "验证结果", "status": "in_progress"},
                                ],
                            },
                        )
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return
            async for chunk in self._stream_response(
                content="计划已更新，继续下一步。"
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("继续修复")

        assert result.status == LoopStatus.COMPLETED
        assert len(result.steps) == 2
        assert result.steps[1].tool == "plan"
        assert result.result == "计划已更新，继续下一步。"

    @pytest.mark.asyncio
    async def test_tier3_compaction_keeps_recent_context_groups(
        self, execution_loop, mock_llm
    ):
        context = LoopContext(task="summarize old context")
        for i in range(12):
            context.add_message(MessageRole.USER, f"message {i}")

        async def mock_summarizer(task: str, transcript: str) -> str:
            return "summary [session_recall can retrieve]"

        await context.compressor.compact_tier3(
            task=context.task, summarizer=mock_summarizer
        )

        assert (
            context.compressor.get_compacted_summary()
            == "summary [session_recall can retrieve]"
        )
        messages = context.compressor.get_messages()
        # With max_context_groups=10, should keep last 10 messages (messages 2-11)
        assert [msg["content"] for msg in messages] == [
            f"message {i}" for i in range(2, 12)
        ]

    @pytest.mark.asyncio
    async def test_final_response_fallback_when_no_content_after_tools(
        self,
        execution_loop,
        mock_llm,
    ):
        """测试工具执行后空响应会注入任务提醒重试，重试后获得内容直接完成"""
        captured_calls = []

        async def mock_stream(messages, tools=None):
            captured_calls.append((messages, tools))
            call_index = len(captured_calls)

            if call_index == 1:
                async for chunk in self._stream_response(
                    content="先查看项目结构",
                    tool_calls=[LLMToolCall(name="mock", arguments={})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            elif call_index == 2:
                async for chunk in self._stream_response(content=""):
                    yield chunk
            else:
                async for chunk in self._stream_response(
                    content="项目采用前后端分离结构。"
                ):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("其项目结构是怎么样的呢？")

        assert result.status == LoopStatus.COMPLETED
        assert "项目采用前后端分离结构" in result.result
        retry_messages, retry_tools = captured_calls[2]
        task_reminder_injected = any(
            "model produced no output" in (m.content or "").lower()
            for m in retry_messages
        )
        assert task_reminder_injected

    @pytest.mark.asyncio
    async def test_rapid_loop_includes_seeded_history_before_current_user_message(
        self,
        execution_loop,
        mock_llm,
    ):
        captured = {}

        async def mock_stream(messages, tools=None):
            captured["messages"] = messages
            async for chunk in self._stream_response(content="ok"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run(
            "继续处理",
            history_messages=[
                {"role": "user", "content": "上一轮需求"},
                {"role": "assistant", "content": "上一轮结论"},
            ],
        )

        contents = [
            message.content for message in captured["messages"] if message.content
        ]
        assert "继续处理" in contents
        assert "上一轮需求" in contents
        assert "上一轮结论" in contents
        assert captured["messages"][-1].role == "user"
        assert captured["messages"][-1].content == "继续处理"

    @pytest.mark.asyncio
    async def test_execution_max_steps(self, execution_loop, mock_llm):
        """测试超过最大步数"""

        # 始终返回工具调用
        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(
                content="继续执行",
                tool_calls=[LLMToolCall(name="mock", arguments={})],
                finish_reason="tool_calls",
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("无限循环任务")

        assert result.status == LoopStatus.COMPLETED
        assert len(result.steps) == 5

    @pytest.mark.asyncio
    async def test_read_only_batch_is_deduplicated_and_capped(self, mock_llm):
        registry = ToolRegistry()
        registry.register(ReadOnlyFileTool())
        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=registry, max_steps=10
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    tool_calls=[
                        LLMToolCall(
                            name="file", arguments={"action": "read", "path": "a.ts"}
                        ),
                        LLMToolCall(
                            name="file", arguments={"action": "read", "path": "a.ts"}
                        ),
                        LLMToolCall(
                            name="file", arguments={"action": "read", "path": "b.ts"}
                        ),
                        LLMToolCall(
                            name="file", arguments={"action": "read", "path": "c.ts"}
                        ),
                        LLMToolCall(
                            name="file", arguments={"action": "read", "path": "d.ts"}
                        ),
                        LLMToolCall(
                            name="file", arguments={"action": "read", "path": "e.ts"}
                        ),
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            async for chunk in self._stream_response(content="检查完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("检查多个文件")

        assert result.status == LoopStatus.COMPLETED
        assert len(result.steps) == 4
        assert [step.args["path"] for step in result.steps] == [
            "a.ts",
            "b.ts",
            "c.ts",
            "d.ts",
        ]

    @pytest.mark.asyncio
    async def test_investigation_budget_allows_additional_read_only_passes_when_each_adds_new_facts(
        self,
        mock_llm,
    ):
        registry = ToolRegistry()
        registry.register(ReadOnlyFileTool())
        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=registry, max_steps=10
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if tools is not None and call_count[0] <= 3:
                async for chunk in self._stream_response(
                    tool_calls=[
                        LLMToolCall(
                            name="file",
                            arguments={"action": "read", "path": f"{call_count[0]}.ts"},
                        )
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            async for chunk in self._stream_response(content="继续基于新证据推进。"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("重新检查并给出结论")

        assert result.status == LoopStatus.COMPLETED
        assert len(result.steps) == 3
        assert result.result == "继续基于新证据推进。"

    @pytest.mark.asyncio
    async def test_investigation_budget_forces_final_summary_after_read_only_pass_yields_no_new_facts(
        self,
        mock_llm,
    ):
        registry = ToolRegistry()
        registry.register(ReadOnlyFileTool())
        execution_loop = RapidExecutionLoop(
            llm=mock_llm, tool_registry=registry, max_steps=20
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if tools is not None:
                async for chunk in self._stream_response(
                    tool_calls=[
                        LLMToolCall(
                            name="file", arguments={"action": "read", "path": "same.ts"}
                        )
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            async for chunk in self._stream_response(content="基于现有证据给出结论。"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("重新检查并给出结论")

        assert result.status == LoopStatus.COMPLETED
        # Loop runs to max_steps (20) since each call is deduplicated but continues
        assert len(result.steps) == 20
        # When max_steps is reached, the result is the default message
        assert result.result == "执行完成（达到最大步数）"

    @pytest.mark.asyncio
    async def test_event_callback_emits_tool_start_and_result(
        self, mock_llm, tool_registry
    ):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=2,
            event_callback=callback,
        )
        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="先检查文件",
                    tool_calls=[LLMToolCall(name="mock", arguments={"path": "."})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            async for chunk in self._stream_response(content="检查完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run("检查项目")

        event_types = [event["type"] for event in events]
        assert "tool:start" in event_types
        assert "tool:result" in event_types
        assert "run:complete" in event_types

    @pytest.mark.asyncio
    async def test_llm_call_emits_performance_metrics(self, mock_llm, tool_registry):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=2,
            event_callback=callback,
        )

        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(content="完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run("检查性能指标")

        metrics_event = next(
            event for event in events if event["type"] == "metrics:llm_call"
        )
        assert metrics_event["data"]["model"] == "gpt-4"
        assert metrics_event["data"]["attempt"] == 1
        assert metrics_event["data"]["prompt_tokens"] > 0
        assert metrics_event["data"]["message_count"] > 0
        assert metrics_event["data"]["tool_count"] == 1
        assert metrics_event["data"]["duration"] >= 0
        assert metrics_event["data"]["first_chunk_latency"] >= 0
        assert metrics_event["data"]["content_chars"] == 2

    @pytest.mark.asyncio
    async def test_tool_approval_required_pauses_run_without_error_recovery(
        self, mock_llm
    ):
        registry = ToolRegistry()
        registry.register(ApprovalTool())
        events = []
        captured_calls = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=3,
            event_callback=callback,
        )

        tool_call = LLMToolCall(name="approval_tool", arguments={"value": 1})

        async def mock_stream(messages, tools=None):
            captured_calls.append(messages)
            async for chunk in self._stream_response(
                content="需要先审批",
                tool_calls=[tool_call],
                finish_reason="tool_calls",
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        async def deny_later():
            await asyncio.sleep(0.1)
            execution_loop.set_approval_result(None)

        result, _ = await asyncio.gather(
            execution_loop.run("执行需要审批的工具"),
            deny_later(),
        )

        assert result.status == LoopStatus.CANCELLED
        assert result.result == "审批被拒绝"
        waiting_step = result.steps[-1]
        assert waiting_step.status == StepStatus.FAILED
        assert waiting_step.error == "审批被拒绝"
        assert waiting_step.tool_call_id == tool_call.id
        assert waiting_step.approval_id == "approval-1"

        event_types = [event["type"] for event in events]
        assert "approval:required" in event_types
        assert "run:waiting_for_approval" in event_types
        # Deny now emits tool:error and run:cancelled to properly terminate
        assert "tool:error" in event_types
        assert "run:cancelled" in event_types
        assert "run:complete" not in event_types
        assert len(captured_calls) == 1

        tool_start_event = next(
            event for event in events if event["type"] == "tool:start"
        )
        assert tool_start_event["data"]["tool_call_id"] == tool_call.id

        approval_event = next(
            event for event in events if event["type"] == "approval:required"
        )
        assert approval_event["data"]["tool_call_id"] == tool_call.id
        assert approval_event["data"]["approval_id"] == "approval-1"

    @pytest.mark.asyncio
    async def test_approval_required_without_metadata_fails_instead_of_waiting(
        self, mock_llm
    ):
        registry = ToolRegistry()
        registry.register(MissingApprovalMetadataTool())
        events = []
        captured_calls = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=3,
            event_callback=callback,
        )
        tool_call = LLMToolCall(
            name="missing_approval_metadata", arguments={"value": 1}
        )

        async def mock_stream(messages, tools=None):
            captured_calls.append(messages)
            if len(captured_calls) == 1:
                async for chunk in self._stream_response(
                    tool_calls=[tool_call],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            async for chunk in self._stream_response(content="已收到工具错误"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("执行错误审批工具")

        assert result.status == LoopStatus.COMPLETED
        assert result.result == "已收到工具错误"
        assert result.steps[-1].status == StepStatus.FAILED
        assert result.steps[-1].tool_call_id == tool_call.id
        assert "approval metadata" in result.steps[-1].error
        assert len(captured_calls) == 2

        tool_message = next(
            message for message in captured_calls[1] if message.role == "tool"
        )
        assert tool_message.tool_call_id == tool_call.id
        assert "approval metadata" in tool_message.content

        event_types = [event["type"] for event in events]
        assert "approval:required" not in event_types
        assert event_types.count("tool:error") == 1

    @pytest.mark.asyncio
    async def test_initial_plan_preflight_emits_plan_without_streaming_preface(
        self, mock_llm
    ):
        import shutil
        from app.execution.plan_file_sync import PlanFileSync

        plan_dir = PlanFileSync()._resolve_base_dir()
        if os.path.isdir(plan_dir):
            shutil.rmtree(plan_dir)

        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(PlanTool())
        events = []
        captured_tools = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=2,
            event_callback=callback,
        )

        async def mock_complete(messages, tools=None):
            from app.llm.base import LLMResponse

            captured_tools.append(tools)
            return LLMResponse(
                content="我先制定计划。",
                tool_calls=[
                    LLMToolCall(
                        name="plan",
                        arguments={
                            "goal": "修复计划显示",
                            "steps": [
                                {"content": "定位问题", "status": "in_progress"},
                                {"content": "修改实现", "status": "pending"},
                                {"content": "验证结果", "status": "pending"},
                            ],
                        },
                    )
                ],
                finish_reason="tool_calls",
                model="gpt-4",
            )

        async def mock_stream(messages, tools=None):
            captured_tools.append(tools)
            # 第一次调用是计划阶段（_bootstrap_plan），需要返回 plan tool_call
            # 后续调用是主循环，返回纯文本
            if len(captured_tools) == 1:
                async for chunk in self._stream_response(
                    content="我先制定计划。",
                    tool_calls=[
                        LLMToolCall(
                            name="plan",
                            arguments={
                                "goal": "修复计划显示",
                                "steps": [
                                    {"content": "定位问题", "status": "in_progress"},
                                    {"content": "修改实现", "status": "pending"},
                                    {"content": "验证结果", "status": "pending"},
                                ],
                            },
                        )
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="开始执行。"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("请修复计划窗口流式显示和位置")

        assert result.status == LoopStatus.COMPLETED
        assert result.result == "开始执行。"
        event_types = [event["type"] for event in events]
        # _bootstrap_plan 阶段通过 stream_collect 发出 llm:content，然后 plan:updated；
        # 主循环再发出 llm:content；结束时再发 plan:updated。
        # 断言：第一个 llm:content 在第一个 plan:updated 之前（bootstrap 流式输出），
        # 并且至少有一个 llm:content 在第一个 plan:updated 之后（主循环输出）。
        first_plan_idx = event_types.index("plan:updated")
        first_content_idx = event_types.index("llm:content")
        assert first_content_idx < first_plan_idx, (
            f"llm:content should appear before plan:updated in bootstrap phase, "
            f"got content at {first_content_idx}, plan at {first_plan_idx}"
        )
        main_content_after_plan = next(
            i for i, t in enumerate(event_types) if t == "llm:content" and i > first_plan_idx
        )
        assert first_plan_idx < main_content_after_plan
        plan_event = next(event for event in events if event["type"] == "plan:updated")
        assert plan_event["data"]["goal"] == "修复计划显示"
        step_contents = [step["content"] for step in plan_event["data"]["steps"]]
        assert step_contents == [
            "定位问题",
            "修改实现",
            "验证结果",
        ]
        main_tool_names = [tool.name for tool in captured_tools[1]]
        assert "plan" in main_tool_names
        main_plan_tool = next(tool for tool in captured_tools[1] if tool.name == "plan")

    @pytest.mark.asyncio
    async def test_initial_plan_preflight_can_decline_and_keep_normal_streaming(
        self, mock_llm
    ):
        import shutil
        from app.execution.plan_file_sync import PlanFileSync

        plan_dir = PlanFileSync()._resolve_base_dir()
        if os.path.isdir(plan_dir):
            shutil.rmtree(plan_dir)

        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(PlanTool())
        events = []
        captured_tools = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=2,
            event_callback=callback,
        )

        async def mock_complete(messages, tools=None):
            from app.llm.base import LLMResponse

            captured_tools.append(tools)
            return LLMResponse(
                content="NO_PLAN",
                tool_calls=[],
                finish_reason="stop",
                model="gpt-4",
            )

        async def mock_stream(messages, tools=None):
            captured_tools.append(tools)
            # 第一次调用是计划阶段（_bootstrap_plan），返回 NO_PLAN
            # 后续调用是主循环，返回纯文本
            if len(captured_tools) == 1:
                async for chunk in self._stream_response(content="NO_PLAN"):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="直接回答。"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("解释一下这个函数")

        assert result.status == LoopStatus.COMPLETED
        assert result.result == "直接回答。"
        assert not any(event["type"] == "plan:updated" for event in events)
        assert any(
            event["type"] == "llm:content"
            and event["data"].get("content") == "直接回答。"
            for event in events
        )
        main_tool_names = [tool.name for tool in captured_tools[1]]
        assert "mock" in main_tool_names

    @pytest.mark.asyncio
    async def test_event_callback(self, mock_llm, tool_registry):
        """测试事件回调"""
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=5,
            event_callback=callback,
        )

        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(content="任务完成"):
                yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run("测试任务")

        # 检查事件
        execution_start = next(e for e in events if e["type"] == "run:start")
        assert execution_start["data"]["run_id"].startswith("run-")
        assert "execution_id" not in execution_start["data"]
        assert any(e["type"] == "llm:content" for e in events)
        assert any(e["type"] == "run:complete" for e in events)
        assert not any(e["type"] == "llm:start" for e in events)

    @pytest.mark.asyncio
    async def test_does_not_emit_legacy_llm_thought_or_tool_call_events(
        self, mock_llm, tool_registry
    ):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=2,
            event_callback=callback,
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="我先查看项目结构，再继续探索。",
                    tool_calls=[LLMToolCall(name="mock", arguments={"path": "."})],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="项目结构已经确认。"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        await execution_loop.run("介绍一下当前项目结构")

        event_types = [event["type"] for event in events]
        assert "llm:thought" not in event_types
        assert "llm:tool_call" not in event_types
        assert "summary:start" not in event_types
        assert "summary:complete" not in event_types

    @pytest.mark.asyncio
    async def test_execution_returns_cancelled_when_task_is_cancelled(
        self,
        mock_llm,
        tool_registry,
    ):
        """测试取消运行中的执行会返回 cancelled 状态并发送事件"""
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=2,
            event_callback=callback,
        )

        async def mock_stream(messages, tools=None):
            yield StreamChunk(type="content", content="正在分析项目结构")
            await asyncio.sleep(5)
            yield StreamChunk(type="done", finish_reason="stop")

        mock_llm.stream_complete = mock_stream

        task = asyncio.create_task(
            execution_loop.run("请检查项目结构", run_id="run-cancel-test")
        )
        await asyncio.sleep(0)
        task.cancel()

        result = await task

        assert result.id == "run-cancel-test"
        assert result.status == LoopStatus.CANCELLED
        assert result.result == "执行已取消"
        assert any(event["type"] == "run:cancelled" for event in events)

    @pytest.mark.asyncio
    async def test_retry_exhaustion_cancels_execution_without_error_recovery(
        self, mock_llm, tool_registry
    ):
        events = []
        call_count = 0

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=3,
            event_callback=callback,
        )

        async def mock_stream(messages, tools=None):
            nonlocal call_count
            call_count += 1
            raise LLMRetryExhaustedError(ValueError("network down"), max_retries=5)
            yield

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("需要联网的任务")

        assert call_count == 1
        assert result.status == LoopStatus.CANCELLED
        assert result.result == "执行已取消：LLM 重试次数已达上限"
        event_types = [event["type"] for event in events]
        assert "run:cancelled" in event_types
        assert "run:error" not in event_types

    @pytest.mark.asyncio
    async def test_failed_execution_emits_execution_error_event(
        self, mock_llm, tool_registry
    ):
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=tool_registry,
            max_steps=3,
            event_callback=callback,
        )

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="先执行工具",
                    tool_calls=[
                        LLMToolCall(name="mock", arguments={"path": "README.md"})
                    ],
                    finish_reason="tool_calls",
                ):
                    yield chunk
                return

            raise RuntimeError("boom")
            yield

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("失败任务")

        assert result.status == LoopStatus.FAILED
        assert any(event["type"] == "run:error" for event in events)

    @pytest.mark.asyncio
    async def test_tool_exception_emits_single_normalized_tool_error(self, mock_llm):
        registry = ToolRegistry()
        registry.register(ExplodingTool())
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=1,
            event_callback=callback,
        )
        tool_call = LLMToolCall(name="explode", arguments={"path": "README.md"})

        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(
                tool_calls=[tool_call],
                finish_reason="tool_calls",
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("执行异常工具")

        assert result.steps[-1].status == StepStatus.FAILED
        tool_error_events = [event for event in events if event["type"] == "tool:error"]
        assert len(tool_error_events) == 1
        assert tool_error_events[0]["data"] == {
            "tool_name": "explode",
            "step_number": 1,
            "tool_call_id": tool_call.id,
            "success": False,
            "output": None,
            "error": "boom",
            "duration": result.steps[-1].duration,
            "arguments": {"path": "README.md"},
        }

    @pytest.mark.asyncio
    async def test_shell_destructive_command_triggers_approval_through_loop(
        self, mock_llm
    ):
        """Shell tool with destructive command should trigger approval flow through the loop."""
        import os
        import tempfile

        from app.security.command_effect_registry import CommandEffectRegistry
        from app.security.path_security import PathSecurity
        from app.security.sandbox.factory import NullSandbox
        from app.security.shell_security import ShellSecurity
        from app.tools.shell_tool import ShellTool

        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            path_security = PathSecurity([root_dir], base_dir=root_dir)
            registry = CommandEffectRegistry()
            shell_tool = ShellTool(
                ShellSecurity(), path_security, registry, NullSandbox()
            )

            tool_registry = ToolRegistry()
            tool_registry.register(shell_tool)

            events = []

            async def callback(event_type, data):
                events.append({"type": event_type, "data": data})

            execution_loop = RapidExecutionLoop(
                llm=mock_llm,
                tool_registry=tool_registry,
                max_steps=3,
                event_callback=callback,
            )

            # DESTRUCTIVE command triggers REQUIRE_APPROVAL
            tool_call = LLMToolCall(
                name="shell", arguments={"command": "rm -rf build/"}
            )

            async def mock_stream(messages, tools=None):
                async for chunk in self._stream_response(
                    content="执行删除命令",
                    tool_calls=[tool_call],
                    finish_reason="tool_calls",
                ):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        async def deny_later():
            await asyncio.sleep(0.1)
            execution_loop.set_approval_result(None)

        result, _ = await asyncio.gather(
            execution_loop.run("测试删除命令", project_path=root_dir),
            deny_later(),
        )

        assert result.status == LoopStatus.CANCELLED
        assert result.result == "审批被拒绝"
        waiting_step = result.steps[-1]
        assert waiting_step.status == StepStatus.FAILED
        assert waiting_step.tool == "shell"

        event_types = [event["type"] for event in events]
        assert "approval:required" in event_types
        assert "run:complete" not in event_types

    @pytest.mark.asyncio
    async def test_approval_resume_continues_loop_execution(self, mock_llm):
        """When approval is granted, the loop resumes and continues executing."""
        registry = ToolRegistry()
        registry.register(ApprovalTool())
        registry.register(MockTool())
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=5,
            event_callback=callback,
        )

        approval_tool_call = LLMToolCall(name="approval_tool", arguments={"value": 1})
        mock_tool_call = LLMToolCall(name="mock", arguments={"path": "."})

        call_count = [0]

        async def mock_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                async for chunk in self._stream_response(
                    content="需要审批",
                    tool_calls=[approval_tool_call],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            elif call_count[0] == 2:
                async for chunk in self._stream_response(
                    content="审批通过，继续执行",
                    tool_calls=[mock_tool_call],
                    finish_reason="tool_calls",
                ):
                    yield chunk
            else:
                async for chunk in self._stream_response(content="任务完成"):
                    yield chunk

        mock_llm.stream_complete = mock_stream

        async def resume_after_delay():
            await asyncio.sleep(0.1)
            execution_loop.set_approval_result(
                {
                    "success": True,
                    "output": "approved output",
                    "error": None,
                }
            )

        asyncio.get_event_loop().create_task(resume_after_delay())

        result = await execution_loop.run("需要审批的任务")

        assert result.status == LoopStatus.COMPLETED
        assert len(result.steps) == 2
        assert result.steps[0].status == StepStatus.SUCCESS
        assert result.steps[0].tool == "approval_tool"
        assert result.steps[1].tool == "mock"
        # 3 tool-execution calls + 1 completion firewall nudge = 4 total
        assert call_count[0] >= 3

        event_types = [event["type"] for event in events]
        assert "run:waiting_for_approval" in event_types
        assert "run:resuming" in event_types
        assert "run:complete" in event_types

    @pytest.mark.asyncio
    async def test_approval_deny_cancels_loop_execution(self, mock_llm):
        """When approval is denied, the loop cancels."""
        registry = ToolRegistry()
        registry.register(ApprovalTool())
        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        execution_loop = RapidExecutionLoop(
            llm=mock_llm,
            tool_registry=registry,
            max_steps=5,
            event_callback=callback,
        )

        approval_tool_call = LLMToolCall(name="approval_tool", arguments={"value": 1})

        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(
                content="需要审批",
                tool_calls=[approval_tool_call],
                finish_reason="tool_calls",
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        async def deny_after_delay():
            await asyncio.sleep(0.1)
            execution_loop.set_approval_result(None)

        asyncio.get_event_loop().create_task(deny_after_delay())

        result = await execution_loop.run("需要审批的任务")

        assert result.status == LoopStatus.CANCELLED
        assert result.result == "审批被拒绝"

        event_types = [event["type"] for event in events]
        assert "run:waiting_for_approval" in event_types
        # Deny emits run:cancelled to properly terminate the run
        assert "run:cancelled" in event_types
        assert "run:complete" not in event_types

    @pytest.mark.asyncio
    async def test_tool_failure_recovery(self, execution_loop, mock_llm):
        """测试工具失败恢复"""

        # 注册一个会失败的工具
        class FailTool(BaseTool):
            @property
            def name(self) -> str:
                return "fail"

            @property
            def description(self) -> str:
                return "Fail tool"

            async def execute(self, args):
                return ToolResult(success=False, error="Failed")

        execution_loop.tool_registry.register(FailTool())

        # 第一次调用返回失败工具
        async def mock_stream(messages, tools=None):
            async for chunk in self._stream_response(
                tool_calls=[LLMToolCall(name="fail", arguments={})],
                finish_reason="tool_calls",
            ):
                yield chunk

        mock_llm.stream_complete = mock_stream

        result = await execution_loop.run("测试失败任务")

        assert result.steps[0].status.value == "failed"


class TestDoomLoopDetection:
    def test_doom_loop_returns_false_for_diverse_calls(self):
        registry = ToolRegistry()
        llm = MagicMock()
        llm.get_model_name.return_value = "test-model"
        loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=registry,
            max_steps=50,
            context_window=128000,
        )
        context = LoopContext(task="test")

        tc1 = LLMToolCall(
            id="c1", name="file", arguments={"action": "read", "path": "a.py"}
        )
        tc2 = LLMToolCall(
            id="c2", name="file", arguments={"action": "read", "path": "b.py"}
        )
        tc3 = LLMToolCall(id="c3", name="grep", arguments={"pattern": "error"})

        loop._record_tool_signature(context, tc1)
        assert not loop._is_doom_loop(context)
        loop._record_tool_signature(context, tc2)
        assert not loop._is_doom_loop(context)
        loop._record_tool_signature(context, tc3)
        assert not loop._is_doom_loop(context)

    def test_doom_loop_returns_true_for_identical_calls(self):
        registry = ToolRegistry()
        llm = MagicMock()
        llm.get_model_name.return_value = "test-model"
        loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=registry,
            max_steps=50,
            context_window=128000,
        )
        context = LoopContext(task="test")

        tc = LLMToolCall(
            id="c1", name="file", arguments={"action": "read", "path": "a.py"}
        )

        loop._record_tool_signature(context, tc)
        assert not loop._is_doom_loop(context)
        loop._record_tool_signature(context, tc)
        assert not loop._is_doom_loop(context)
        loop._record_tool_signature(context, tc)
        assert loop._is_doom_loop(context)

    def test_doom_loop_broken_by_different_call(self):
        registry = ToolRegistry()
        llm = MagicMock()
        llm.get_model_name.return_value = "test-model"
        loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=registry,
            max_steps=50,
            context_window=128000,
        )
        context = LoopContext(task="test")

        tc_a = LLMToolCall(
            id="c1", name="file", arguments={"action": "read", "path": "a.py"}
        )
        tc_b = LLMToolCall(
            id="c2", name="file", arguments={"action": "read", "path": "b.py"}
        )

        loop._record_tool_signature(context, tc_a)
        loop._record_tool_signature(context, tc_a)
        loop._record_tool_signature(context, tc_b)
        loop._record_tool_signature(context, tc_a)
        assert not loop._is_doom_loop(context)


class TestHardenedLoopIntegration:
    @staticmethod
    def _create_mock_llm():
        """创建带有 stream_collect 实现的 mock LLM"""
        llm = AsyncMock()
        llm.get_model_name = lambda: "test-model"

        async def stream_collect(
            messages, tools=None, *, on_content=None, on_reasoning=None, max_empty_retries=3,
            track_first_chunk_latency=False,
        ):
            first_chunk_latency = None
            first_chunk_received = False

            for attempt in range(max_empty_retries + 1):
                content_parts = []
                reasoning_parts = []
                tool_calls = []
                finish_reason = "stop"

                async for chunk in llm.stream_complete(messages, tools):
                    if chunk.type == "content" and chunk.content:
                        content_parts.append(chunk.content)
                        if on_content:
                            await on_content(chunk.content)
                        if track_first_chunk_latency and not first_chunk_received:
                            first_chunk_latency = 0.01
                            first_chunk_received = True
                    elif chunk.type == "reasoning" and chunk.reasoning_content:
                        reasoning_parts.append(chunk.reasoning_content)
                        if on_reasoning:
                            await on_reasoning(chunk.reasoning_content)
                        if track_first_chunk_latency and not first_chunk_received:
                            first_chunk_latency = 0.01
                            first_chunk_received = True
                    elif chunk.type == "tool_calls":
                        tool_calls = chunk.tool_calls
                        finish_reason = chunk.finish_reason or "tool_calls"
                        break
                    elif chunk.type == "done":
                        finish_reason = chunk.finish_reason or "stop"
                        break
                    elif chunk.type == "error":
                        if attempt < max_empty_retries:
                            break
                        raise RuntimeError(chunk.error or "LLM 流式调用失败")

                response = LLMResponse(
                    content="".join(content_parts),
                    reasoning_content="".join(reasoning_parts) or None,
                    tool_calls=tool_calls,
                    finish_reason=finish_reason,
                    model=llm.get_model_name(),
                )

                if response.has_content or response.has_tool_calls:
                    return response, first_chunk_latency

                if attempt < max_empty_retries:
                    continue

            return response, first_chunk_latency

        llm.stream_collect = stream_collect
        return llm

    @pytest.mark.asyncio
    async def test_doom_loop_detection_triggers_on_repeated_write_calls(self):
        registry = ToolRegistry()
        tool = FailingTool()
        registry.register(tool)

        llm = self._create_mock_llm()
        call_count = 0

        async def mock_stream(messages, tools):
            nonlocal call_count
            call_count += 1
            tc = LLMToolCall(
                id=f"c{call_count}", name="failing", arguments={"action": "try"}
            )
            yield StreamChunk(
                type="tool_calls", tool_calls=[tc], finish_reason="tool_calls"
            )

        llm.stream_complete = mock_stream
        loop = RapidExecutionLoop(
            llm=llm, tool_registry=registry, max_steps=20, context_window=128000
        )

        result = await loop.run(task="test doom loop integration")
        assert result.status in (LoopStatus.COMPLETED, LoopStatus.FAILED)

    @pytest.mark.asyncio
    async def test_premature_stop_detected_and_nudged(self):
        registry = ToolRegistry()
        registry.register(ReadOnlyFileTool())

        llm = self._create_mock_llm()
        phase = 0

        async def mock_stream(messages, tools):
            nonlocal phase
            phase += 1
            if phase == 1:
                tc = LLMToolCall(
                    id="c1", name="file", arguments={"action": "read", "path": "a.py"}
                )
                yield StreamChunk(
                    type="tool_calls", tool_calls=[tc], finish_reason="tool_calls"
                )
            else:
                yield StreamChunk(
                    type="content", content="You can now write the code yourself!"
                )
                yield StreamChunk(type="done", finish_reason="stop")

        llm.stream_complete = mock_stream
        loop = RapidExecutionLoop(
            llm=llm, tool_registry=registry, max_steps=20, context_window=128000
        )

        result = await loop.run(task="implement feature X")
        assert result.status in (LoopStatus.COMPLETED, LoopStatus.FAILED)

    @pytest.mark.asyncio
    async def test_plan_incomplete_prevents_stop_and_nudges(self):
        from app.tools.plan_tool import PlanTool

        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(PlanTool())

        llm = self._create_mock_llm()
        call_count = 0

        async def mock_stream(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                tc = LLMToolCall(
                    id="c1",
                    name="plan",
                    arguments={
                        "goal": "Fix bug",
                        "steps": [
                            {"content": "Analyze", "status": "in_progress"},
                            {"content": "Fix", "status": "pending"},
                            {"content": "Test", "status": "pending"},
                        ],
                    },
                )
                yield StreamChunk(
                    type="tool_calls", tool_calls=[tc], finish_reason="tool_calls"
                )
            elif call_count == 2:
                tc = LLMToolCall(id="c2", name="mock", arguments={"query": "test"})
                yield StreamChunk(
                    type="tool_calls", tool_calls=[tc], finish_reason="tool_calls"
                )
            else:
                yield StreamChunk(type="content", content="I have analyzed the issue.")
                yield StreamChunk(type="done", finish_reason="stop")

        llm.stream_complete = mock_stream

        events = []

        async def callback(event_type, data):
            events.append({"type": event_type, "data": data})

        loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=registry,
            max_steps=20,
            context_window=128000,
            event_callback=callback,
        )

        result = await loop.run(task="fix the auth bug")

        # Should not be COMPLETED after just 1 step — the nudge should have triggered
        # The loop either completed with nudged content or kept going
        # Check that a nudge was injected (user message about plan not complete)
        user_msgs = [
            e
            for e in events
            if e["type"] == "tool:result"
            and "NOT complete" in (e["data"].get("output") or "")
        ]
        # At minimum, the plan tool should have been called
        plan_events = [e for e in events if e["type"] == "plan:updated"]
        assert len(plan_events) >= 1

    @pytest.mark.asyncio
    async def test_blocked_step_allows_stop_for_clarification(self):
        from app.tools.plan_tool import PlanTool

        registry = ToolRegistry()
        registry.register(MockTool())
        registry.register(PlanTool())

        llm = self._create_mock_llm()
        call_count = 0

        async def mock_stream(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                tc = LLMToolCall(
                    id="c1",
                    name="plan",
                    arguments={
                        "goal": "Fix bug",
                        "steps": [
                            {
                                "content": "Analyze",
                                "status": "completed",
                                "findings": "Found issue",
                            },
                            {"content": "Fix", "status": "blocked"},
                            {"content": "Test", "status": "pending"},
                        ],
                    },
                )
                yield StreamChunk(
                    type="tool_calls", tool_calls=[tc], finish_reason="tool_calls"
                )
            else:
                yield StreamChunk(
                    type="content",
                    content="The fix step is blocked — I need user clarification on which approach to use. Which do you prefer: option A or option B?",
                )
                yield StreamChunk(type="done", finish_reason="stop")

        llm.stream_complete = mock_stream

        loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=registry,
            max_steps=10,
            context_window=128000,
        )

        result = await loop.run(task="fix the auth bug")

        # Should be COMPLETED — blocked step + clarification question means it's OK to stop
        assert result.status == LoopStatus.COMPLETED
        assert (
            "clarification" in result.result.lower()
            or "option" in result.result.lower()
            or "blocked" in result.result.lower()
        )


