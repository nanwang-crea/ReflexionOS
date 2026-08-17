# 文件功能：会话附件（图片）上传与获取相关的 API 路由
# 文件描述：处理会话内图片附件的上传（校验类型/大小、落盘保存）和读取
#           （按 attachment_id 查找文件并以正确 MIME 类型返回）。
# 核心逻辑：上传时校验会话存在性、文件类型、大小限制后保存到
#           storage/uploads/{session_id}/ 目录；获取时通过 AttachmentService
#           定位文件并推断 MIME 类型返回。
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.storage.database import db
from app.storage.repositories.session_repo import SessionRepository
from app.services.attachment_service import get_attachment_service

router = APIRouter(prefix="/api", tags=["upload"])
session_repo = SessionRepository(db)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/sessions/{session_id}/upload")
async def upload_image(
    session_id: str,
    file: UploadFile = File(...),
) -> dict:
    """
    POST /api/sessions/{session_id}/upload：为指定会话上传图片附件。
    入参：session_id（路径参数，会话 ID）；file（表单文件，图片文件，
          仅支持 image/* 类型，大小不超过 MAX_FILE_SIZE）。
    逻辑：校验会话存在 -> 校验文件类型为图片 -> 读取内容并校验大小 ->
          按时间戳+随机 ID 生成文件名保存到 storage/uploads/{session_id}/ 目录。
    出参：dict，包含 attachment_id（附件 ID）、file_path（保存路径）、
          file_size（文件大小）、mime_type（MIME 类型）；
          会话不存在或校验失败时抛出 HTTPException（404/400）。
    """
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


@router.get("/sessions/{session_id}/attachments/{attachment_id}")
async def get_attachment(session_id: str, attachment_id: str):
    """
    GET /api/sessions/{session_id}/attachments/{attachment_id}：获取会话中的附件图片文件。
    入参：session_id（路径参数，会话 ID）；attachment_id（路径参数，附件 ID）。
    逻辑：校验会话存在 -> 通过 AttachmentService 按 session_id/attachment_id
          查找实际文件路径 -> 推断文件 MIME 类型。
    出参：FileResponse（图片文件流及对应 MIME 类型）；
          会话或附件不存在时抛出 HTTPException(404)。
    """
    # 验证 session 存在
    session = session_repo.get(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")

    # 使用 AttachmentService 查找文件
    attachment_service = get_attachment_service()
    file_path = attachment_service.find_attachment_file(session_id, attachment_id)

    if not file_path:
        raise HTTPException(404, "附件不存在")

    # 推断 MIME 类型
    mime_type = attachment_service.infer_mime_type(file_path)

    return FileResponse(file_path, media_type=mime_type)
