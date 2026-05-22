from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_SESSION_TITLE = "新建聊天"


class SessionCreate(BaseModel):
    title: str | None = None
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None


class Session(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str = DEFAULT_SESSION_TITLE
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None
    last_event_seq: int = 0
    active_turn_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def default_updated_at_to_created_at(self):
        if self.updated_at is None:
            self.updated_at = self.created_at
        return self
