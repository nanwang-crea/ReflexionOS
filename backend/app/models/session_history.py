from datetime import datetime

from pydantic import BaseModel, Field


class SessionHistoryItemDto(BaseModel):
    id: str
    type: str
    content: str = ""
    receipt_status: str | None = None
    details: list[dict] = Field(default_factory=list)
    created_at: datetime


class SessionHistoryRoundDto(BaseModel):
    id: str
    created_at: datetime
    items: list[SessionHistoryItemDto] = Field(default_factory=list)


class SessionHistoryResponse(BaseModel):
    session_id: str
    project_id: str | None = None
    rounds: list[SessionHistoryRoundDto] = Field(default_factory=list)
