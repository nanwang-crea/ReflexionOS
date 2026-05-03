# backend/tests/test_security/test_effect_category.py
import enum
import pytest

from app.security.effect_category import (
    EffectCategory,
    EFFECT_DANGER_LEVEL,
    EFFECT_ACTION_MAP,
    most_dangerous,
)
from app.security.command_policy import CommandAction


class TestEffectCategory:
    def test_is_string_enum(self):
        assert issubclass(EffectCategory, str)
        assert issubclass(EffectCategory, enum.Enum)

    def test_categories_exist(self):
        assert EffectCategory.READ_ONLY == "read_only"
        assert EffectCategory.WRITE_PROJECT == "write_project"
        assert EffectCategory.WRITE_SYSTEM == "write_system"
        assert EffectCategory.DESTRUCTIVE == "destructive"
        assert EffectCategory.ESCALATE == "escalate"
        assert EffectCategory.NETWORK_OUT == "network_out"
        assert EffectCategory.CODE_GEN == "code_gen"
        assert EffectCategory.UNKNOWN == "unknown"


class TestDangerLevel:
    def test_danger_level_ordering(self):
        assert EFFECT_DANGER_LEVEL[EffectCategory.READ_ONLY] < EFFECT_DANGER_LEVEL[EffectCategory.WRITE_PROJECT]
        assert EFFECT_DANGER_LEVEL[EffectCategory.WRITE_PROJECT] < EFFECT_DANGER_LEVEL[EffectCategory.CODE_GEN]
        assert EFFECT_DANGER_LEVEL[EffectCategory.CODE_GEN] < EFFECT_DANGER_LEVEL[EffectCategory.NETWORK_OUT]
        assert EFFECT_DANGER_LEVEL[EffectCategory.NETWORK_OUT] < EFFECT_DANGER_LEVEL[EffectCategory.WRITE_SYSTEM]
        assert EFFECT_DANGER_LEVEL[EffectCategory.WRITE_SYSTEM] < EFFECT_DANGER_LEVEL[EffectCategory.DESTRUCTIVE]
        assert EFFECT_DANGER_LEVEL[EffectCategory.DESTRUCTIVE] < EFFECT_DANGER_LEVEL[EffectCategory.ESCALATE]

    def test_unknown_is_between_code_gen_and_network_out(self):
        assert EFFECT_DANGER_LEVEL[EffectCategory.UNKNOWN] > EFFECT_DANGER_LEVEL[EffectCategory.WRITE_PROJECT]
        assert EFFECT_DANGER_LEVEL[EffectCategory.UNKNOWN] < EFFECT_DANGER_LEVEL[EffectCategory.ESCALATE]


class TestActionMapping:
    def test_read_only_allows(self):
        assert EFFECT_ACTION_MAP[EffectCategory.READ_ONLY] == CommandAction.ALLOW

    def test_write_project_allows(self):
        assert EFFECT_ACTION_MAP[EffectCategory.WRITE_PROJECT] == CommandAction.ALLOW

    def test_write_system_requires_approval(self):
        assert EFFECT_ACTION_MAP[EffectCategory.WRITE_SYSTEM] == CommandAction.REQUIRE_APPROVAL

    def test_destructive_requires_approval(self):
        assert EFFECT_ACTION_MAP[EffectCategory.DESTRUCTIVE] == CommandAction.REQUIRE_APPROVAL

    def test_escalate_denies(self):
        assert EFFECT_ACTION_MAP[EffectCategory.ESCALATE] == CommandAction.DENY

    def test_network_out_requires_approval(self):
        assert EFFECT_ACTION_MAP[EffectCategory.NETWORK_OUT] == CommandAction.REQUIRE_APPROVAL

    def test_code_gen_requires_approval(self):
        assert EFFECT_ACTION_MAP[EffectCategory.CODE_GEN] == CommandAction.REQUIRE_APPROVAL

    def test_unknown_requires_approval(self):
        assert EFFECT_ACTION_MAP[EffectCategory.UNKNOWN] == CommandAction.REQUIRE_APPROVAL

    def test_all_categories_have_action(self):
        for cat in EffectCategory:
            assert cat in EFFECT_ACTION_MAP, f"Missing action for {cat}"


class TestMostDangerous:
    def test_single_category(self):
        assert most_dangerous([EffectCategory.READ_ONLY]) == EffectCategory.READ_ONLY

    def test_read_only_and_write_project(self):
        assert most_dangerous([EffectCategory.READ_ONLY, EffectCategory.WRITE_PROJECT]) == EffectCategory.WRITE_PROJECT

    def test_pipe_chain_escalate_wins(self):
        assert most_dangerous([EffectCategory.NETWORK_OUT, EffectCategory.ESCALATE]) == EffectCategory.ESCALATE

    def test_pipe_chain_destructive_wins_over_write(self):
        assert most_dangerous([EffectCategory.WRITE_PROJECT, EffectCategory.DESTRUCTIVE]) == EffectCategory.DESTRUCTIVE

    def test_empty_list_raises(self):
        with pytest.raises(ValueError):
            most_dangerous([])
