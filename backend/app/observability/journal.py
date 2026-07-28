import json
import os
import threading
from pathlib import Path

from pydantic import BaseModel

from app.models.observability import (
    ObservabilityEventCreate,
    redact_observability_payload,
    subject_hash,
    utc_now,
)

_META_FILE = "journal-meta.json"


class JournalEntry(BaseModel):
    journal_sequence: int
    written_at: str
    event: ObservabilityEventCreate


class ObservabilityFallbackJournal:
    def __init__(
        self,
        root_dir: Path,
        *,
        segment_event_limit: int = 500,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.segment_event_limit = segment_event_limit
        self._lock = threading.RLock()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def append(self, event: ObservabilityEventCreate) -> int:
        with self._lock:
            meta = self._load_meta()
            sequence = int(meta["next_sequence"])
            segment_start = meta.get("active_segment_start")
            segment_count = int(meta.get("active_segment_count", 0))
            if segment_start is None:
                segment_start = sequence
                segment_count = 0

            entry = JournalEntry(
                journal_sequence=sequence,
                written_at=utc_now().isoformat(),
                event=event,
            )
            self._append_line(self._segment_path(int(segment_start)), entry)

            meta["next_sequence"] = sequence + 1
            segment_count += 1
            if segment_count >= self.segment_event_limit:
                meta["active_segment_start"] = None
                meta["active_segment_count"] = 0
            else:
                meta["active_segment_start"] = int(segment_start)
                meta["active_segment_count"] = segment_count
            self._write_meta(meta)
            return sequence

    def list_entries(self, *, limit: int = 100) -> list[JournalEntry]:
        with self._lock:
            entries: list[JournalEntry] = []
            for path in self._segment_files():
                entries.extend(self._read_entries(path))
                if len(entries) >= limit:
                    break
            entries.sort(key=lambda item: item.journal_sequence)
            return entries[:limit]

    def count_entries(self) -> int:
        with self._lock:
            return sum(len(self._read_entries(path)) for path in self._segment_files())

    def has_backlog(self) -> bool:
        return self.count_entries() > 0

    def acknowledge_through(self, journal_sequence: int) -> None:
        with self._lock:
            for path in self._segment_files():
                entries = self._read_entries(path)
                if not entries:
                    path.unlink(missing_ok=True)
                    continue

                remaining = [
                    entry for entry in entries if entry.journal_sequence > journal_sequence
                ]
                if not remaining:
                    path.unlink(missing_ok=True)
                    continue

                if len(remaining) == len(entries):
                    break

                self._write_entries(path, remaining)
                break

    def redact_subject(self, subject_type: str, subject_id: str) -> int:
        key_hash = subject_hash(subject_type, subject_id)
        rewrite_count = 0
        with self._lock:
            for path in self._segment_files():
                entries = self._read_entries(path)
                changed = False
                rewritten: list[JournalEntry] = []
                for entry in entries:
                    event = entry.event
                    if event.entity_type == "privacy_tombstone":
                        rewritten.append(entry)
                        continue

                    event_hashes = self._event_hashes(event)
                    if key_hash not in event_hashes.get(subject_type, set()):
                        rewritten.append(entry)
                        continue

                    sensitive_values = {
                        value
                        for value in (
                            event.subject_project_id,
                            event.subject_session_id,
                            event.subject_run_id,
                            subject_id,
                        )
                        if value
                    }
                    rewritten_event = event.model_copy(
                        update={
                            "payload_json": redact_observability_payload(
                                event.payload_json,
                                sensitive_values=sensitive_values,
                            ),
                            "subject_project_id": None,
                            "subject_session_id": None,
                            "subject_run_id": None,
                            "subject_type": subject_type,
                            "subject_key_hash": key_hash,
                        }
                    )
                    rewritten.append(entry.model_copy(update={"event": rewritten_event}))
                    changed = True
                    rewrite_count += 1

                if changed:
                    self._write_entries(path, rewritten)
        return rewrite_count

    def _load_meta(self) -> dict:
        path = self.root_dir / _META_FILE
        meta = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {
                "next_sequence": 1,
                "active_segment_start": None,
                "active_segment_count": 0,
            }
        )
        repaired = self._repair_meta(meta)
        if repaired != meta:
            self._write_meta(repaired)
        return repaired

    def _write_meta(self, payload: dict) -> None:
        path = self.root_dir / _META_FILE
        temp_path = path.with_suffix(".tmp")
        serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)

    def _segment_files(self) -> list[Path]:
        return sorted(self.root_dir.glob("segment-*.jsonl"))

    def _segment_path(self, sequence: int) -> Path:
        return self.root_dir / f"segment-{sequence:020d}.jsonl"

    def _append_line(self, path: Path, entry: JournalEntry) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _read_entries(self, path: Path) -> list[JournalEntry]:
        entries: list[JournalEntry] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                entries.append(JournalEntry.model_validate_json(stripped))
        return entries

    def _write_entries(self, path: Path, entries: list[JournalEntry]) -> None:
        temp_path = path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)

    def _repair_meta(self, meta: dict) -> dict:
        segment_paths = self._segment_files()
        if not segment_paths:
            return {
                "next_sequence": max(1, int(meta.get("next_sequence", 1))),
                "active_segment_start": None,
                "active_segment_count": 0,
            }

        max_sequence = 0
        active_segment_start = None
        active_segment_count = 0

        for path in segment_paths:
            entries = self._read_entries(path)
            if not entries:
                continue
            active_segment_start = entries[0].journal_sequence
            active_segment_count = len(entries)
            max_sequence = max(max_sequence, entries[-1].journal_sequence)

        next_sequence = max(int(meta.get("next_sequence", 1)), max_sequence + 1)
        return {
            "next_sequence": next_sequence,
            "active_segment_start": active_segment_start,
            "active_segment_count": active_segment_count,
        }

    @staticmethod
    def _event_hashes(event: ObservabilityEventCreate) -> dict[str, set[str]]:
        hashes: dict[str, set[str]] = {}
        if event.subject_type and event.subject_key_hash:
            hashes.setdefault(event.subject_type, set()).add(event.subject_key_hash)
        for subject_type, subject_id in (
            ("project", event.subject_project_id),
            ("session", event.subject_session_id),
            ("run", event.subject_run_id),
        ):
            if subject_id:
                hashes.setdefault(subject_type, set()).add(subject_hash(subject_type, subject_id))
        return hashes
