# 文件功能：会话（Session）管理相关的 API 路由
# 文件描述：提供会话的创建、按项目列出会话、获取对话快照、更新会话信息、
#           重置会话、删除会话等接口。
# 核心逻辑：路由层多为对 session_service / conversation_service / agent_service
#           的薄封装；删除会话时需要依次清理浏览器资源、安全状态、附件文件，
#           各步骤独立 try/except 记录警告日志，避免某一步失败阻塞整体删除流程。
import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.app_services import agent_service
from app.errors import NotFoundError, NotFoundValueError, value_error_to_app_error
from app.models.conversation_snapshot import ConversationSnapshot
from app.models.session import Session, SessionCreate, SessionUpdate
from app.services.chat_archive_service import (
    MAX_ARCHIVE_BYTES,
    ChatArchiveError,
    build_chat_archive,
    dumps_archive,
    import_chat_archive,
)
from app.services.conversation_service import conversation_service
from app.services.session_service import session_service

router = APIRouter(prefix="/api", tags=["sessions"])
logger = logging.getLogger(__name__)


@router.post("/projects/{project_id}/sessions", response_model=Session)
async def create_session(project_id: str, payload: SessionCreate):
    """
    POST /api/projects/{project_id}/sessions：在指定项目下创建新会话。
    入参：project_id（路径参数，项目 ID）；payload（请求体，会话创建参数）。
    逻辑：调用 session_service.create_session 创建并持久化会话记录。
    出参：Session（创建后的会话信息）。
    """
    try:
        return session_service.create_session(project_id, payload)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc


@router.get("/projects/{project_id}/sessions", response_model=list[Session])
async def list_project_sessions(project_id: str):
    """
    GET /api/projects/{project_id}/sessions：列出指定项目下的所有会话。
    入参：project_id（路径参数，项目 ID）。
    逻辑：调用 session_service.list_project_sessions 查询会话列表。
    出参：list[Session]（会话列表）。
    """
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
    """
    GET /api/sessions/{session_id}/conversation：分页获取会话的对话快照（消息记录）。
    入参：session_id（路径参数，会话 ID）；limit（查询参数，返回条数上限，默认 20）；
          before_turn（查询参数，游标，获取该轮次之前的消息，空字符串会被归一化为 None）。
    逻辑：归一化 before_turn 后调用 conversation_service.get_snapshot 分页读取对话内容。
    出参：ConversationSnapshot（对话快照，含消息列表及分页信息）。
    """
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
    """
    PATCH /api/sessions/{session_id}：更新会话信息（如标题等）。
    入参：session_id（路径参数，会话 ID）；payload（请求体，待更新字段）。
    逻辑：调用 session_service.update_session 执行局部更新。
    出参：Session（更新后的会话信息）。
    """
    try:
        return session_service.update_session(session_id, payload)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc


@router.post("/sessions/{session_id}/reset", response_model=Session)
async def reset_session(session_id: str):
    """
    POST /api/sessions/{session_id}/reset：重置会话状态（如清空对话上下文）。
    入参：session_id（路径参数，会话 ID）。
    逻辑：调用 agent_service.reset_session 执行会话重置。
    出参：Session（重置后的会话信息）。
    """
    try:
        return await agent_service.reset_session(session_id)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """
    DELETE /api/sessions/{session_id}：删除指定会话及其关联资源。
    入参：session_id（路径参数，会话 ID）。
    逻辑：依次清理浏览器资源、会话安全状态、附件文件（各步骤失败仅记录
          警告日志、不中断流程），最后删除会话数据本身。
    出参：dict，包含删除成功提示信息 message；会话不存在等业务错误抛出对应异常。
    """
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


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str):
    """
    GET /api/sessions/{session_id}/export：把会话导出为 .reflexion-chat.json 归档下载。
    入参：session_id（路径参数，会话 ID）。
    逻辑：会话存在且有活跃 Run 时拒绝导出（归档只含已终态的历史）；
          按快照折叠为 reflexion-chat v1 JSON（消息 + 思考 + 工具只读记录），
          以附件形式下发（文件名带会话 ID，UTF-8 编码）。
    出参：JSON 文件下载；错误以 HTTPException/400 返回（会话不存在/运行中/空会话）。
    """
    try:
        snapshot = conversation_service.get_snapshot(session_id)
        from app.services.agent_service import resolve_active_run_id_from_conversation
        if resolve_active_run_id_from_conversation(snapshot) is not None:
            raise ChatArchiveError("会话正在运行中，请先停止或等待运行结束后再导出")
        session = session_service.get_session(session_id)
        archive = build_chat_archive(snapshot, session)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="会话") from exc

    payload = dumps_archive(archive)
    filename = quote(f"reflexion-chat-{session_id}.json")
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/sessions/import")
async def import_session_archive(file: UploadFile, project_id: str = Form(...)):
    """
    POST /api/sessions/import：上传 .reflexion-chat.json 归档，在指定项目下重建为新会话。
    入参：file（multipart 文件，归档 JSON，上限 16MiB）；project_id（表单字段，目标项目）。
    逻辑：读取并解析归档 → chat_archive_service.import_chat_archive 校验并在
          单次补偿语义下重建（新会话/新 ID，工具记录为惰性只读投影，不恢复任何
          运行时状态）；失败时已创建的会话会被回滚删除。
    出参：dict（session_id/title/imported_messages/imported_tools）。
    """
    payload = await file.read()
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=400, detail=f"归档文件超过 {MAX_ARCHIVE_BYTES // (1024 * 1024)}MiB 上限")
    try:
        archive = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"归档不是有效的 UTF-8 JSON: {exc}") from exc

    try:
        return import_chat_archive(
            conversation_service,
            session_service,
            project_id=project_id,
            archive=archive,
        )
    except ChatArchiveError as exc:
        # 结构/内容非法：400
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundValueError as exc:
        # 目标项目不存在：404
        raise NotFoundError(resource="项目", message=str(exc)) from exc
