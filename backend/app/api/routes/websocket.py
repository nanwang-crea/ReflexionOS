import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.websocket_manager import ws_manager
from app.services.agent_service import agent_service
from app.services.conversation_service import conversation_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _send_error(websocket: WebSocket, *, code: str, message: str):
    await websocket.send_json(
        {
            "type": "conversation.error",
            "data": {
                "code": code,
                "message": message,
            },
        }
    )


async def _send_synced(websocket: WebSocket, *, session_id: str):
    snapshot = conversation_service.get_snapshot(session_id)
    await websocket.send_json(
        {
            "type": "conversation.synced",
            "data": {
                "session_id": session_id,
                "last_event_seq": snapshot.session.last_event_seq,
            },
        }
    )


async def _send_resync_required(websocket: WebSocket, *, session_id: str, after_seq: int):
    await websocket.send_json(
        {
            "type": "conversation.resync_required",
            "data": {
                "session_id": session_id,
                "after_seq": after_seq,
                "reason": "stale_after_seq",
            },
        }
    )


async def _send_live_state(websocket: WebSocket, *, session_id: str):
    live_state = agent_service.get_live_state(session_id)
    if live_state is None:
        return
    await websocket.send_json(
        {
            "type": "conversation.live_state",
            "data": live_state,
        }
    )


@router.websocket("/ws/sessions/{session_id}/conversation")
async def websocket_conversation(websocket: WebSocket, session_id: str):
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            raw_message = await websocket.receive_text()

            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await _send_error(websocket, code="invalid_json", message="无效 JSON 消息")
                continue

            msg_type = message.get("type")
            msg_data = message.get("data", {})

            if msg_type == "conversation.sync":
                try:
                    after_seq = int(msg_data.get("after_seq", 0))
                except (TypeError, ValueError):
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="after_seq 必须是整数",
                    )
                    continue

                try:
                    if conversation_service.requires_resync(session_id, after_seq):
                        await _send_resync_required(
                            websocket,
                            session_id=session_id,
                            after_seq=after_seq,
                        )
                        continue
                    events = conversation_service.list_events_after(session_id, after_seq)
                except ValueError as exc:
                    await _send_error(websocket, code="not_found", message=str(exc))
                    continue

                for event in events:
                    await websocket.send_json(
                        {
                            "type": "conversation.event",
                            "data": event.model_dump(mode="json"),
                        }
                    )

                try:
                    await _send_live_state(websocket, session_id=session_id)
                    await _send_synced(websocket, session_id=session_id)
                except ValueError as exc:
                    await _send_error(websocket, code="not_found", message=str(exc))
                continue

            if msg_type == "conversation.start_turn":
                content = msg_data.get("content")
                if not isinstance(content, str) or not content.strip():
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="content 不能为空",
                    )
                    continue

                provider_id = msg_data.get("provider_id")
                model_id = msg_data.get("model_id")

                try:
                    snapshot = conversation_service.get_snapshot(session_id)
                    await agent_service.start_turn(
                        project_id=snapshot.session.project_id,
                        session_id=session_id,
                        content=content,
                        provider_id=provider_id,
                        model_id=model_id,
                    )
                except ValueError as exc:
                    await _send_error(websocket, code="invalid_request", message=str(exc))
                    continue

                continue

            if msg_type == "conversation.cancel_run":
                run_id = msg_data.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="run_id 不能为空",
                    )
                    continue

                try:
                    await agent_service.cancel_run(run_id)
                except ValueError as exc:
                    await _send_error(websocket, code="invalid_request", message=str(exc))
                continue

            await _send_error(
                websocket,
                code="invalid_request",
                message=f"未知消息类型: {msg_type}",
            )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
        logger.info("WebSocket 断开连接: %s", session_id)
    except Exception as exc:  # pragma: no cover
        logger.error("WebSocket 错误: %s", exc)
        ws_manager.disconnect(websocket, session_id)
