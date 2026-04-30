from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.memory.curated_store import CuratedMemoryStore
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
        current_user_input: str | None = None,
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

        # 3) Supplemental block: latest continuation artifact (SQL-level query).
        artifact = self.conversation_service.message_repo.get_latest_continuation_artifact(session_id)
        supplemental_block = artifact.content_text.strip() if artifact and (artifact.content_text or "").strip() else None

        # 4) Recent seed candidates (SQL-level filter + slice).
        candidates = self.conversation_service.message_repo.list_recent_seed_candidates(
            session_id,
            current_turn_id=current_turn_id,
            limit=max_seed_messages,
            scan_limit=scan_limit,
        )
        recent_messages = [{"role": msg.role, "content": msg.content_text} for msg in candidates]

        return build_context_assembly(
            static_blocks=static_blocks,
            recent_messages=recent_messages,
            supplemental_block=supplemental_block,
        )
