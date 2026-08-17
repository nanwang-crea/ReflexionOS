"""
对话历史加载器：从数据库读取历史消息，转换为可直接喂给 LLM 的 seed messages。

负责把 ConversationService 返回的数据库消息模型（含普通对话消息和
TOOL_TRACE 工具调用记录）转换成标准的 role/content/tool_calls 消息字典，
并做规范化过滤（去空、多模态内容保留、tool_call 配对等），供任务执行引擎
在新建 run 时预填充上下文历史。不负责静态上下文（AGENTS.md、Skills）加载，
那部分由 PromptManager 统一管理。
"""

from __future__ import annotations

from typing import Any

from app.models.conversation import MessageType
from app.services.conversation_service import ConversationService


def _message_to_seed_dict(message: Any, supports_vision: bool | None = None) -> list[dict[str, Any]]:
    """
    将单条数据库消息模型转换为 seed dict 列表。

    参数：
        message：数据库消息模型对象（需具备 message_type/role/content_text，
            可选 attachments/payload_json 等属性）。
        supports_vision：当前模型是否支持视觉输入，传给附件转换逻辑决定
            是否将图片附件转为多模态内容。
    工作流程：
    1. 若消息类型为 TOOL_TRACE（工具调用记录），转发给
       `_tool_trace_to_paired_seeds` 生成 assistant+tool 配对消息。
    2. 否则构造基础 {role, content} 消息；若存在附件，将文本与图片附件
       一并转换为多模态 content_parts 列表替换 content 字段。
    返回值：seed 消息字典列表（普通消息返回长度为 1 的列表，工具调用
    记录返回 assistant+tool 两条）。
    """
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
    """
    将一条 TOOL_TRACE 记录还原为 assistant(带 tool_calls) + tool(结果) 两条消息。

    参数：message：数据库消息模型，payload_json 中携带工具调用的
        tool_name/arguments/tool_call_id/output/error/success 等字段。
    工作流程：
    1. 解析 payload，缺失 tool_call_id 时用消息 id 生成兜底 ID。
    2. 组装 assistant 消息（content=None，携带单个 tool_calls 项）。
    3. 根据 success 选择 output 或 error 作为 tool 消息内容，并用
       `truncate_head_tail` 截断过长内容（保留头尾，避免撑爆上下文）。
    返回值：[assistant_msg, tool_msg] 两条消息组成的列表，用于保持
    tool_call_id 关联、可被 LLM 正确解读为一次完整的工具调用。
    """
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

    参数：messages：待过滤的原始 seed 消息字典列表。
    返回值：过滤/规范化后的消息字典列表，字段固定为
    role/content（+ 可选 tool_calls/tool_call_id）。
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
        """
        初始化加载器。

        参数：conversation_service：会话服务，提供数据库消息查询能力
            （本类通过它拉取历史候选消息）。
        无返回值。
        """
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

        参数：
            session_id：会话 ID，限定加载哪个会话的历史。
            project_id：项目 ID（当前仅作为调用上下文传入，未直接用于过滤查询）。
            current_turn_id：当前对话轮次 ID，用于在查询时排除/定位当前轮，
                避免把本轮消息重复当作历史种子。
            max_seed_messages：最多加载的 seed 消息条数上限。
            max_tool_traces：最多加载的工具调用记录（TOOL_TRACE）条数上限。
            scan_limit：数据库扫描的消息条数上限（用于限制查询范围/性能）。
            supports_vision：当前模型是否支持视觉输入，影响图片附件是否转换。

        工作流程：
        1. 调用 conversation_service.list_recent_seed_candidates 拉取候选消息。
        2. 对每条候选消息调用 `_message_to_seed_dict` 转换为标准 seed 字典
           （工具调用记录会展开为 assistant+tool 两条）。
        3. 调用 `_filter_seed_messages` 做去空/规范化过滤。

        注意：project_path 参数已移除。AGENTS.md 加载已移至 PromptManager，
        Skills 注入也已移至 PromptManager。

        返回值：过滤规范化后的 seed 消息字典列表，可直接作为历史消息
        灌入 LoopContext。
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
