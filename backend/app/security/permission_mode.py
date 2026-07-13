# 权限模式：控制本地操作审批行为
from __future__ import annotations
import enum
from app.security.effect_category import CommandAction, EffectCategory


class PermissionMode(str, enum.Enum):
    """三档权限模式（会话级）。
    - ASK:  每步操作都弹审批（READ_ONLY 除外）
    - AUTO: 默认模式，按 EFFECT_ACTION_MAP 自动决策
    - YOLO: 本地操作全部放行，网络审批不受 PermissionMode 影响
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
    """根据权限模式和效果分类决定最终动作。

    NETWORK_OUT 不受 PermissionMode 影响（无论 ASK/AUTO/YOLO 都返回 REQUIRE_APPROVAL），
    因为网络命令的审批完全由 EFFECT_ACTION_MAP 定义。
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
