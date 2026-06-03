from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.memory.curated_store import CuratedMemoryStore
from app.models.conversation import MessageType
from app.orchestration.skill_registry import SkillRegistry
from app.services.conversation_service import ConversationService


class ContextAssemblyResult(BaseModel):
    system_sections: list[str]
    recent_messages: list[dict[str, Any]]
    supplemental_block: str | None = None


def _message_to_seed_dict(message: Any) -> list[dict[str, Any]]:
    if message.message_type == MessageType.TOOL_TRACE:
        return _tool_trace_to_paired_seeds(message)
    return [{"role": str(message.role), "content": str(message.content_text)}]


def _tool_trace_to_paired_seeds(message: Any) -> list[dict[str, Any]]:
    from uuid import uuid4

    from app.memory.payload_utils import as_payload_dict
    from app.memory.text_compaction import truncate_head_tail

    payload = as_payload_dict(message.payload_json)

    tool_name = payload.get("tool_name", "")
    arguments = payload.get("arguments", {})
    tool_call_id = payload.get("tool_call_id") or f"prev_{uuid4().hex[:8]}"
    output = payload.get("output", "")
    error = payload.get("error", "")
    success = payload.get("success", True)

    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": "",
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


def build_context_assembly(
    *,
    static_blocks: list[str],
    recent_messages: list[dict[str, Any]],
    supplemental_block: str | None,
) -> ContextAssemblyResult:
    result_messages: list[dict[str, Any]] = []
    for message in recent_messages:
        role = str(message.get("role") or "").strip()
        if not role:
            continue
        content = str(message.get("content") or "")
        tool_calls = message.get("tool_calls")
        tool_call_id = message.get("tool_call_id")
        has_content = content.strip() or tool_calls
        if not has_content:
            continue
        entry: dict[str, Any] = {"role": role, "content": content}
        if tool_calls is not None:
            entry["tool_calls"] = tool_calls
        if tool_call_id is not None:
            entry["tool_call_id"] = tool_call_id
        result_messages.append(entry)

    return ContextAssemblyResult(
        system_sections=[block for block in static_blocks if str(block or "").strip()],
        recent_messages=result_messages,
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
        skill_registry: SkillRegistry | None = None,
    ):
        self.conversation_service = conversation_service
        self.curated_store = curated_store or CuratedMemoryStore()
        self.skill_registry = skill_registry

    def build_for_session(
        self,
        *,
        session_id: str,
        project_id: str,
        project_path: str | None = None,
        current_turn_id: str | None = None,
        current_user_input: str | None = None,
        max_seed_messages: int = 8,
        max_tool_traces: int = 4,
        scan_limit: int = 200,
    ) -> ContextAssemblyResult:
        static_blocks: list[str] = []

        # 1) AGENTS.md (project rules) if present.
        if project_path:
            agents_path = Path(project_path) / "AGENTS.md"
            if agents_path.exists() and agents_path.is_file():
                agents_content = agents_path.read_text(encoding="utf-8")
                static_blocks.append(
                    f"Project rules (from {agents_path}):\n{agents_content}"
                )

        # 1.5) Inject enabled skill metadata into system context.
        if self.skill_registry:
            enabled_skills = self.skill_registry.list_enabled_skills()
            if enabled_skills:
                skill_section_parts = ["""## Available Skills

When a skill clearly matches your current task, load it first using the 'skill' tool with action='load'.

### Skill usage guidelines:
1. Before starting a task, briefly consider whether an available skill matches.
2. If a skill matches, use the 'skill' tool with action='load' to read its full content.
3. Follow the loaded skill's instructions — skills provide proven workflows for complex tasks.
4. Process skills (debugging, TDD, brainstorming) help you approach a task correctly — check them when relevant.
5. Implementation skills guide execution — use them after process skills when applicable.
6. A skill's hard gates and checklists are important safeguards — respect them.

### Available skills:"""]
                for s in enabled_skills:
                    req_str = ", ".join(s.required_skills)
                    req = f" (requires: {req_str})" if s.required_skills else ""
                    skill_section_parts.append(f"- **{s.name}**: {s.description}{req}")
                static_blocks.append("\n".join(skill_section_parts))

        # 2) Curated USER/MEMORY (project-level) if any active entries exist.
        for target in ("user", "memory"):
            entries = self.curated_store.load_entries(project_id=project_id, target=target)
            if any(entry.status == "active" for entry in entries):
                static_blocks.append(
                    self.curated_store.render_markdown(project_id=project_id, target=target)
                )

        # 3) Supplemental block: latest continuation artifact (SQL-level query).
        artifact = self.conversation_service.get_latest_continuation_artifact(
            session_id
        )
        supplemental_block = (
            artifact.content_text.strip()
            if artifact and (artifact.content_text or "").strip()
            else None
        )

        # 4) Recent seed candidates (SQL-level filter + slice).
        candidates = self.conversation_service.list_recent_seed_candidates(
            session_id,
            current_turn_id=current_turn_id,
            limit=max_seed_messages,
            scan_limit=scan_limit,
            max_tool_traces=max_tool_traces,
        )
        recent_messages: list[dict[str, Any]] = []
        for msg in candidates:
            recent_messages.extend(_message_to_seed_dict(msg))

        return build_context_assembly(
            static_blocks=static_blocks,
            recent_messages=recent_messages,
            supplemental_block=supplemental_block,
        )
