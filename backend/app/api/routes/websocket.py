# 文件功能：会话对话的 WebSocket 长连接路由
# 文件描述：客户端通过 /ws/sessions/{session_id}/conversation 建立长连接后，
#   以 JSON 消息进行双向通信：客户端发送 {"type": "...", "data": {...}} 格式的消息，
#   服务端处理后通过 send_ws_json 推送对应的响应/事件消息（如 conversation:event、
#   conversation:synced、conversation:error 等），实现会话消息同步、发起对话轮次、
#   取消运行、编辑重跑、工具调用审批、切换模式等能力
# 核心逻辑：连接建立后进入 while True 事件循环，每次 receive_text 读取一条消息，
#   按 msg_type 分支处理，每个分支处理完毕后 continue 回到循环顶部等待下一条消息；
#   出现 WebSocketDisconnect 或未捕获异常时退出循环并做连接清理
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.websocket_manager import send_ws_json, ws_manager
from app.app_services import agent_service
from app.models.session import SessionUpdate
from app.services.conversation_service import conversation_service
from app.services.session_service import session_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _send_error(websocket: WebSocket, *, code: str, message: str):
    """向客户端推送 conversation:error 类型的错误消息（携带错误码与描述）"""
    await send_ws_json(websocket, {
        "type": "conversation:error",
        "data": {"code": code, "message": message},
    })


async def _send_synced(websocket: WebSocket, *, session_id: str):
    """
    向客户端推送 conversation:synced 消息，告知同步已完成及当前最新事件序号。
    入参：session_id —— 会话 ID
    逻辑：读取该会话当前快照，取出 last_event_seq 一并下发
    """
    snapshot = conversation_service.get_snapshot(session_id)
    await send_ws_json(websocket, {
        "type": "conversation:synced",
        "data": {
            "session_id": session_id,
            "last_event_seq": snapshot.session.last_event_seq,
        },
    })


async def _send_resync_required(websocket: WebSocket, *, session_id: str, after_seq: int):
    """
    向客户端推送 conversation:resync_required 消息，告知客户端本地 after_seq 已过期，
    需要重新做全量同步（reason 固定为 stale_after_seq）。
    入参：session_id —— 会话 ID；after_seq —— 客户端请求同步时携带的起始序号
    """
    await send_ws_json(websocket, {
        "type": "conversation:resync_required",
        "data": {
            "session_id": session_id,
            "after_seq": after_seq,
            "reason": "stale_after_seq",
        },
    })


async def _send_live_state(websocket: WebSocket, *, session_id: str):
    """
    向客户端推送 conversation:live_state 消息，同步当前会话的实时运行状态。
    入参：session_id —— 会话 ID
    逻辑：从 agent_service 取该会话的实时状态快照，若不存在（如当前无运行中的任务）则跳过不发送
    """
    live_state = agent_service.get_live_state(session_id)
    if live_state is None:
        return
    await send_ws_json(websocket, {
        "type": "conversation:live_state",
        "data": live_state,
    })


@router.websocket("/ws/sessions/{session_id}/conversation")
async def websocket_conversation(websocket: WebSocket, session_id: str):
    """
    WebSocket /ws/sessions/{session_id}/conversation：会话对话长连接入口。
    入参：session_id —— 路径参数，目标会话 ID
    消息协议：客户端发送 JSON {"type": <消息类型>, "data": {...}}，服务端按 type 分支处理，
      支持的 type 包括：
        - conversation:sync           增量/全量同步事件（携带 after_seq）
        - conversation:start_turn     发起一轮对话（携带 content/provider_id/model_id/attachment_ids）
        - conversation:cancel_run     取消一次运行（携带 run_id）
        - conversation:edit_and_rerun 编辑历史消息并重跑（携带 message_id/new_content/...）
        - conversation:approve_tool / conversation:deny_tool  审批/拒绝工具调用（携带 approval_id/run_id）
        - session:set_mode            切换会话模式 build/plan
        - session:set_permission_mode 切换权限模式 ask/auto/yolo
        - plan:clear                  清除计划文件
      未知 type 会回复 invalid_request 错误。
    工作流程：连接建立后注册进 ws_manager -> 进入 while True 循环，逐条读取并解析消息 ->
      按 msg_type 分支处理并通过 send_ws_json 推送响应/事件 -> 每个分支处理完 continue；
      客户端主动断开时捕获 WebSocketDisconnect 做清理；其余未预期异常尽量通知客户端后同样清理连接
    出参：无返回值（通过 WebSocket 持续推送消息，直到连接关闭）
    """
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

            # 分支：同步事件——按 after_seq 增量拉取事件，过期则要求客户端全量重同步
            if msg_type == "conversation:sync":
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
                    await send_ws_json(websocket, {
                        "type": "conversation:event",
                        "data": event.model_dump(mode="json"),
                    })

                try:
                    await _send_live_state(websocket, session_id=session_id)
                    await _send_synced(websocket, session_id=session_id)
                except ValueError as exc:
                    await _send_error(websocket, code="not_found", message=str(exc))
                continue

            # 分支：发起一轮新对话——校验 content 非空后交给 agent_service 启动运行
            if msg_type == "conversation:start_turn":
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
                attachment_ids = msg_data.get("attachment_ids", [])

                try:
                    snapshot = conversation_service.get_snapshot(session_id)
                    await agent_service.start_turn(
                        project_id=snapshot.session.project_id,
                        session_id=session_id,
                        content=content,
                        provider_id=provider_id,
                        model_id=model_id,
                        attachment_ids=attachment_ids,
                    )
                except ValueError as exc:
                    await _send_error(websocket, code="invalid_request", message=str(exc))
                    continue

                continue

            # 分支：取消运行——校验 run_id 后交给 agent_service 取消
            if msg_type == "conversation:cancel_run":
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

            # 分支：编辑历史消息并重跑——校验 message_id/new_content 后交给 agent_service 重跑
            if msg_type == "conversation:edit_and_rerun":
                message_id = msg_data.get("message_id")
                if not isinstance(message_id, str) or not message_id:
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="message_id 不能为空",
                    )
                    continue

                new_content = msg_data.get("new_content")
                if new_content is not None and not isinstance(new_content, str):
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="new_content 必须是字符串",
                    )
                    continue

                provider_id = msg_data.get("provider_id")
                model_id = msg_data.get("model_id")

                try:
                    snapshot = conversation_service.get_snapshot(session_id)
                    await agent_service.edit_and_rerun(
                        project_id=snapshot.session.project_id,
                        session_id=session_id,
                        message_id=message_id,
                        new_content=new_content if new_content else None,
                        provider_id=provider_id,
                        model_id=model_id,
                    )
                except ValueError as exc:
                    await _send_error(websocket, code="invalid_request", message=str(exc))
                continue

            # 分支：审批/拒绝工具调用——先按 run_id 定位真实 session_id（兼容 SubAgent 场景），
            # 再根据 msg_type 分别调用 approve_tool_call 或 deny_tool_call
            if msg_type in {"conversation:approve_tool", "conversation:deny_tool"}:
                approval_id = msg_data.get("approval_id")
                if not isinstance(approval_id, str) or not approval_id:
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="approval_id 不能为空",
                    )
                    continue

                run_id = msg_data.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="run_id 不能为空",
                    )
                    continue

                try:
                    # 从 run_id 获取实际的 session_id，支持 SubAgent 审批
                    # SubAgent 的 run_id 未存储到数据库，使用前端传递的 parent_session_id 路由
                    run = conversation_service.get_run(run_id)
                    if run is not None:
                        target_session_id = run.session_id
                    else:
                        parent_session_id = msg_data.get("parent_session_id")
                        if isinstance(parent_session_id, str) and parent_session_id:
                            target_session_id = parent_session_id
                        else:
                            # 回退到当前 WebSocket 连接的 session_id
                            target_session_id = session_id

                    if msg_type == "conversation:approve_tool":
                        decision_str = msg_data.get("decision", "allow_once")
                        if decision_str not in ("allow_once", "trust_and_allow"):
                            await _send_error(
                                websocket,
                                code="invalid_request",
                                message="decision must be allow_once or trust_and_allow",
                            )
                            continue

                        await agent_service.approve_tool_call(
                            session_id=target_session_id,
                            run_id=run_id,
                            approval_id=approval_id,
                            decision=decision_str,
                        )
                    else:
                        await agent_service.deny_tool_call(
                            session_id=target_session_id,
                            run_id=run_id,
                            approval_id=approval_id,
                        )
                except ValueError as exc:
                    await _send_error(websocket, code="invalid_request", message=str(exc))
                continue

            # 分支：切换会话的 Agent 模式（build/plan）
            if msg_type == "session:set_mode":
                mode = msg_data.get("mode", "build")
                if mode not in ("build", "plan"):
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="mode must be 'build' or 'plan'",
                    )
                    continue

                try:
                    session_service.update_session(
                        session_id,
                        SessionUpdate(agent_mode=mode),
                    )
                    await send_ws_json(websocket, {
                        "type": "session:mode_changed",
                        "data": {"session_id": session_id, "mode": mode},
                    })
                except ValueError as exc:
                    await _send_error(websocket, code="not_found", message=str(exc))
                continue

            # 分支：切换会话的权限模式（ask/auto/yolo，即工具调用审批策略）
            if msg_type == "session:set_permission_mode":
                mode = msg_data.get("mode", "auto")
                if mode not in ("ask", "auto", "yolo"):
                    await _send_error(
                        websocket,
                        code="invalid_request",
                        message="permission_mode must be 'ask', 'auto', or 'yolo'",
                    )
                    continue

                try:
                    session_service.update_session(
                        session_id,
                        SessionUpdate(permission_mode=mode),
                    )
                    await send_ws_json(websocket, {
                        "type": "session:permission_mode_changed",
                        "data": {"session_id": session_id, "mode": mode},
                    })
                except ValueError as exc:
                    await _send_error(websocket, code="not_found", message=str(exc))
                continue


            # 分支：清除计划文件——按 path 删除对应 plan 文件
            if msg_type == "plan:clear":
                try:
                    plan_path = msg_data.get("path")
                    if plan_path and isinstance(plan_path, str):
                        from app.execution.plan_file_sync import PlanFileSync
                        PlanFileSync().delete(plan_path)
                    else:
                        raise ValueError("缺少有效的 path 参数")
                    await send_ws_json(websocket, {
                        "type": "plan:cleared",
                        "data": {"path": plan_path},
                    })
                except Exception as exc:
                    await _send_error(websocket, code="internal_error", message=str(exc))
                continue

            await _send_error(
                websocket,
                code="invalid_request",
                message=f"未知消息类型: {msg_type}",
            )
    except WebSocketDisconnect:
        # 客户端正常断开：从 ws_manager 中移除该连接
        ws_manager.disconnect(websocket, session_id)
        logger.info("WebSocket 断开连接: %s", session_id)
    except Exception as exc:  # pragma: no cover
        logger.error("WebSocket 错误: %s", exc)
        # 尝试通知客户端内部错误；若 websocket 已断开等导致发送失败，
        # 无需关心，后续仍要 disconnect 清理，故用 suppress 吞掉发送异常
        with contextlib.suppress(Exception):
            await _send_error(
                websocket,
                code="internal_error",
                message=f"内部错误: {exc}",
            )
        ws_manager.disconnect(websocket, session_id)
