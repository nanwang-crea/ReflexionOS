# 权限模式：控制本地操作审批行为
# 定义会话级权限模式枚举（ASK/AUTO/YOLO）以及"效果分类 + 权限模式 -> 最终动作"的映射函数
# resolve_action。这是 command_policy.py 判定管线的最后一步：效果分类只回答"这个命令有多危险"，
# 而具体"危险到什么程度需要拦下来"取决于当前会话选择了哪种权限模式，两者职责分离。
from __future__ import annotations
import enum
from app.security.effect_category import CommandAction, EffectCategory


class PermissionMode(str, enum.Enum):
    """会话级执行模式。

    ASK 对任何非只读操作都要求人工审批；AUTO 遵循 EFFECT_ACTION_MAP 的默认映射；
    YOLO 跳过大多数本地审批，但仍然遵守硬性安全边界（如沙盒是否可用、
    对外网络请求始终需要审批）。
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
    """在给定权限模式下，把效果分类映射为最终动作。

    参数：
        mode: 当前会话的权限模式（ASK/AUTO/YOLO）。
        category: 命令的效果分类（EffectCategory）。
        sandbox_available: 是否有沙盒可用（仅关键字参数）；影响 YOLO 模式下能否放行。

    逻辑：
        1. ESCALATE（提权）无论何种模式一律 DENY——这是不可被任何权限模式绕过的硬边界。
        2. YOLO 模式：
           - 无沙盒可用时整体 DENY（否则 YOLO 会退化成无约束的主机执行，风险不可控）；
           - NETWORK_OUT 单独排除在"跳过审批"之外，始终 REQUIRE_APPROVAL
             （因为数据外泄风险与本地操作是否方便无关，不应该被 YOLO 图省事而放开）；
           - 其余分类直接 ALLOW。
        3. ASK 模式：只有 READ_ONLY 直接放行，其余任何有副作用的分类都要审批
           （最保守的模式，人工全程在环）。
        4. 其余情况（即 AUTO 模式）：直接查 EFFECT_ACTION_MAP 取默认映射。

    返回：
        最终的 CommandAction（ALLOW/REQUIRE_APPROVAL/DENY）。
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
