# 权限模式：控制本地操作审批行为
from __future__ import annotations
import enum
from app.security.effect_category import CommandAction, EffectCategory


class PermissionMode(str, enum.Enum):
    """Session-level execution modes.

    ASK keeps a human in the loop for anything non-read-only, AUTO follows the
    default effect map, and YOLO skips most local approvals but still respects
    hard safety boundaries such as sandbox availability and outbound network
    controls.
    """
    ASK = "ask"
    AUTO = "auto"
    YOLO = "yolo"


def resolve_action(
    mode: PermissionMode,
    category: EffectCategory,
    *,
    sandbox_available: bool = True,
) -> CommandAction:
    """Resolve the final action for an effect under the active mode.

    NETWORK_OUT intentionally stays approval-gated across ASK/AUTO/YOLO because
    exfiltration risk is orthogonal to local convenience. YOLO also requires a
    sandbox; otherwise it would silently turn into unrestricted host execution.
    """
    if category == EffectCategory.ESCALATE:
        return CommandAction.DENY
    if mode == PermissionMode.YOLO:
        if not sandbox_available:
            return CommandAction.DENY
        # 确保 YOLO 下网络不被 ALLOW——网络审批不受 YOLO 影响
        if category == EffectCategory.NETWORK_OUT:
            return CommandAction.REQUIRE_APPROVAL
        return CommandAction.ALLOW
    if mode == PermissionMode.ASK:
        if category == EffectCategory.READ_ONLY:
            return CommandAction.ALLOW
        return CommandAction.REQUIRE_APPROVAL
    from app.security.effect_category import EFFECT_ACTION_MAP
    return EFFECT_ACTION_MAP[category]
