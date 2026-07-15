# 权限模式（PermissionMode）与 resolve_action 决策函数单测
import pytest

from app.security.permission_mode import PermissionMode, resolve_action
from app.security.effect_category import EffectCategory, CommandAction


class TestPermissionMode:
    def test_yolo_local_open_no_sandbox_deny(self):
        assert resolve_action(PermissionMode.YOLO, EffectCategory.READ_ONLY, sandbox_available=False) == CommandAction.DENY

    def test_yolo_local_open_with_sandbox(self):
        for cat in [EffectCategory.READ_ONLY, EffectCategory.WRITE_PROJECT, EffectCategory.DESTRUCTIVE]:
            assert resolve_action(PermissionMode.YOLO, cat, sandbox_available=True) == CommandAction.ALLOW

    def test_yolo_network_still_requires_approval(self):
        # YOLO 本地全放行；NETWORK_OUT 不受 PermissionMode 影响，始终走 EFFECT_ACTION_MAP 映射
        assert resolve_action(PermissionMode.YOLO, EffectCategory.NETWORK_OUT, sandbox_available=True) == CommandAction.REQUIRE_APPROVAL

    def test_yolo_escalate_always_deny(self):
        assert resolve_action(PermissionMode.YOLO, EffectCategory.ESCALATE, sandbox_available=True) == CommandAction.DENY

    def test_ask_read_only_allow(self):
        assert resolve_action(PermissionMode.ASK, EffectCategory.READ_ONLY, sandbox_available=True) == CommandAction.ALLOW

    def test_ask_write_project_requires_approval(self):
        assert resolve_action(PermissionMode.ASK, EffectCategory.WRITE_PROJECT, sandbox_available=True) == CommandAction.REQUIRE_APPROVAL

    def test_auto_write_project_allow(self):
        assert resolve_action(PermissionMode.AUTO, EffectCategory.WRITE_PROJECT, sandbox_available=True) == CommandAction.ALLOW

    def test_auto_destructive_requires_approval(self):
        assert resolve_action(PermissionMode.AUTO, EffectCategory.DESTRUCTIVE, sandbox_available=True) == CommandAction.REQUIRE_APPROVAL

    def test_auto_unknown_requires_approval(self):
        assert resolve_action(PermissionMode.AUTO, EffectCategory.UNKNOWN, sandbox_available=True) == CommandAction.REQUIRE_APPROVAL

    @pytest.mark.parametrize("mode", list(PermissionMode))
    def test_escalate_always_deny(self, mode):
        assert resolve_action(mode, EffectCategory.ESCALATE, sandbox_available=True) == CommandAction.DENY

    def test_no_sandbox_ask_still_works(self):
        assert resolve_action(PermissionMode.ASK, EffectCategory.READ_ONLY, sandbox_available=False) == CommandAction.ALLOW
        assert resolve_action(PermissionMode.ASK, EffectCategory.WRITE_PROJECT, sandbox_available=False) == CommandAction.REQUIRE_APPROVAL
