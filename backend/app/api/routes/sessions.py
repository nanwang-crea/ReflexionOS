from fastapi import APIRouter, HTTPException

from app.models.conversation_snapshot import ConversationSnapshot
from app.models.session import Session
from app.services.conversation_service import conversation_service
from app.services.session_service import SessionCreate, SessionUpdate, session_service

router = APIRouter(prefix="/api", tags=["sessions"])


@router.post("/projects/{project_id}/sessions", response_model=Session)
async def create_session(project_id: str, payload: SessionCreate):
    try:
        return session_service.create_session(project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/sessions", response_model=list[Session])
async def list_project_sessions(project_id: str):
    try:
        return session_service.list_project_sessions(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sessions/{session_id}", response_model=Session)
async def get_session(session_id: str):
    session = session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get("/sessions/{session_id}/conversation", response_model=ConversationSnapshot)
async def get_session_conversation(session_id: str):
    try:
        return conversation_service.get_snapshot(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/sessions/{session_id}", response_model=Session)
async def update_session(session_id: str, payload: SessionUpdate):
    try:
        return session_service.update_session(session_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        session_service.delete_session(session_id)
        return {"message": "会话已删除"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
