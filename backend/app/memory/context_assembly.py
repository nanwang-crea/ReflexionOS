from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.memory.curated_store import CuratedMemoryStore
from app.models.conversation import Message, MessageType
from app.services.conversation_service import ConversationService


class ContextAssemblyResult(BaseModel):
    system_sections: list[str]
    recent_messages: list[dict[str, str]]
    supplemental_block: str | None = None


def build_context_assembly(
    *,
    static_blocks: list[str],
    recent_messages: list[dict[str, Any]],
    supplemental_block: str | None,
) -> ContextAssemblyResult:
    return ContextAssemblyResult(
        system_sections=[block for block in static_blocks if str(block or "").strip()],
        recent_messages=[
            {
                "role": str(message.get("role") or ""),
                "content": str(message.get("content") or ""),
            }
            for message in recent_messages
            if str(message.get("role") or "").strip() and str(message.get("content") or "").strip()
        ],
        supplemental_block=supplemental_block.strip() if supplemental_block else None,
    )


def _as_payload_dict(payload_json: object) -> dict:
    if isinstance(payload_json, dict):
        return payload_json
    if isinstance(payload_json, str):
        try:
            parsed = json.loads(payload_json)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _is_continuation_artifact(message: Message) -> bool:
    if message.message_type != MessageType.SYSTEM_NOTICE:
        return False
    payload = _as_payload_dict(message.payload_json)
    return payload.get("kind") == "continuation_artifact"


class ContextAssembler:
    """
    Build the three-layer context assembly used by runtime execution:
    - static system sections (AGENTS/USER/MEMORY)
    - recent seeded messages (conversation history)
    - supplemental block (latest continuation artifact)
    """

    def __init__(
        self,
        *,
        conversation_service: ConversationService,
        curated_store: CuratedMemoryStore | None = None,
    ):
        self.conversation_service = conversation_service
        self.curated_store = curated_store or CuratedMemoryStore()

    def build_for_session(
        self,
        *,
        session_id: str,
        project_id: str,
        project_path: str | None = None,
        current_turn_id: str | None = None,
        current_user_input: str | None = None,  # reserved for future ranking
        max_seed_messages: int = 8,
        scan_limit: int = 200,
    ) -> ContextAssemblyResult:
        static_blocks: list[str] = []

        # 1) AGENTS.md (project rules) if present.
        if project_path:
            agents_path = Path(project_path) / "AGENTS.md"
            if agents_path.exists() and agents_path.is_file():
                static_blocks.append(agents_path.read_text(encoding="utf-8"))

        # 2) Curated USER/MEMORY (project-level) if any active entries exist.
        for target in ("user", "memory"):
            entries = self.curated_store.load_entries(project_id=project_id, target=target)
            if any(entry.status == "active" for entry in entries):
                static_blocks.append(self.curated_store.render_markdown(project_id=project_id, target=target))

        # 3) Conversation-derived layers (bounded scan to avoid full-session walk).
        messages = self.conversation_service.message_repo.list_recent_by_session(
            session_id,
            limit=max(50, int(scan_limit)) if scan_limit else 200,
        )

        supplemental_block: str | None = None
        for message in reversed(messages):
            if _is_continuation_artifact(message) and (message.content_text or "").strip():
                supplemental_block = message.content_text.strip()
                break

        recent_seed_candidates: list[Message] = []
        for message in messages:
            if current_turn_id and message.turn_id == current_turn_id:
                continue
            if message.message_type not in {MessageType.USER_MESSAGE, MessageType.ASSISTANT_MESSAGE}:
                continue
            if _is_continuation_artifact(message):
                continue
            if not (message.content_text or "").strip():
                continue
            recent_seed_candidates.append(message)

        sliced = recent_seed_candidates[-max(0, int(max_seed_messages)) :] if max_seed_messages else []
        recent_messages = [{"role": msg.role, "content": msg.content_text} for msg in sliced]

        return build_context_assembly(
            static_blocks=static_blocks,
            recent_messages=recent_messages,
            supplemental_block=supplemental_block,
        )
