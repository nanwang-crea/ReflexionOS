from pydantic import BaseModel, Field
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
    id: str = Field(default_factory=lambda: f"proj-{uuid.uuid4().hex[:8]}")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        from_attributes = True
