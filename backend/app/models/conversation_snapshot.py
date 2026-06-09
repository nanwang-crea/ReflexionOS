from pydantic import BaseModel

from app.models.conversation import Message, Run, Turn
from app.models.session import Session


class ConversationSnapshot(BaseModel):
    session: Session
    turns: list[Turn]
    runs: list[Run]
    messages: list[Message]
    has_more: bool = False
    next_before_turn_id: str | None = None


class StartTurnResult(BaseModel):
    turn: Turn
    run: Run
    user_message: Message
