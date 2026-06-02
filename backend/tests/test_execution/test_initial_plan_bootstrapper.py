import pytest

from app.execution.context_manager import LoopContext
from app.execution.initial_plan_bootstrapper import InitialPlanBootstrapper
from app.execution.loop_message_builder import LoopMessageBuilder
from app.execution.prompt_manager import PromptManager
from app.execution.runtime_tool_definitions import RuntimeToolDefinitions
from app.llm.base import LLMResponse, LLMToolCall, StreamChunk
from app.tools.plan_tool import PlanTool
from app.tools.registry import ToolRegistry


class FakeLLM:
    def __init__(self, response: LLMResponse):
        self.response = response
        self.complete_calls = 0
        self.stream_complete_calls = 0

    async def complete(self, messages, tools=None):
        self.complete_calls += 1
        return self.response

    async def stream_complete(self, messages, tools=None):
        self.stream_complete_calls += 1
        yield StreamChunk(type="error", error="stream should not be used")

    def get_model_name(self) -> str:
        return "fake-model"


def build_bootstrapper(llm: FakeLLM, events: list[tuple[str, dict]]) -> InitialPlanBootstrapper:
    registry = ToolRegistry()
    registry.register(PlanTool())

    async def emit(event_type: str, data: dict):
        events.append((event_type, data))

    return InitialPlanBootstrapper(
        llm=llm,
        tool_definitions=RuntimeToolDefinitions(registry),
        message_builder=LoopMessageBuilder(prompt_manager=PromptManager(), max_context_groups=10),
        emit=emit,
    )


@pytest.mark.asyncio
async def test_initial_plan_bootstrapper_uses_non_streaming_complete(tmp_path):
    response = LLMResponse(
        tool_calls=[
            LLMToolCall(
                name="plan",
                arguments={
                    "action": "create",
                    "goal": "修复初始计划调用",
                    "steps": ["定位调用路径", "改为非流式", "验证行为"],
                },
            )
        ]
    )
    llm = FakeLLM(response)
    events: list[tuple[str, dict]] = []
    bootstrapper = build_bootstrapper(llm, events)
    context = LoopContext(task="修复初始计划调用", project_path=str(tmp_path))

    await bootstrapper.bootstrap(context)

    assert llm.complete_calls == 1
    assert llm.stream_complete_calls == 0
    assert context.plan is not None
    assert context.plan.goal == "修复初始计划调用"
    assert [event_type for event_type, _ in events] == ["plan:updated"]
