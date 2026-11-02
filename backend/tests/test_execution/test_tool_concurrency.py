"""写操作并发调度策略（tool_concurrency）的单元测试。

覆盖：extract_write_target_path 的可解析性判定、collect_parallel_write_run 的
连续段收集规则（路径互斥、patch 未知足迹、shell 断段、同路径串行、单批上限）。
"""
import pytest
from app.llm.base import LLMToolCall

from app.execution.tool_concurrency import (
    MAX_PARALLEL_WRITE_BATCH,
    collect_parallel_write_run,
    extract_write_target_path,
)


def edit_call(path: str, action: str = "str_replace", call_id: str = "call-1") -> LLMToolCall:
    return LLMToolCall(id=call_id, name="edit", arguments={"action": action, "path": path})


def shell_call(call_id: str = "call-sh") -> LLMToolCall:
    return LLMToolCall(id=call_id, name="shell", arguments={"command": "ls"})


def patch_call(call_id: str = "call-patch") -> LLMToolCall:
    return LLMToolCall(id=call_id, name="patch", arguments={"patch": "*** Begin Patch\n*** End Patch"})


def test_extract_path_accepts_file_scoped_edit_actions():
    assert extract_write_target_path(edit_call("/x/a.py")) == "/x/a.py"
    assert extract_write_target_path(edit_call("C:\\repo\\a.py", action="write")) == "C:/repo/a.py"


def test_extract_path_rejects_unknown_footprints():
    assert extract_write_target_path(edit_call("/x/a.py", action="patch")) is None
    assert extract_write_target_path(shell_call()) is None
    assert extract_write_target_path(edit_call("", call_id="c2")) is None


def test_collects_run_of_distinct_path_edits():
    calls = [edit_call("/a.py", call_id="c1"), edit_call("/b.py", call_id="c2"), edit_call("/c.py", call_id="c3")]
    run = collect_parallel_write_run(calls, 0)
    assert [call.id for call in run] == ["c1", "c2", "c3"]


def test_stops_run_at_duplicate_path():
    calls = [edit_call("/a.py", call_id="c1"), edit_call("/a.py", call_id="c2"), edit_call("/b.py", call_id="c3")]
    run = collect_parallel_write_run(calls, 0)
    assert [call.id for call in run] == ["c1"]


def test_stops_run_at_shell_boundary():
    calls = [edit_call("/a.py", call_id="c1"), shell_call(), edit_call("/b.py", call_id="c3")]
    run = collect_parallel_write_run(calls, 0)
    assert [call.id for call in run] == ["c1"]
    # shell 之后的独立 edit 可再次成段
    assert [call.id for call in collect_parallel_write_run(calls, 2)] == ["c3"]


def test_patch_action_is_unknown_footprint_and_serial():
    calls = [patch_call(), edit_call("/a.py", call_id="c2")]
    assert [call.id for call in collect_parallel_write_run(calls, 0)] == []
    assert [call.id for call in collect_parallel_write_run(calls, 1)] == ["c2"]


def test_respects_max_parallel_batch():
    calls = [edit_call(f"/f{i}.py", call_id=f"c{i}") for i in range(MAX_PARALLEL_WRITE_BATCH + 2)]
    run = collect_parallel_write_run(calls, 0)
    assert len(run) == MAX_PARALLEL_WRITE_BATCH


def test_single_qualifying_call_returns_length_one():
    calls = [edit_call("/a.py", call_id="c1"), shell_call()]
    assert [call.id for call in collect_parallel_write_run(calls, 0)] == ["c1"]
