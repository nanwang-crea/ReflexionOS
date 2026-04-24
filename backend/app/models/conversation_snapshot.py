from pydantic import BaseModel

from app.models.conversation import Message, Run, Turn
from app.models.session import Session


class ConversationSnapshot(BaseModel):
    session: Session
    turns: list[Turn]
    runs: list[Run]
    messages: list[Message]


class StartTurnResult(BaseModel):
    turn: Turn
    run: Run
    user_message: Message
