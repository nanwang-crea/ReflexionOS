from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class CuratedEntry(BaseModel):
    target: Literal["user", "memory"]
    type: Literal["preference", "rule", "constraint", "fact"]
    scope: Literal["project", "global"]
    source: Literal["user_explicit", "user_implied", "derived"]
    confidence: Literal["high", "medium"]
    status: Literal["active", "superseded"] = "active"
    source_refs: list[str] = Field(default_factory=list)
    summary: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CuratedWriteResult(BaseModel):
    success: bool
    conflict: bool
    conflicting_entry: CuratedEntry | None = None


class CuratedMemoryStore:
    """
    Entry-based curated memory store for per-project USER.md / MEMORY.md.

    Storage layout (default):
      {base_dir}/projects/{project_id}/curated_{target}.json
      {base_dir}/projects/{project_id}/{USER|MEMORY}.md
    """

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir) if base_dir is not None else (Path.home() / ".reflexion" / "memory")

    def add_entry(self, *, project_id: str, entry: CuratedEntry) -> CuratedWriteResult:
        conflict = self._find_conflict(project_id=project_id, entry=entry)
        if conflict is not None:
            return CuratedWriteResult(success=False, conflict=True, conflicting_entry=conflict)

        entries = self.load_entries(project_id=project_id, target=entry.target)
        entries.append(entry)
        self.save_entries(project_id=project_id, target=entry.target, entries=entries)
        self.render_to_markdown(project_id=project_id, target=entry.target, entries=entries)
        return CuratedWriteResult(success=True, conflict=False, conflicting_entry=None)

    def replace_entry(
        self,
        *,
        project_id: str,
        target: Literal["user", "memory"],
        old_summary: str,
        entry: CuratedEntry,
    ) -> CuratedWriteResult:
        entries = self.load_entries(project_id=project_id, target=target)
        updated_any = False
        now = datetime.now(timezone.utc)

        for existing in entries:
            if existing.status == "active" and existing.summary == old_summary:
                existing.status = "superseded"
                existing.updated_at = now
                updated_any = True
                break

        if not updated_any:
            # Deterministic behavior: treat "not found" as a non-successful write.
            return CuratedWriteResult(success=False, conflict=False, conflicting_entry=None)

        conflict = self._find_conflict(project_id=project_id, entry=entry, entries=entries)
        if conflict is not None:
            return CuratedWriteResult(success=False, conflict=True, conflicting_entry=conflict)

        entries.append(entry)
        self.save_entries(project_id=project_id, target=target, entries=entries)
        self.render_to_markdown(project_id=project_id, target=target, entries=entries)
        return CuratedWriteResult(success=True, conflict=False, conflicting_entry=None)

    def remove_entry(
        self,
        *,
        project_id: str,
        target: Literal["user", "memory"],
        summary: str,
    ) -> bool:
        entries = self.load_entries(project_id=project_id, target=target)
        now = datetime.now(timezone.utc)
        removed_any = False

        for existing in entries:
            if existing.status == "active" and existing.summary == summary:
                existing.status = "superseded"
                existing.updated_at = now
                removed_any = True
                break

        if not removed_any:
            return False

        self.save_entries(project_id=project_id, target=target, entries=entries)
        self.render_to_markdown(project_id=project_id, target=target, entries=entries)
        return True

    def load_entries(self, *, project_id: str, target: Literal["user", "memory"]) -> list[CuratedEntry]:
        path = self._entries_path(project_id=project_id, target=target)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
        if not isinstance(data, list):
            return []
        return [CuratedEntry(**item) for item in data]

    def save_entries(
        self,
        *,
        project_id: str,
        target: Literal["user", "memory"],
        entries: list[CuratedEntry],
    ) -> None:
        path = self._entries_path(project_id=project_id, target=target)
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = [entry.model_dump(mode="json") for entry in entries]
        path.write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8")

    def render_markdown(self, *, project_id: str, target: Literal["user", "memory"]) -> str:
        entries = self.load_entries(project_id=project_id, target=target)
        title = "USER" if target == "user" else "MEMORY"
        lines: list[str] = [f"# {title}", ""]
        for entry in entries:
            if entry.status != "active":
                continue
            lines.append(f"- [{entry.type}] {entry.summary}")
        return "\n".join(lines).strip() + "\n"

    def render_to_markdown(
        self,
        *,
        project_id: str,
        target: Literal["user", "memory"],
        entries: list[CuratedEntry] | None = None,
    ) -> None:
        # Optional fast-path to avoid re-loading entries in tight loops.
        if entries is None:
            entries = self.load_entries(project_id=project_id, target=target)

        title = "USER" if target == "user" else "MEMORY"
        lines: list[str] = [f"# {title}", ""]
        for entry in entries:
            if entry.status != "active":
                continue
            lines.append(f"- [{entry.type}] {entry.summary}")
        content = "\n".join(lines).strip() + "\n"

        md_path = self._markdown_path(project_id=project_id, target=target)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(content, encoding="utf-8")

    def _find_conflict(
        self,
        *,
        project_id: str,
        entry: CuratedEntry,
        entries: list[CuratedEntry] | None = None,
    ) -> CuratedEntry | None:
        if entry.status != "active":
            return None

        if entries is None:
            entries = self.load_entries(project_id=project_id, target=entry.target)

        new_key = self._drift_key(entry.summary)
        if not new_key:
            return None

        for existing in entries:
            if existing.status != "active":
                continue
            if existing.target != entry.target:
                continue
            if existing.type != entry.type:
                continue
            if existing.scope != entry.scope:
                continue
            if existing.summary == entry.summary:
                continue

            old_key = self._drift_key(existing.summary)
            if old_key and old_key == new_key:
                return existing

        return None

    def _project_dir(self, *, project_id: str) -> Path:
        return self.base_dir / "projects" / project_id

    def _entries_path(self, *, project_id: str, target: Literal["user", "memory"]) -> Path:
        return self._project_dir(project_id=project_id) / f"curated_{target}.json"

    def _markdown_path(self, *, project_id: str, target: Literal["user", "memory"]) -> Path:
        filename = "USER.md" if target == "user" else "MEMORY.md"
        return self._project_dir(project_id=project_id) / filename

    def _drift_key(self, summary: str) -> str:
        """
        Deterministic, heuristic "topic key" used to detect simple contradictions.

        Strategy: normalize punctuation/whitespace and remove common negation markers,
        so that:
          "默认不要直接写入用户仓库。" and "默认直接写入用户仓库。"
        collapse to the same key.
        """

        text = (summary or "").strip().lower()
        if not text:
            return ""

        # Remove punctuation and whitespace first.
        text = re.sub(r"[\\s\\t\\r\\n]+", "", text)
        text = re.sub(r"[。，,;；:：!?！？()（）\\[\\]{}<>\"'“”‘’·`~@#$%^&*_+=|\\\\/]+", "", text)

        # Remove common negation markers (order matters).
        for token in ("不要", "禁止", "别", "勿", "不", "do not", "don't", "not", "no", "never"):
            text = text.replace(token, "")

        return text.strip()

