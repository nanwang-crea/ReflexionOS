from typing import Any

from pydantic import BaseModel, Field


class BrowserActionResult(BaseModel):
    success: bool
    action: str
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
