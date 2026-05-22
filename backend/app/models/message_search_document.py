from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageSearchDocument(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    turn_id: str
    run_id: str | None = None
    role: str
    message_type: str
    turn_index: int
    turn_message_index: int
    search_text: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
