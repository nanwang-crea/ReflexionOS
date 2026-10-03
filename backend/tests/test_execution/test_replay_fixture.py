"""
文件功能：回放夹具模型（replay_fixture）的单元测试
文件描述：验证 ReplayFixture 及其子模型的 JSON round-trip 一致性与
         pydantic 校验行为（缺必填字段、method 枚举非法时拒绝加载）。
"""

import pytest
from pydantic import ValidationError

from tests.support.replay_fixture import (
    ReplayFixture,
    load_fixture,
    save_fixture,
)


def _build_fixture() -> ReplayFixture:
    """构造一个覆盖全部字段的合法夹具对象，供 round-trip 测试使用。

    入参：无。
    出参：ReplayFixture - 含两条响应（stream 带工具调用 + complete 纯文本）。
    """
    return ReplayFixture.model_validate(
        {
            "scenario": "round-trip",
            "description": "round-trip 测试夹具",
            "recorded_at": "2026-10-02",
            "model": "deepseek-chat",
            "task": "总结这个仓库",
            "responses": [
                {
                    "method": "stream",
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "grep", "arguments": {"pattern": "class"}}
                    ],
                    "finish_reason": "tool_calls",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
                {
                    "method": "complete",
                    "content": "总结内容",
                    "finish_reason": "stop",
                },
            ],
            "expected": {
                "loop_status": "completed",
                "event_sequence": ["run:start", "llm:content", "run:complete"],
            },
        }
    )


class TestFixtureRoundTrip:
    """F-01：夹具保存后重新加载，全字段一致"""

    def test_round_trip(self, tmp_path):
        """构造夹具 → save 到临时目录 → load，断言完全相等。

        入参：tmp_path (pytest 内建临时目录 fixture)。
        出参：无（断言失败即测试失败）。
        """
        fixture = _build_fixture()
        path = tmp_path / "round-trip.json"

        save_fixture(fixture, path)
        loaded = load_fixture(path)

        assert loaded == fixture

    def test_saved_file_is_human_readable_json(self, tmp_path):
        """保存的 JSON 应为带缩进、非 ASCII 不转义的可读格式。

        入参：tmp_path。
        出参：无。
        """
        path = tmp_path / "readable.json"
        save_fixture(_build_fixture(), path)

        text = path.read_text(encoding="utf-8")
        assert "总结这个仓库" in text  # ensure_ascii=False
        assert "\n  " in text  # indent=2


class TestFixtureValidation:
    """F-02 / F-03：非法夹具被拒绝"""

    def test_missing_responses_rejected(self, tmp_path):
        """缺少必填字段 responses 的 JSON 应抛 ValidationError。

        入参：tmp_path。
        出参：无。
        """
        path = tmp_path / "bad.json"
        path.write_text(
            '{"scenario": "x", "expected": {"loop_status": "completed", "event_sequence": []}}',
            encoding="utf-8",
        )

        with pytest.raises(ValidationError):
            load_fixture(path)

    def test_invalid_method_rejected(self, tmp_path):
        """method 取值不在 complete/stream 枚举内应抛 ValidationError。

        入参：tmp_path。
        出参：无。
        """
        fixture = _build_fixture().model_dump()
        fixture["responses"][0]["method"] = "invalid"
        path = tmp_path / "bad-method.json"
        import json

        path.write_text(json.dumps(fixture), encoding="utf-8")

        with pytest.raises(ValidationError):
            load_fixture(path)


class TestApprovalDecisions:
    """approval_decisions 字段：round-trip / 向后兼容 / 枚举校验"""

    def test_round_trip_with_approval_decisions(self, tmp_path):
        """带审批决策脚本的夹具保存后重新加载，决策字段完全一致。

        入参：tmp_path。出参：无。
        """
        fixture = _build_fixture().model_dump()
        fixture["approval_decisions"] = [
            {
                "tool_call_id": "call_appr_1",
                "action": "approve",
                "output": "审批通过后的工具输出",
                "success": True,
            },
            {"tool_call_id": "call_appr_2", "action": "reject"},
        ]
        path = tmp_path / "with-decisions.json"
        import json

        path.write_text(json.dumps(fixture), encoding="utf-8")
        loaded = load_fixture(path)

        assert len(loaded.approval_decisions) == 2
        assert loaded.approval_decisions[0].action == "approve"
        assert loaded.approval_decisions[0].output == "审批通过后的工具输出"
        assert loaded.approval_decisions[1].action == "reject"
        assert loaded.approval_decisions[1].success is True  # 默认值

    def test_legacy_fixture_without_decisions_defaults_empty(self, tmp_path):
        """旧格式夹具（无 approval_decisions 字段）加载后默认为空列表。

        入参：tmp_path。出参：无。
        """
        path = tmp_path / "legacy.json"
        save_fixture(_build_fixture(), path)  # _build_fixture 不含决策字段

        loaded = load_fixture(path)

        assert loaded.approval_decisions == []

    def test_invalid_action_rejected(self, tmp_path):
        """action 取值不在 approve/reject 枚举内应抛 ValidationError。

        入参：tmp_path。出参：无。
        """
        fixture = _build_fixture().model_dump()
        fixture["approval_decisions"] = [
            {"tool_call_id": "c1", "action": "maybe"}
        ]
        path = tmp_path / "bad-action.json"
        import json

        path.write_text(json.dumps(fixture), encoding="utf-8")

        with pytest.raises(ValidationError):
            load_fixture(path)
