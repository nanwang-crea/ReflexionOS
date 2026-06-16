"""上下文压缩器 - 统一管理消息状态和三级压缩模型"""
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from app.llm.base import LLMMessage, LLMToolCall, MessageRole
from app.llm.token_counter import count_messages_tokens
from app.memory.text_compaction import truncate_head_tail

logger = logging.getLogger(__name__)


@dataclass
class MessageGroup:
    """
    消息分组 - assistant+tool_calls 开组，tool 消息归入当前组

    分组规则：
    - assistant 消息（带 tool_calls）开启新组
    - 后续的 tool 消息归入当前组
    - 其他消息（user, assistant 纯文本）单独成组
    """
    messages: list[dict]  # 该组的所有消息
    token_count: int      # 预计算的 token 数，避免重复计算

    @property
    def has_tool_calls(self) -> bool:
        """是否包含工具调用"""
        return any(
            msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls")
            for msg in self.messages
        )

    @property
    def first_message_role(self) -> str:
        """返回组内第一条消息的角色"""
        return self.messages[0]["role"] if self.messages else ""


class ContextCompressor:
    """
    上下文压缩器 - 统一管理消息状态和三级压缩模型

    三级压缩模型：
    - Tier 1: 完整保真 - 最近 N 组消息，原文不改
    - Tier 2: 截断但可见 - 超出窗口的旧消息逐条截断，每条仍在 context 中
    - Tier 3: LLM 摘要 - 极端压力时旧消息压缩为摘要，细节可 session_recall 回溯
    """

    # ========== 初始化 ==========

    def __init__(
        self,
        max_context_groups: int = 10,
        tool_output_max_chars: int = 2_400,
    ):
        """
        初始化压缩器

        Args:
            max_context_groups: Tier 1 保留的最大分组数
            tool_output_max_chars: Tier 2 截断时保留的最大字符数
        """
        self._messages: list[dict] = []              # 所有消息
        self._compacted_summary: str | None = None   # Tier 3 压缩摘要
        self._total_tokens: int = 0                  # 当前总 token 数
        self._group_count: int = 0                   # 消息分组计数
        self.max_context_groups = max_context_groups
        self.tool_output_max_chars = tool_output_max_chars
