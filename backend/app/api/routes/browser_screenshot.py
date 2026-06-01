import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/browser", tags=["browser"])

SCREENSHOT_BASE = Path(tempfile.gettempdir()) / "browser-screenshots"


@router.get("/screenshot")
async def get_screenshot(path: str = Query(..., description="Path to screenshot file")):
    real_path = Path(path).resolve()
    screenshot_base_real = SCREENSHOT_BASE.resolve()

    if not str(real_path).startswith(str(screenshot_base_real)):
        raise HTTPException(status_code=403, detail="Path outside allowed directory")

    if not real_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    return FileResponse(real_path, media_type="image/png")
