# backend/app/security/effect_category.py
# 效果分类与危险等级定义：本模块是整套命令安全体系的"分类词表"，
# 定义命令可能产生的效果类别（EffectCategory）、各类别的相对危险程度
# （EFFECT_DANGER_LEVEL，用于比较"谁更危险"）、以及默认情况下每种效果对应的动作
# （EFFECT_ACTION_MAP，被 permission_mode.resolve_action 在 AUTO 模式下直接使用）。
# command_policy.py 和 command_effect_registry.py 都依赖这里的枚举做分类判断。
import enum
import logging

logger = logging.getLogger(__name__)


class CommandAction(str, enum.Enum):
    """命令效果分类之后，最终要执行的动作。"""
    ALLOW = "allow"                       # 直接放行
    REQUIRE_APPROVAL = "require_approval"  # 需要人工审批后才能执行
    DENY = "deny"                          # 直接拒绝


class EffectCategory(str, enum.Enum):
    """命令效果分类（安全判定的核心维度）。

    按危险程度从低到高排列（具体数值见 EFFECT_DANGER_LEVEL）：
    只读 -> 项目内写 -> 系统级写 -> 破坏性 -> 提权 -> 对外网络 -> 内联代码 -> 未知。
    """

    READ_ONLY = "read_only"           # 无副作用
    WRITE_PROJECT = "write_project"   # 修改项目目录范围内的文件/依赖
    WRITE_SYSTEM = "write_system"     # 修改项目目录之外的系统状态
    DESTRUCTIVE = "destructive"       # 删除/覆盖文件
    ESCALATE = "escalate"             # 提权（sudo/su/shell 裸解释器等）
    NETWORK_OUT = "network_out"       # 对外发起网络请求
    CODE_GEN = "code_gen"             # 内联代码执行（如 -c/-e，内容无法静态审查）
    UNKNOWN = "unknown"               # 未识别的命令


# 各效果分类的危险等级（数值越大越危险），用于 most_dangerous 比较多个分类结果时取最坏情况。
EFFECT_DANGER_LEVEL: dict[EffectCategory, int] = {
    EffectCategory.READ_ONLY: 0,
    EffectCategory.WRITE_PROJECT: 1,
    EffectCategory.CODE_GEN: 2,
    EffectCategory.UNKNOWN: 3,
    EffectCategory.NETWORK_OUT: 4,
    EffectCategory.WRITE_SYSTEM: 5,
    EffectCategory.DESTRUCTIVE: 6,
    EffectCategory.ESCALATE: 7,
}

# 效果分类 -> 默认动作 的映射。AUTO 权限模式下由 permission_mode.resolve_action 直接查表使用；
# ASK/YOLO 模式则各自有独立规则，不完全依赖这张表（见 permission_mode.py）。
EFFECT_ACTION_MAP: dict[EffectCategory, CommandAction] = {
    EffectCategory.READ_ONLY: CommandAction.ALLOW,
    EffectCategory.WRITE_PROJECT: CommandAction.ALLOW,
    EffectCategory.WRITE_SYSTEM: CommandAction.REQUIRE_APPROVAL,
    EffectCategory.DESTRUCTIVE: CommandAction.REQUIRE_APPROVAL,
    EffectCategory.ESCALATE: CommandAction.DENY,
    EffectCategory.NETWORK_OUT: CommandAction.REQUIRE_APPROVAL,
    EffectCategory.CODE_GEN: CommandAction.REQUIRE_APPROVAL,
    EffectCategory.UNKNOWN: CommandAction.REQUIRE_APPROVAL,
}


def most_dangerous(categories: list[EffectCategory]) -> EffectCategory:
    """从一组效果分类中取出最危险的一个（按 EFFECT_DANGER_LEVEL 比较）。

    参数：
        categories: 效果分类列表（如命令链多个分段各自的分类结果）。

    逻辑：
        用 EFFECT_DANGER_LEVEL 作为排序 key，取 max。这是"按最坏情况判定"策略的
        核心实现：命令链中只要有一段危险，整条命令就要按那一段的危险级别处理，
        不能因为其他段是只读的而被平均/稀释掉风险。

    返回：
        危险等级最高的 EffectCategory。

    异常：
        列表为空时抛 ValueError（调用方应确保传入非空列表；这是防御性检查，
        避免 max() 对空序列抛出更难定位的 ValueError）。
    """
    if not categories:
        raise ValueError("categories list must not be empty")
    return max(categories, key=lambda c: EFFECT_DANGER_LEVEL[c])
