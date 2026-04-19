from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
import uuid


class ProjectBase(BaseModel):
    name: str
    path: str
    language: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: f"proj-{uuid.uuid4().hex[:8]}")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
