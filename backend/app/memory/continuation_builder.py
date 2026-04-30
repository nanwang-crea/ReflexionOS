from __future__ import annotations

import json
from dataclasses import dataclass

from app.memory.payload_utils import as_payload_dict
from app.memory.text_compaction import truncate_head_tail
from app.models.conversation import Message, MessageType


@dataclass(frozen=True)
class ContinuationPromptInput:
    task: str
    transcript: str


@dataclass(frozen=True)
class _TranscriptItem:
    index: int
    priority: int
    text: str


class ContinuationArtifactBuilder:
    """
    Build a budgeted continuation transcript from full conversation history.

    The source history is left untouched; only this derived prompt input is filtered
    and compacted.
    """

    def __init__(
        self,
        *,
        max_task_chars: int = 4_000,
        max_transcript_chars: int = 60_000,
        max_item_chars: int = 4_000,
        max_tool_output_chars: int = 2_400,
        tool_output_head_chars: int = 1_600,
        tool_output_tail_chars: int = 600,
    ):
        self.max_task_chars = max_task_chars
        self.max_transcript_chars = max_transcript_chars
        self.max_item_chars = max_item_chars
        self.max_tool_output_chars = max_tool_output_chars
        self.tool_output_head_chars = tool_output_head_chars
        self.tool_output_tail_chars = tool_output_tail_chars

    def build_prompt_input(self, *, task: str, messages: list[Message]) -> ContinuationPromptInput:
        items = self._build_items(messages)
        transcript = self._fit_global_budget(items)
        return ContinuationPromptInput(
            task=self._truncate_text(task or "", self.max_task_chars),
            transcript=transcript,
        )

    def _build_items(self, messages: list[Message]) -> list[_TranscriptItem]:
        items: list[_TranscriptItem] = []
        for index, message in enumerate(messages):
            if self._should_skip(message):
                continue

            text = self._format_message(message)
            if not text:
                continue

            items.append(
                _TranscriptItem(
                    index=index,
                    priority=self._priority(message),
                    text=self._truncate_text(text, self.max_item_chars),
                )
            )
        return items

    def _should_skip(self, message: Message) -> bool:
        if message.message_type != MessageType.SYSTEM_NOTICE:
            return False
        payload = as_payload_dict(message.payload_json)
        return payload.get("kind") == "continuation_artifact"

    def _format_message(self, message: Message) -> str:
        if message.message_type in {MessageType.USER_MESSAGE, MessageType.ASSISTANT_MESSAGE}:
            content = (message.content_text or "").strip()
            return f"[{message.role}/{message.message_type.value}] {content}" if content else ""

        if message.message_type == MessageType.TOOL_TRACE:
            return self._format_tool_trace(message)

        if message.message_type == MessageType.SYSTEM_NOTICE:
            content = (message.content_text or "").strip()
            return f"[system/{message.message_type.value}] {content}" if content else ""

        content = (message.content_text or "").strip()
        return f"[{message.role}/{message.message_type.value}] {content}" if content else ""

    def _format_tool_trace(self, message: Message) -> str:
        payload = as_payload_dict(message.payload_json)
        lines = [f"[{message.role}/{message.message_type.value}]"]
        lines.append(f"tool_name={payload.get('tool_name', '')}")

        if payload.get("arguments") is not None:
            lines.append(
                f"arguments={json.dumps(payload['arguments'], ensure_ascii=False, sort_keys=True)}"
            )
        if payload.get("success") is not None:
            lines.append(f"success={payload['success']}")
        if payload.get("output") is not None:
            output = self._truncate_head_tail(str(payload["output"]), self.max_tool_output_chars)
            lines.append(f"output={output}")
        if payload.get("error") is not None:
            error = self._truncate_head_tail(str(payload["error"]), self.max_tool_output_chars)
            lines.append(f"error={error}")

        return "\n".join(line for line in lines if line.strip())

    def _fit_global_budget(self, items: list[_TranscriptItem]) -> str:
        if not items:
            return ""

        full_transcript = self._join_items(items)
        if len(full_transcript) <= self.max_transcript_chars:
            return full_transcript

        notice = "[system/notice] 已按 continuation 预算省略部分较早或低优先级上下文。"
        budget = max(0, self.max_transcript_chars - len(notice) - 2)
        selected: list[_TranscriptItem] = []
        used = 0

        for item in sorted(items, key=lambda item: (item.priority, item.index), reverse=True):
            extra_separator = 2 if selected else 0
            next_size = len(item.text) + extra_separator
            if used + next_size > budget:
                continue
            selected.append(item)
            used += next_size

        if not selected:
            return self._truncate_text(notice, self.max_transcript_chars)

        selected.sort(key=lambda item: item.index)
        return self._join_items([_TranscriptItem(index=-1, priority=0, text=notice), *selected])

    def _join_items(self, items: list[_TranscriptItem]) -> str:
        return "\n\n".join(item.text for item in items).strip()

    def _priority(self, message: Message) -> int:
        if message.message_type == MessageType.USER_MESSAGE:
            return 100
        if message.message_type == MessageType.ASSISTANT_MESSAGE:
            return 80
        if message.message_type == MessageType.TOOL_TRACE:
            return 60
        return 20

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        value = text.strip()
        if len(value) <= max_chars:
            return value
        return truncate_head_tail(
            value,
            max_chars,
            head_chars=self.tool_output_head_chars,
            tail_chars=self.tool_output_tail_chars,
            reason="continuation artifact",
        )

    def _truncate_head_tail(self, text: str, max_chars: int) -> str:
        return truncate_head_tail(
            text,
            max_chars,
            head_chars=self.tool_output_head_chars,
            tail_chars=self.tool_output_tail_chars,
            reason="continuation artifact",
        )
