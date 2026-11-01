# 文件功能：会话聊天记录归档（.reflexion-chat.json）的导出与导入
# 文件描述：导出把指定会话折叠为版本化 JSON（消息 + 思考 + 工具只读记录），供备份/迁移；
#          导入把归档文件校验后在指定项目下重建为全新的只读历史会话（新 ID、惰性工具记录，
#          不恢复任何运行时状态——审批/队列/授权/附件均不在归档内，参考 reflexion-os-studio
#          的 ChatArchiveSchema 语义）。有活跃 Run 的会话拒绝导出。
# 核心逻辑：导出按快照消息顺序线性折叠（工具轨迹挂到其后第一条助手消息）；
#          导入按"一条用户消息开启一轮 + 后续助手/工具归属该轮"重建事件序列，
#          run 终态取该轮最后一条助手消息的状态，全部写入失败时删除已建会话补偿。
import json
import logging
from datetime import datetime
from typing import Any

from app.ids import new_event_id, new_message_id, new_run_id, new_turn_id
from app.llm.base import MessageRole
from app.models.conversation import (
    ConversationEvent,
    EventType,
    MessageType,
    StreamState,
)
from app.models.session import SessionCreate

logger = logging.getLogger(__name__)

ARCHIVE_FORMAT = "reflexion-chat"
ARCHIVE_VERSION = 1
# 归档文件大小上限：与 reflexion-os-studio 的 MAX_CHAT_ARCHIVE_BYTES 对齐
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_MESSAGES = 100_000

_ASSISTANT_STATUSES = {"completed", "failed", "cancelled"}


class ChatArchiveError(ValueError):
    """归档导出/导入的业务错误（ValueError 子类，路由层按既有惯例转 400）。"""


def build_chat_archive(snapshot, session) -> dict[str, Any]:
    """把会话快照折叠为归档字典。

    输入：snapshot（ConversationSnapshot）、session（会话对象，取标题）
    逻辑：
      1. 按快照消息顺序线性遍历：user_message → user 条目；tool_trace → 暂存到
         pending_tools；assistant_message → 助手条目（携带暂存的工具清单后清空）；
      2. 状态从 stream_state 映射（completed/failed/cancelled，进行中的一律视为 completed）；
      3. reasoning 从助手消息负载的 reasoning_text 提取（缺失为 None）；
      4. model 从条目所属 run 的 model_id 取（快照 runs 里按 run_id 查）。
    输出：归档字典（format/version/exported_at/title/messages）
    异常：ChatArchiveError（会话为空）
    """
    runs_by_id = {run.id: run for run in snapshot.runs}
    entries: list[dict[str, Any]] = []
    pending_tools: list[dict[str, Any]] = []

    def _status_of(stream_state: Any) -> str:
        if stream_state == StreamState.FAILED:
            return "failed"
        if stream_state == StreamState.CANCELLED:
            return "cancelled"
        return "completed"

    for message in snapshot.messages:
        created_at = (message.created_at or message.updated_at or datetime.now()).isoformat()
        if message.message_type == MessageType.USER_MESSAGE:
            entries.append({
                "role": "user",
                "content": message.content_text or "",
                "reasoning": None,
                "created_at": created_at,
                "status": "completed",
                "model": None,
                "tools": [],
            })
            continue
        if message.message_type == MessageType.TOOL_TRACE:
            pending_tools.append({
                "name": message.payload_json.get("tool_name") or "tool",
                "arguments": message.payload_json.get("arguments") or {},
                "output": message.payload_json.get("output") or message.content_text or "",
                "status": "completed" if message.payload_json.get("success") is not False else "failed",
            })
            continue
        if message.message_type == MessageType.ASSISTANT_MESSAGE:
            run = runs_by_id.get(message.run_id or "")
            reasoning = message.payload_json.get("reasoning_text")
            entries.append({
                "role": "assistant" if message.role != MessageRole.USER else "user",
                "content": message.content_text or "",
                "reasoning": reasoning if isinstance(reasoning, str) else None,
                "created_at": created_at,
                "status": _status_of(message.stream_state),
                "model": getattr(run, "model_id", None),
                "tools": pending_tools,
            })
            pending_tools = []

    if pending_tools:
        # 末尾悬挂的工具记录（没有后续助手消息）：作为仅含工具的助手条目保留，避免丢信息
        entries.append({
            "role": "assistant",
            "content": "",
            "reasoning": None,
            "created_at": datetime.now().isoformat(),
            "status": "completed",
            "model": None,
            "tools": pending_tools,
        })

    if not entries:
        raise ChatArchiveError("会话没有可导出的消息")

    return {
        "format": ARCHIVE_FORMAT,
        "version": ARCHIVE_VERSION,
        "exported_at": datetime.now().isoformat(),
        "title": session.title,
        "messages": entries,
    }


def _validate_archive(archive: Any) -> list[dict[str, Any]]:
    """校验归档字典的结构与内容，返回合法的 messages 列表。
    异常：ChatArchiveError（格式/版本/条目非法）
    """
    if not isinstance(archive, dict):
        raise ChatArchiveError("归档文件不是有效的 JSON 对象")
    if archive.get("format") != ARCHIVE_FORMAT:
        raise ChatArchiveError(f"归档 format 必须是 {ARCHIVE_FORMAT!r}")
    if archive.get("version") != ARCHIVE_VERSION:
        raise ChatArchiveError(f"仅支持 version {ARCHIVE_VERSION} 的归档")
    messages = archive.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ChatArchiveError("归档 messages 为空")
    if len(messages) > MAX_ARCHIVE_MESSAGES:
        raise ChatArchiveError(f"归档消息数超过上限 {MAX_ARCHIVE_MESSAGES}")

    for index, entry in enumerate(messages):
        if not isinstance(entry, dict):
            raise ChatArchiveError(f"第 {index + 1} 条消息不是对象")
        if entry.get("role") not in {"user", "assistant"}:
            raise ChatArchiveError(f"第 {index + 1} 条消息 role 非法")
        if not isinstance(entry.get("content"), str):
            raise ChatArchiveError(f"第 {index + 1} 条消息 content 必须是字符串")
        tools = entry.get("tools", [])
        if not isinstance(tools, list):
            raise ChatArchiveError(f"第 {index + 1} 条消息 tools 必须是数组")
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                raise ChatArchiveError(f"第 {index + 1} 条消息的 tools 条目非法")
    return messages


def import_chat_archive(
    conversation_service,
    session_service,
    *,
    project_id: str,
    archive: Any,
) -> dict[str, Any]:
    """把已解析的归档在指定项目下重建为新的只读历史会话。

    输入：conversation_service（事件写入）、session_service（会话创建/删除）、
          project_id（目标项目）、archive（解析后的归档字典）
    逻辑：
      1. 结构校验；
      2. 创建新会话（标题取归档 title 并加"（导入）"后缀）；
      3. 按"一条 user 消息开启一轮，后续 assistant/tools 归属该轮"重建事件序列：
         TURN_CREATED → user MESSAGE_CREATED → RUN_CREATED → 工具/助手消息事件 → RUN 终态
         （终态取该轮最后一条助手消息的状态，无助手消息则 completed）；
      4. 任何异常删除已创建的会话补偿（等效原子），再抛出原错误。
    输出：{"session_id", "title", "imported_messages", "imported_tools"}
    异常：ChatArchiveError（结构非法）；其余异常在补偿后原样抛出
    """
    messages = _validate_archive(archive)

    base_title = archive.get("title") if isinstance(archive.get("title"), str) else ""
    title = (base_title or "导入的会话").strip()[:80] + "（导入）"
    session = session_service.create_session(project_id, SessionCreate(title=title))
    session_id = session.id

    imported_tools = 0
    try:
        turn_index = 0
        current: dict[str, Any] | None = None

        def _flush() -> None:
            """把当前开启的轮次以最后一条助手消息的状态收尾（无助手则 completed）。"""
            nonlocal current
            if current is None:
                return
            status = current.get("last_status") or "completed"
            terminal_type = {
                "completed": EventType.RUN_COMPLETED,
                "failed": EventType.RUN_FAILED,
                "cancelled": EventType.RUN_CANCELLED,
            }[status]
            terminal_payload = {"finished_at": datetime.now().isoformat()}
            if status == "failed":
                terminal_payload = {"error_message": "导入的历史记录中该回复标记为失败"}
            current["events"].append(
                ConversationEvent(
                    id=new_event_id(),
                    session_id=session_id,
                    turn_id=current["turn_id"],
                    run_id=current["run_id"],
                    event_type=terminal_type,
                    payload_json=terminal_payload,
                    created_at=current.get("last_created_at") or datetime.now(),
                )
            )
            conversation_service.append_events(session_id, current["events"])
            current = None

        for entry in messages:
            created_at = _parse_created_at(entry.get("created_at"))

            if entry["role"] == "user":
                _flush()
                turn_index += 1
                turn_id = new_turn_id()
                run_id = new_run_id()
                user_message_id = new_message_id()
                events = [
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type=EventType.TURN_CREATED,
                        payload_json={"turn_id": turn_id, "turn_index": turn_index, "root_message_id": user_message_id},
                        created_at=created_at,
                    ),
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        message_id=user_message_id,
                        event_type=EventType.MESSAGE_CREATED,
                        payload_json={
                            "message_id": user_message_id,
                            "turn_id": turn_id,
                            "run_id": None,
                            "role": MessageRole.USER,
                            "message_type": "user_message",
                            "turn_message_index": 1,
                            "display_mode": "default",
                            "content_text": entry["content"],
                            "payload_json": {},
                            "attachments": [],
                        },
                        created_at=created_at,
                    ),
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        event_type=EventType.RUN_CREATED,
                        payload_json={
                            "run_id": run_id,
                            "turn_id": turn_id,
                            "attempt_index": 1,
                            "provider_id": None,
                            "model_id": entry.get("model"),
                            "workspace_ref": None,
                        },
                        created_at=created_at,
                    ),
                ]
                current = {"turn_id": turn_id, "run_id": run_id, "events": events, "message_index": 1, "last_status": None, "last_created_at": None}
                continue

            # assistant 条目：归属当前轮（归档以助手开头时补一个空用户轮）
            if current is None:
                turn_index += 1
                turn_id = new_turn_id()
                run_id = new_run_id()
                user_message_id = new_message_id()
                events = [
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type=EventType.TURN_CREATED,
                        payload_json={"turn_id": turn_id, "turn_index": turn_index, "root_message_id": user_message_id},
                        created_at=created_at,
                    ),
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        message_id=user_message_id,
                        event_type=EventType.MESSAGE_CREATED,
                        payload_json={
                            "message_id": user_message_id,
                            "turn_id": turn_id,
                            "run_id": None,
                            "role": MessageRole.USER,
                            "message_type": "user_message",
                            "turn_message_index": 1,
                            "display_mode": "default",
                            "content_text": "",
                            "payload_json": {},
                            "attachments": [],
                        },
                        created_at=created_at,
                    ),
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        event_type=EventType.RUN_CREATED,
                        payload_json={
                            "run_id": run_id,
                            "turn_id": turn_id,
                            "attempt_index": 1,
                            "provider_id": None,
                            "model_id": entry.get("model"),
                            "workspace_ref": None,
                        },
                        created_at=created_at,
                    ),
                ]
                current = {"turn_id": turn_id, "run_id": run_id, "events": events, "message_index": 1, "last_status": None, "last_created_at": None}

            run_id = current["run_id"]
            turn_id = current["turn_id"]

            # 惰性工具记录：重建为已完成的只读轨迹，不可重放
            for tool in entry.get("tools", []):
                current["message_index"] += 1
                tool_message_id = new_message_id()
                tool_call_id = f"call-import-{session_id[:8]}-{imported_tools}"
                current["events"].extend([
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        message_id=tool_message_id,
                        event_type=EventType.MESSAGE_CREATED,
                        payload_json={
                            "message_id": tool_message_id,
                            "turn_id": turn_id,
                            "run_id": run_id,
                            "role": MessageRole.TOOL,
                            "message_type": "tool_trace",
                            "turn_message_index": current["message_index"],
                            "display_mode": "default",
                            "content_text": "",
                            "payload_json": {
                                "tool_name": tool["name"],
                                "arguments": tool.get("arguments") or {},
                                "tool_call_id": tool_call_id,
                                "output": tool.get("output") or "",
                                "status": "completed",
                            },
                        },
                        created_at=created_at,
                    ),
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        message_id=tool_message_id,
                        event_type=EventType.MESSAGE_COMPLETED,
                        payload_json={"completed_at": (created_at or datetime.now()).isoformat()},
                        created_at=created_at,
                    ),
                ])
                imported_tools += 1

            # 助手消息
            current["message_index"] += 1
            assistant_message_id = new_message_id()
            status = entry.get("status") if entry.get("status") in _ASSISTANT_STATUSES else "completed"
            created_payload = {
                "message_id": assistant_message_id,
                "turn_id": turn_id,
                "run_id": run_id,
                "role": MessageRole.ASSISTANT,
                "message_type": "assistant_message",
                "turn_message_index": current["message_index"],
                "display_mode": "default",
                "content_text": entry["content"],
                "payload_json": (
                    {"reasoning_text": entry["reasoning"]}
                    if isinstance(entry.get("reasoning"), str) and entry["reasoning"]
                    else {}
                ),
                "attachments": [],
            }
            assistant_events = [
                ConversationEvent(
                    id=new_event_id(),
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    message_id=assistant_message_id,
                    event_type=EventType.MESSAGE_CREATED,
                    payload_json=created_payload,
                    created_at=created_at,
                )
            ]
            if status == "failed":
                assistant_events.append(
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        message_id=assistant_message_id,
                        event_type=EventType.MESSAGE_FAILED,
                        payload_json={"error_code": "imported_failed", "error_message": "导入的历史记录中该回复标记为失败"},
                        created_at=created_at,
                    )
                )
            else:
                assistant_events.append(
                    ConversationEvent(
                        id=new_event_id(),
                        session_id=session_id,
                        turn_id=turn_id,
                        run_id=run_id,
                        message_id=assistant_message_id,
                        event_type=EventType.MESSAGE_COMPLETED,
                        payload_json={"completed_at": (created_at or datetime.now()).isoformat()},
                        created_at=created_at,
                    )
                )
            current["events"].extend(assistant_events)
            current["last_status"] = status
            current["last_created_at"] = created_at

        _flush()
    except Exception:
        # 补偿：导入失败时删除已创建的会话（等效原子），保留原错误
        logger.exception("归档导入失败，回滚已创建的会话: session=%s", session_id)
        try:
            session_service.delete_session(session_id)
        except Exception:
            logger.exception("导入补偿删除会话失败: session=%s", session_id)
        raise

    logger.info(
        "归档导入完成: session=%s, messages=%s, tools=%s", session_id, len(messages), imported_tools
    )
    return {
        "session_id": session_id,
        "title": title,
        "imported_messages": len(messages),
        "imported_tools": imported_tools,
    }


def _parse_created_at(value: Any) -> datetime | None:
    """把归档里的 created_at 字符串解析为 datetime；非法/缺失返回 None（事件用当前时间）。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def dumps_archive(archive: dict[str, Any]) -> bytes:
    """序列化归档为 UTF-8 JSON 字节（ensure_ascii=False 保留中文可读性）。"""
    return json.dumps(archive, ensure_ascii=False, indent=2).encode("utf-8")
