import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.storage.database import db
from app.storage.repositories.session_repo import SessionRepository

router = APIRouter(prefix="/api", tags=["upload"])
session_repo = SessionRepository(db)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/sessions/{session_id}/upload")
async def upload_image(
    session_id: str,
    file: UploadFile = File(...),
) -> dict:
    """上传图片附件"""
    # 1. 验证 session 存在
    session = session_repo.get(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")

    # 2. 验证文件类型
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "只支持图片文件（PNG, JPG, WEBP）")

    # 3. 读取并验证文件大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"图片大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）")

    # 4. 保存文件
    upload_dir = Path("storage/uploads") / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    file_id = uuid.uuid4().hex[:8]
    file_ext = Path(file.filename).suffix if file.filename else ".png"
    file_path = upload_dir / f"{timestamp}_{file_id}{file_ext}"

    with open(file_path, "wb") as f:
        f.write(content)

    # 5. 返回 attachment 信息
    return {
        "attachment_id": f"att_{file_id}",
        "file_path": str(file_path),
        "file_size": len(content),
        "mime_type": file.content_type
    }
