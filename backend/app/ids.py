# 各类业务实体 ID 生成工具模块。
# 统一使用 `前缀-十六进制随机串` 格式，前缀标识实体类型，便于日志/调试中直接识别 ID 归属。

from uuid import uuid4

# 使用 12 位十六进制（48 bit），生日悖论下约 1600 万条记录才有 50% 碰撞概率
# 8 位（32 bit）仅约 65000 条就会 50% 碰撞，风险过高
_ID_HEX_LEN = 12


def new_event_id() -> str:
    """生成事件 ID，格式：evt-<12位十六进制随机串>。"""
    return f"evt-{uuid4().hex[:_ID_HEX_LEN]}"


def new_message_id() -> str:
    """生成消息 ID，格式：msg-<12位十六进制随机串>。"""
    return f"msg-{uuid4().hex[:_ID_HEX_LEN]}"


def new_run_id() -> str:
    """生成运行（Agent Run）ID，格式：run-<12位十六进制随机串>。"""
    return f"run-{uuid4().hex[:_ID_HEX_LEN]}"


def new_turn_id() -> str:
    """生成对话轮次（Turn）ID，格式：turn-<12位十六进制随机串>。"""
    return f"turn-{uuid4().hex[:_ID_HEX_LEN]}"


def new_session_id() -> str:
    """生成会话（Session）ID，格式：session-<12位十六进制随机串>。"""
    return f"session-{uuid4().hex[:_ID_HEX_LEN]}"


def new_approval_id() -> str:
    """生成审批（Approval）ID，格式：approval-<12位十六进制随机串>。"""
    return f"approval-{uuid4().hex[:_ID_HEX_LEN]}"
