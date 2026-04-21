from datetime import datetime

from pydantic import BaseModel, Field


class TranscriptRecord(BaseModel):
    id: str
    execution_id: str
    session_id: str
    project_id: str
    item_type: str
    content: str = ""
    receipt_status: str | None = None
    details_json: list[dict] = Field(default_factory=list)
    sequence: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
