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
