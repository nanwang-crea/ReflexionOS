# 会话快照相关模型：用于一次性返回某个会话的完整（或分页）对话历史，
# 以及“开始新回合”操作返回的结果结构。
from pydantic import BaseModel

from app.models.conversation import Message, Run, Turn
from app.models.session import Session


class ConversationSnapshot(BaseModel):
    """会话快照：包含会话基本信息及其下的回合、运行、消息列表，支持分页加载历史消息
    （has_more 标记是否还有更早的数据，next_before_turn_id 为下一页起始回合 id）。"""

    session: Session
    turns: list[Turn]
    runs: list[Run]
    messages: list[Message]
    has_more: bool = False
    next_before_turn_id: str | None = None


class StartTurnResult(BaseModel):
    """开始新回合的返回结果：新创建的回合、其首次运行，以及用户发出的初始消息。"""

    turn: Turn
    run: Run
    user_message: Message
