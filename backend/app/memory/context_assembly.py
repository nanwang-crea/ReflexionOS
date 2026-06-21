from __future__ import annotations

from typing import Any

from app.models.conversation import MessageType
from app.services.conversation_service import ConversationService


def _message_to_seed_dict(message: Any, supports_vision: bool | None = None) -> list[dict[str, Any]]:
    if message.message_type == MessageType.TOOL_TRACE:
        return _tool_trace_to_paired_seeds(message)

    # 基础消息内容
    base_msg = {"role": str(message.role), "content": str(message.content_text)}

    # 如果有附件，转换为多模态消息
    if hasattr(message, 'attachments') and message.attachments:
        from app.services.attachment_service import convert_attachments_to_content_parts

        # 构建多模态内容
        content_parts = []

        # 添加文本部分
        if message.content_text and message.content_text.strip():
            content_parts.append({"type": "text", "text": message.content_text})

        # 添加图片部分
        image_parts = convert_attachments_to_content_parts(message.attachments, supports_vision)
        content_parts.extend(image_parts)

        if content_parts:
            base_msg["content"] = content_parts

    return [base_msg]


def _tool_trace_to_paired_seeds(message: Any) -> list[dict[str, Any]]:
    from app.memory.payload_utils import as_payload_dict
    from app.memory.text_compaction import truncate_head_tail

    payload = as_payload_dict(message.payload_json)

    tool_name = payload.get("tool_name", "")
    arguments = payload.get("arguments", {})
    tool_call_id = payload.get("tool_call_id") or f"prev_{str(getattr(message, 'id', 'unknown'))[:12]}"
    output = payload.get("output", "")
    error = payload.get("error", "")
    success = payload.get("success", True)

    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tool_call_id,
                "name": tool_name,
                "arguments": arguments,
            }
        ],
    }

    tool_content = output if success else (error or "Tool execution failed")
    tool_content = truncate_head_tail(
        str(tool_content),
        max_chars=800,
        head_chars=500,
        tail_chars=200,
        reason="seed context",
    )

    tool_msg: dict[str, Any] = {
        "role": "tool",
        "content": tool_content,
        "tool_call_id": tool_call_id,
    }

    return [assistant_msg, tool_msg]


def _filter_seed_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤和规范化 seed 消息。

    原先 build_context_assembly 的过滤逻辑内联于此：
    - 去除空 role
    - 规范化 content（None → ""，保留多模态 list 格式）
    - 去除空内容消息（无文本、无 tool_calls）
    - 保留 tool_calls 和 tool_call_id 字段
    """
    result: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "").strip()
        if not role:
            continue
        raw_content = message.get("content")
        if raw_content is None:
            content: str | list = ""
        elif isinstance(raw_content, list):
            # 多模态内容（text + image_url），保留 list 格式
            content = raw_content
        else:
            content = str(raw_content)
        tool_calls = message.get("tool_calls")
        tool_call_id = message.get("tool_call_id")
        has_content = (
            (isinstance(content, list) and len(content) > 0)
            or (isinstance(content, str) and content.strip())
            or tool_calls
        )
        if not has_content:
            continue
        entry: dict[str, Any] = {"role": role, "content": content}
        if tool_calls is not None:
            entry["tool_calls"] = tool_calls
        if tool_call_id is not None:
            entry["tool_call_id"] = tool_call_id
        result.append(entry)
    return result


class ConversationHistoryLoader:
    """
    从数据库加载对话历史并转换为 LLM seed dict 格式。

    职责单一：只管对话历史，不管静态上下文（AGENTS.md、Skills 等）。
    静态上下文由 PromptManager 统一管理。
    """

    def __init__(
        self,
        *,
        conversation_service: ConversationService,
    ):
        self.conversation_service = conversation_service

    def load_for_session(
        self,
        *,
        session_id: str,
        project_id: str,
        current_turn_id: str | None = None,
        max_seed_messages: int = 8,
        max_tool_traces: int = 20,
        scan_limit: int = 200,
        supports_vision: bool | None = None,
    ) -> list[dict[str, Any]]:
        """加载对话历史，返回过滤后的 seed messages 列表。

        注意：project_path 参数已移除。AGENTS.md 加载已移至 PromptManager，
        Skills 注入也已移至 PromptManager。
        """
        # 从数据库获取最近的 seed 候选消息
        candidates = self.conversation_service.list_recent_seed_candidates(
            session_id,
            current_turn_id=current_turn_id,
            limit=max_seed_messages,
            scan_limit=scan_limit,
            max_tool_traces=max_tool_traces,
        )

        # 将消息模型转为 seed dict 格式
        raw_messages: list[dict[str, Any]] = []
        for msg in candidates:
            raw_messages.extend(_message_to_seed_dict(msg, supports_vision))

        # 过滤和规范化
        return _filter_seed_messages(raw_messages)
