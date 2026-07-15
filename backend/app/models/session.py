from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_SESSION_TITLE = "新建聊天"


class SessionCreate(BaseModel):
    title: str | None = None
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None
    agent_mode: str | None = None
    permission_mode: str | None = None

    @field_validator("permission_mode")
    @classmethod
    def validate_permission_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in ("ask", "auto", "yolo"):
            raise ValueError(f"permission_mode 必须是 'ask'、'auto' 或 'yolo'，收到: {v}")
        return v


class Session(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str = DEFAULT_SESSION_TITLE
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None
    agent_mode: str = "build"
    permission_mode: str = "auto"
    last_event_seq: int = 0
    active_turn_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def default_updated_at_to_created_at(self):
        if self.updated_at is None:
            self.updated_at = self.created_at
        return self
