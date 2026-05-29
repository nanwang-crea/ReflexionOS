from uuid import uuid4

# 使用 12 位十六进制（48 bit），生日悖论下约 1600 万条记录才有 50% 碰撞概率
# 8 位（32 bit）仅约 65000 条就会 50% 碰撞，风险过高
_ID_HEX_LEN = 12


def new_event_id() -> str:
    return f"evt-{uuid4().hex[:_ID_HEX_LEN]}"


def new_message_id() -> str:
    return f"msg-{uuid4().hex[:_ID_HEX_LEN]}"


def new_run_id() -> str:
    return f"run-{uuid4().hex[:_ID_HEX_LEN]}"


def new_turn_id() -> str:
    return f"turn-{uuid4().hex[:_ID_HEX_LEN]}"


def new_session_id() -> str:
    return f"session-{uuid4().hex[:_ID_HEX_LEN]}"


def new_approval_id() -> str:
    return f"approval-{uuid4().hex[:_ID_HEX_LEN]}"
