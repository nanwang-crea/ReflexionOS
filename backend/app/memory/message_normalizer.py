from __future__ import annotations

import json

from app.memory.payload_utils import as_payload_dict
from app.memory.text_compaction import truncate_head_tail
from app.models.conversation import Message, MessageType

MAX_SEARCH_TOOL_OUTPUT_CHARS = 4_000
SEARCH_TOOL_OUTPUT_HEAD_CHARS = 2_600
SEARCH_TOOL_OUTPUT_TAIL_CHARS = 900


def normalize_message_text(message: Message) -> str:
    if message.message_type in {MessageType.USER_MESSAGE, MessageType.ASSISTANT_MESSAGE}:
        return message.content_text.strip()

    if message.message_type == MessageType.SYSTEM_NOTICE:
        payload = as_payload_dict(message.payload_json)
        notice_code = payload.get("notice_code")
        parts = [message.content_text.strip()]
        if notice_code:
            parts.append(f"notice_code={notice_code}")
        return "\n".join(part for part in parts if part)

    if message.message_type == MessageType.TOOL_TRACE:
        payload = as_payload_dict(message.payload_json)
        lines = [f"tool_name={payload.get('tool_name', '')}"]
        if payload.get("arguments") is not None:
            lines.append(
                f"arguments={json.dumps(payload['arguments'], ensure_ascii=False, sort_keys=True)}"
            )
        if payload.get("success") is not None:
            lines.append(f"success={payload['success']}")
        if payload.get("output") is not None:
            lines.append(f"output={_compact_tool_text(payload['output'])}")
        if payload.get("error") is not None:
            lines.append(f"error={_compact_tool_text(payload['error'])}")
        return "\n".join(line for line in lines if line.strip())

    return message.content_text.strip()


def _compact_tool_text(value: object) -> str:
    return truncate_head_tail(
        str(value),
        MAX_SEARCH_TOOL_OUTPUT_CHARS,
        head_chars=SEARCH_TOOL_OUTPUT_HEAD_CHARS,
        tail_chars=SEARCH_TOOL_OUTPUT_TAIL_CHARS,
        reason="search index",
    )
