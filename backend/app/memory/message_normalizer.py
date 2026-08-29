"""
消息文本归一化模块。

将数据库中不同类型的 Message（用户/助手消息、系统通知、工具调用记录）统一
转换为纯文本表示，供搜索索引、召回、记忆摘要等场景使用；对工具输出等可能
超长的字段会做压缩截断，避免索引/记忆条目过大。
"""

from __future__ import annotations

import json

from app.memory.payload_utils import as_payload_dict
from app.memory.text_compaction import truncate_head_tail
from app.models.conversation import Message, MessageType

MAX_SEARCH_TOOL_OUTPUT_CHARS = 4_000
SEARCH_TOOL_OUTPUT_HEAD_CHARS = 2_600
SEARCH_TOOL_OUTPUT_TAIL_CHARS = 900

def normalize_message_text(message: Message) -> str:
    """
    将单条消息归一化为可用于索引/展示的纯文本。

    参数：
        message: 数据库中的 Message 实体，包含 message_type、content_text、payload_json 等字段。
    逻辑：
        - USER_MESSAGE / ASSISTANT_MESSAGE：直接返回去除首尾空白的正文文本；
        - SYSTEM_NOTICE：正文文本之外，若 payload 中带 notice_code，则追加一行 "notice_code=..."；
        - TOOL_TRACE：从 payload 中拼出 tool_name/arguments/success/output/error 等字段各占一行，
          其中 output/error 会经 _compact_tool_text 压缩，避免工具输出过长；
        - 其他未知类型：兜底返回去除首尾空白的正文文本。
    返回：
        归一化后的纯文本字符串（可能为多行）。
    """
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
    """
    压缩工具调用中的长文本字段（如 output/error）。

    参数：
        value: 待压缩的原始值，会先转换为字符串。
    逻辑：
        调用 truncate_head_tail 按"保头保尾"策略截断到 MAX_SEARCH_TOOL_OUTPUT_CHARS 长度，
        用于搜索索引场景（reason="search index"），避免单条记录因工具输出过长而膨胀。
    返回：
        压缩后的字符串。
    """
    return truncate_head_tail(
        str(value),
        MAX_SEARCH_TOOL_OUTPUT_CHARS,
        head_chars=SEARCH_TOOL_OUTPUT_HEAD_CHARS,
        tail_chars=SEARCH_TOOL_OUTPUT_TAIL_CHARS,
        reason="search index",
    )
