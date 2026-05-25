from pydantic import BaseModel, ConfigDict


class FileContentResponse(BaseModel):
    content: str
    language: str
    exists: bool


class FileDiffContentResponse(BaseModel):
    original: str
    modified: str
    language: str


class FileWriteRequest(BaseModel):
    project_id: str
    path: str
    content: str


class FileWriteResponse(BaseModel):
    success: bool
    error: str | None = None
