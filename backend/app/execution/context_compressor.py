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
    token_count: int  # 预计算的 token 数，避免重复计算

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
        self._messages: list[dict] = []  # 所有消息
        self._compacted_summary: str | None = None  # Tier 3 压缩摘要
        self._total_tokens: int = 0  # 当前总 token 数
        self._group_count: int = 0  # 消息分组计数
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
                grouped.append(
                    MessageGroup(messages=active_tool_group, token_count=token_count)
                )
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

    # ========== Token 管理 ==========

    def calculate_tokens(self, messages: list[dict]) -> int:
        """计算消息列表的 token 数"""
        return count_messages_tokens(messages)

    def recalculate_tokens(self) -> None:
        """重新计算总 token 数（用于 Tier 3 压缩后）"""
        self._total_tokens = count_messages_tokens(self._messages)

    def get_total_tokens(self) -> int:
        """获取当前总 token 数"""
        return self._total_tokens

    def check_pressure(self, context_window: int, tier3_ratio: float) -> bool:
        """
        检查是否需要触发 Tier 3 压缩

        Args:
            context_window: 模型的上下文窗口大小
            tier3_ratio: Tier 3 阈值比例（如 0.85 表示 85% 窗口）

        Returns:
            True 表示需要压缩
        """
        tier3_threshold = int(context_window * tier3_ratio)
        return self._total_tokens > tier3_threshold

    # ========== Tier 1: 完整保留 ==========

    def get_recent_messages(self, max_groups: int | None = None) -> list[dict]:
        """
        获取 Tier 1 最近 N 组消息（完整保留，包括多模态内容）

        Args:
            max_groups: 保留的最大分组数，默认使用 self.max_context_groups

        Returns:
            展平后的消息列表（保持原始格式）
        """
        if not self._messages:
            return []

        max_groups = max_groups or self.max_context_groups
        grouped = self.group_messages(self._messages)

        # 保留最近 N 组
        recent_groups = grouped[-max_groups:]

        # 展平为消息列表
        flat_messages = []
        for group in recent_groups:
            flat_messages.extend(group.messages)

        return flat_messages

    # ========== Tier 2: 截断可见 ==========

    def build_tier2_messages(self) -> list[LLMMessage]:
        """
        构建 Tier 2 消息：超出窗口的旧消息逐条截断但始终可见

        处理规则：
        - 只处理超出 max_context_groups 的旧分组
        - tool output 超过 tool_output_max_chars 时 head+tail 截断
        - 标记 [session_recall can retrieve] 提示可回溯
        - 保持原始消息角色，确保 tool_call_id / tool_calls 关联不被破坏

        Returns:
            LLMMessage 列表（可直接用于 LLM 调用）
        """
        grouped = self.group_messages(self._messages)

        # 如果总分组数不超过窗口，无需 Tier 2
        if len(grouped) <= self.max_context_groups:
            return []

        # 只处理超出窗口的旧分组
        older_groups = grouped[: -self.max_context_groups]
        tier2: list[LLMMessage] = []

        for group in older_groups:
            for msg in group.messages:
                content = msg.get("content")

                # 空内容的 assistant 消息（只有 tool_calls）
                if content is None or (
                    isinstance(content, str) and not content.strip()
                ):
                    if msg["role"] == MessageRole.ASSISTANT and msg.get("tool_calls"):
                        tool_calls_list = msg.get("tool_calls", [])
                        tier2.append(
                            LLMMessage(
                                role=MessageRole.ASSISTANT,
                                content=content,
                                tool_calls=(
                                    [LLMToolCall(**tc) for tc in tool_calls_list]
                                    if tool_calls_list
                                    else None
                                ),
                            )
                        )
                    continue

                # tool 消息：截断长输出
                if msg["role"] == MessageRole.TOOL:
                    # 已被裁剪的保持原样
                    if content == "[Old tool result content cleared]":
                        tier2.append(
                            LLMMessage(
                                role=MessageRole.TOOL,
                                content=content,
                                tool_call_id=msg.get("tool_call_id"),
                            )
                        )
                        continue

                    # 超长输出：head+tail 截断
                    if len(content) > self.tool_output_max_chars:
                        content = truncate_head_tail(
                            content,
                            self.tool_output_max_chars,
                            head_chars=1_600,
                            tail_chars=600,
                            reason="session_recall retrieve",
                        )

                    tier2.append(
                        LLMMessage(
                            role=MessageRole.TOOL,
                            content=content,
                            tool_call_id=msg.get("tool_call_id"),
                        )
                    )

                # assistant 消息（有 tool_calls 或纯文本）
                elif msg["role"] == MessageRole.ASSISTANT:
                    tool_calls_list = msg.get("tool_calls", [])
                    tier2.append(
                        LLMMessage(
                            role=MessageRole.ASSISTANT,
                            content=content,
                            tool_calls=(
                                [LLMToolCall(**tc) for tc in tool_calls_list]
                                if tool_calls_list
                                else []
                            ),
                        )
                    )

                # user 消息：保留所有（包括多模态内容）
                elif msg["role"] == MessageRole.USER:
                    tier2.append(LLMMessage(role=MessageRole.USER, content=content))

        return tier2

    # ========== Tier 3: LLM 摘要 ==========

    async def compact_tier3(
        self,
        task: str,
        summarizer: Callable[[str, str], Awaitable[str]],
    ) -> None:
        """
        Tier 3 压缩：将窗口外的旧消息经 LLM 压缩为摘要

        处理流程：
        1. 提取超出窗口的旧消息
        2. 构建 transcript（角色 + 内容，截断过长内容）
        3. 调用 summarizer 回调生成摘要
        4. 更新 _compacted_summary
        5. 从 _messages 中移除旧消息，保留最近 N 组
        6. 重新计算 token 数

        Args:
            task: 当前任务描述（用于摘要提示词）
            summarizer: 摘要生成回调函数
                        签名：async (task: str, transcript: str) -> str
                        调用方负责构建 prompt 并调用 LLM

        注意：
        - 压缩失败时静默跳过，不中断 run
        - 摘要包含 [可 session_recall 取回] 标记
        - DB 中的原始消息不受影响
        """
        try:
            grouped = self.group_messages(self._messages)

            # 如果分组数不超过窗口，无需压缩
            if len(grouped) <= self.max_context_groups:
                return

            # 提取旧消息
            older_groups = grouped[: -self.max_context_groups]
            older_messages = []
            for group in older_groups:
                older_messages.extend(group.messages)

            # 构建 transcript
            transcript_parts = []
            for msg in older_messages:
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    role = msg.get("role", "unknown")
                    # 截断过长内容
                    truncated_content = (
                        content[:2000] if len(content) > 2000 else content
                    )
                    transcript_parts.append(f"[{role}] {truncated_content}")

            transcript = "\n\n".join(transcript_parts)

            # 调用 summarizer 回调生成摘要
            summary = await summarizer(task, transcript)

            if not summary or not summary.strip():
                logger.warning("Tier 3 compaction returned empty summary, skipping")
                return

            # 更新摘要
            self._compacted_summary = summary.strip()

            # 移除旧消息，保留最近 N 组
            recent_groups = grouped[-self.max_context_groups :]
            self._messages = []
            for group in recent_groups:
                self._messages.extend(group.messages)

            # 更新分组计数
            self._group_count = len(recent_groups)

            # 重新计算 token
            self.recalculate_tokens()

            logger.info(
                "Tier 3 compaction completed. Summary length=%d, remaining messages=%d, tokens=%d",
                len(summary),
                len(self._messages),
                self._total_tokens,
            )

        except Exception as e:
            logger.exception("Tier 3 compaction failed: %s, skipping", e)

    def get_compacted_summary(self) -> str | None:
        """获取 Tier 3 压缩摘要"""
        return self._compacted_summary

    def set_compacted_summary(self, summary: str | None) -> None:
        """设置 Tier 3 压缩摘要（用于测试或手动设置）"""
        self._compacted_summary = summary

    # ========== 轻量裁剪 ==========

    def prune_tool_outputs(
        self,
        protect_recent_groups: int = 2,
        minimum_recovery_tokens: int = 20_000,
        protected_tool_names: set[str] | None = None,
    ) -> int:
        """
        轻量裁剪：清除旧 tool output 的 content，回收 token

        处理规则：
        - 保护最近 N 组消息不被裁剪
        - 只有回收量 >= minimum_recovery_tokens 才执行
        - 受保护的工具（如 skill）不被裁剪
        - 将 content 替换为 "[Old tool result content cleared]"

        Args:
            protect_recent_groups: 保护的最近分组数
            minimum_recovery_tokens: 最小回收 token 数（避免频繁小量裁剪）
            protected_tool_names: 受保护的工具名称集合（默认 {"skill"}）

        Returns:
            实际回收的 token 数
        """
        if protected_tool_names is None:
            protected_tool_names = {"skill"}

        grouped = self.group_messages(self._messages)

        # 如果分组数不超过保护数，无需裁剪
        if len(grouped) <= protect_recent_groups:
            return 0

        # 计算可回收的 token 和候选消息
        older_groups = grouped[:-protect_recent_groups]
        reclaimable = 0
        candidates: list[tuple[int, dict]] = []

        for group in older_groups:
            for msg in group.messages:
                if msg["role"] != MessageRole.TOOL:
                    continue

                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue

                # 已被裁剪的跳过
                if content == "[Old tool result content cleared]":
                    continue

                # 检查是否受保护 - 查找组内的 assistant 消息
                is_protected = False
                tool_call_msg = next(
                    (m for m in group.messages if m["role"] == MessageRole.ASSISTANT),
                    None,
                )
                if tool_call_msg:
                    for tc in tool_call_msg.get("tool_calls", []):
                        if tc.get("name") in protected_tool_names:
                            is_protected = True
                            break

                if is_protected:
                    continue

                # 计算 token
                msg_tokens = count_messages_tokens([msg])
                reclaimable += msg_tokens
                candidates.append((msg_tokens, msg))

        # 如果回收量不足，不执行
        if reclaimable < minimum_recovery_tokens:
            return 0

        # 执行裁剪
        recovered = 0
        for msg_tokens, msg in candidates:
            msg["content"] = "[Old tool result content cleared]"
            recovered += msg_tokens

        # 重新计算总 token
        self.recalculate_tokens()

        logger.info(
            "Pruned %d tool outputs, recovered ~%d tokens, remaining total_tokens=%d",
            len(candidates),
            recovered,
            self._total_tokens,
        )

        return recovered
