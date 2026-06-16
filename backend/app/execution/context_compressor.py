"""上下文压缩器 - 统一管理消息状态和三级压缩模型"""
import copy
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

    # ========== 消息管理（增删查）==========

    def add_message(
        self,
        role: str,
        content: str | list[dict] | None = None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        """
        添加消息（支持多模态内容）

        自动处理：
        - Token 计算（增量）
        - 分组计数更新
        - 时间戳添加

        Args:
            role: 消息角色 (user/assistant/tool/system)
            content: 消息内容（支持纯文本或多模态 list）
            tool_calls: 工具调用列表
            tool_call_id: 工具调用 ID
        """
        message: dict = {"role": role, "timestamp": datetime.now().isoformat()}

        if content is not None:
            message["content"] = content
        if tool_calls:
            message["tool_calls"] = tool_calls
        if tool_call_id:
            message["tool_call_id"] = tool_call_id

        self._messages.append(message)

        # 增量计算 token
        msg_tokens = count_messages_tokens([message])
        self._total_tokens += msg_tokens

        # 更新分组计数
        if role == MessageRole.ASSISTANT and tool_calls:
            self._group_count += 1
        elif role == MessageRole.TOOL:
            # tool 消息归入当前组，不增加计数
            pass
        else:
            self._group_count += 1

    def get_messages(self) -> list[dict]:
        """获取所有消息（深拷贝副本）"""
        return copy.deepcopy(self._messages)

    def get_message_count(self) -> int:
        """获取消息总数"""
        return len(self._messages)

    def clear_messages(self) -> None:
        """清空所有消息（用于测试或重置）"""
        self._messages.clear()
        self._total_tokens = 0
        self._group_count = 0
        self._compacted_summary = None

    # ========== 分组逻辑 ==========

    @staticmethod
    def group_messages(messages: list[dict]) -> list[MessageGroup]:
        """
        将消息按 assistant+tool_calls 开组的方式分组

        分组规则：
        - assistant 消息（带 tool_calls）开启新组
        - 后续的 tool 消息归入当前组，直到遇到非 tool 消息
        - 其他消息单独成组

        Args:
            messages: 原始消息列表

        Returns:
            分组后的 MessageGroup 列表，每组包含消息和预计算的 token 数
        """
        grouped: list[MessageGroup] = []
        active_tool_group: list[dict] | None = None

        for msg in messages:
            # assistant 消息（带 tool_calls）开启新组
            if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                active_tool_group = [msg]
                # 预计算该消息的 token
                token_count = count_messages_tokens([msg])
                grouped.append(MessageGroup(messages=active_tool_group, token_count=token_count))
                continue

            # tool 消息归入当前组
            if msg["role"] == MessageRole.TOOL and active_tool_group is not None:
                active_tool_group.append(msg)
                # 累加 token 到当前组
                grouped[-1].token_count += count_messages_tokens([msg])
                continue

            # 其他消息单独成组
            active_tool_group = None
            token_count = count_messages_tokens([msg])
            grouped.append(MessageGroup(messages=[msg], token_count=token_count))

        return grouped

    def get_groups(self) -> list[MessageGroup]:
        """获取当前消息的分组（包含 token 预计算）"""
        return self.group_messages(self._messages)

    def get_group_count(self) -> int:
        """获取当前分组数"""
        return self._group_count
