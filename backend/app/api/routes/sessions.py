import logging

from fastapi import APIRouter

from app.app_services import agent_service
from app.errors import value_error_to_app_error
from app.models.conversation_snapshot import ConversationSnapshot
from app.models.session import Session, SessionCreate, SessionUpdate
from app.services.conversation_service import conversation_service
from app.services.session_service import session_service

router = APIRouter(prefix="/api", tags=["sessions"])
logger = logging.getLogger(__name__)


@router.post("/projects/{project_id}/sessions", response_model=Session)
async def create_session(project_id: str, payload: SessionCreate):
    try:
        return session_service.create_session(project_id, payload)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc


@router.get("/projects/{project_id}/sessions", response_model=list[Session])
async def list_project_sessions(project_id: str):
    try:
        return session_service.list_project_sessions(project_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc


@router.get("/sessions/{session_id}/conversation", response_model=ConversationSnapshot)
async def get_session_conversation(
    session_id: str,
    limit: int = 20,
    before_turn: str | None = None,
):
    try:
        normalized_before_turn = before_turn or None
        return conversation_service.get_snapshot(
            session_id,
            limit=limit,
            before_turn=normalized_before_turn,
        )
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc


@router.patch("/sessions/{session_id}", response_model=Session)
async def update_session(session_id: str, payload: SessionUpdate):
    try:
        return session_service.update_session(session_id, payload)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc


@router.post("/sessions/{session_id}/reset", response_model=Session)
async def reset_session(session_id: str):
    try:
        return await agent_service.reset_session(session_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        # 清理浏览器资源
        try:
            await agent_service.cleanup_browser_for_session(session_id)
        except Exception:
            logger.warning(
                "删除会话时清理浏览器资源失败: session_id=%s",
                session_id,
                exc_info=True,
            )
        try:
            agent_service.cleanup_session_security_state(session_id)
        except Exception:
            logger.warning(
                "删除会话时清理安全状态失败: session_id=%s",
                session_id,
                exc_info=True,
            )

        # 清理附件文件
        try:
            from app.services.attachment_service import get_attachment_service
            attachment_service = get_attachment_service()
            attachment_service.cleanup_session_attachments(session_id)
        except Exception:
            logger.warning(
                "删除会话时清理附件失败: session_id=%s",
                session_id,
                exc_info=True,
            )

        # 删除会话数据
        session_service.delete_session(session_id)
        return {"message": "会话已删除"}
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc
