import asyncio
import contextlib
import json
import logging
import threading
from collections import deque
from datetime import UTC
from pathlib import Path

from sqlalchemy import func

from app.models.observability import (
    ObservabilityCollectionResult,
    ObservabilityEventCreate,
    ObservabilityHealth,
    redact_observability_payload,
    subject_hash,
    utc_now,
)
from app.observability.journal import ObservabilityFallbackJournal
from app.observability.projector import ObservabilityProjector
from app.storage.models import (
    LLMLogicalCallModel,
    LLMProviderRequestModel,
    ObservabilityEventModel,
    ObservabilityProjectionCheckpointModel,
    ToolCallMetricModel,
)
from app.storage.repositories.observability_event_repo import ObservabilityEventRepository

logger = logging.getLogger(__name__)


class ObservabilityCollector:
    def __init__(
        self,
        db,
        *,
        journal_dir: str | Path | None = None,
        memory_queue_limit: int = 1000,
        replay_batch_size: int = 100,
        replay_interval_seconds: float = 2.0,
    ) -> None:
        self.db = db
        self.event_repo = ObservabilityEventRepository(db)
        self.projector = ObservabilityProjector(db)
        root_dir = (
            Path(journal_dir)
            if journal_dir is not None
            else Path(self.db.db_path).resolve().parent / "observability-journal"
        )
        self.journal = ObservabilityFallbackJournal(root_dir)
        self.health_state_path = root_dir / "collector-health.json"
        self.memory_queue_limit = memory_queue_limit
        self.replay_batch_size = replay_batch_size
        self.replay_interval_seconds = replay_interval_seconds
        self._created_at = utc_now()
        self._lock = threading.RLock()
        self._memory_queue: deque[ObservabilityEventCreate] = deque()
        self._replay_task: asyncio.Task | None = None
        self._last_event_recorded_at = None
        self._last_projection_at = None
        self._last_projection_lag_count = 0
        self._dropped_metrics_count = 0
        self._last_error_code = None
        self._last_error_at = None

    def record(self, event: ObservabilityEventCreate) -> ObservabilityCollectionResult:
        with self._lock:
            if self.journal.has_backlog():
                return self._append_to_journal_locked(event, error_code="journal_backlog")

        try:
            stored = self.event_repo.append(event)
        except Exception:
            logger.warning("observability database append failed", exc_info=True)
            with self._lock:
                self._set_error_locked("database_write_failed")
                try:
                    return self._append_to_journal_locked(
                        event,
                        error_code="database_write_failed",
                    )
                except Exception:
                    logger.warning("observability journal append failed", exc_info=True)
                    self._set_error_locked("journal_write_failed")
                    return self._enqueue_memory_locked(event)

        with self._lock:
            self._last_event_recorded_at = stored.recorded_at
        self._persist_health_state_best_effort()
        self._project_pending()
        return ObservabilityCollectionResult(
            event_id=stored.id,
            target="database",
            event_sequence=stored.sequence,
        )

    def replay_pending(self) -> int:
        replayed = 0
        journal_entries = self.journal.list_entries(limit=self.replay_batch_size)
        if journal_entries:
            last_sequence = None
            for entry in journal_entries:
                try:
                    stored = self.event_repo.append(entry.event)
                except Exception:
                    logger.warning("observability journal replay failed", exc_info=True)
                    with self._lock:
                        self._set_error_locked("journal_replay_failed")
                    self._persist_health_state_best_effort()
                    return replayed
                last_sequence = entry.journal_sequence
                replayed += 1
                with self._lock:
                    self._last_event_recorded_at = stored.recorded_at
            if last_sequence is not None:
                self.journal.acknowledge_through(last_sequence)
                self._project_pending()

        while not self.journal.has_backlog():
            with self._lock:
                if not self._memory_queue:
                    break
                event = self._memory_queue[0]

            result = self.record(event)
            if result.target == "memory":
                break

            with self._lock:
                if self._memory_queue and self._memory_queue[0].id == event.id:
                    self._memory_queue.popleft()
            replayed += 1

        with self._lock:
            if not self._memory_queue and not self.journal.has_backlog():
                self._last_error_code = None
        self._persist_health_state_best_effort()
        return replayed

    def redact_subject(self, subject_type: str, subject_id: str) -> int:
        rewrite_count = self.journal.redact_subject(subject_type, subject_id)
        key_hash = subject_hash(subject_type, subject_id)
        with self._lock:
            rewritten_queue: deque[ObservabilityEventCreate] = deque()
            for event in self._memory_queue:
                if key_hash in self._event_hashes(event).get(subject_type, set()):
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
                    event = event.model_copy(
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
                    rewrite_count += 1
                rewritten_queue.append(event)
            self._memory_queue = rewritten_queue
        self._persist_health_state_best_effort()
        return rewrite_count

    def get_health(self) -> ObservabilityHealth:
        backlog_count = self.journal.count_entries()
        projection_lag_count = self._load_projection_lag_count()
        with self._lock:
            memory_queue_depth = len(self._memory_queue)
            dropped_metrics_count = self._dropped_metrics_count
            last_error_code = self._last_error_code
            last_error_at = self._last_error_at
            last_event_recorded_at = self._last_event_recorded_at
            last_projection_at = self._last_projection_at

        if dropped_metrics_count > 0 or memory_queue_depth > 0:
            status = "critical"
        elif backlog_count > 0 or projection_lag_count > 0 or last_error_code is not None:
            status = "degraded"
        else:
            status = "healthy"

        return ObservabilityHealth(
            status=status,
            last_event_recorded_at=last_event_recorded_at,
            last_projection_at=last_projection_at,
            projection_lag_count=projection_lag_count,
            fallback_backlog_count=backlog_count,
            memory_queue_depth=memory_queue_depth,
            dropped_metrics_count=dropped_metrics_count,
            last_error_code=last_error_code,
            last_error_at=last_error_at,
        )

    def start_background_tasks(self) -> None:
        if self._replay_task is not None and not self._replay_task.done():
            return
        self.repair_hanging_records()
        self._replay_task = asyncio.create_task(
            self._replay_loop(),
            name="observability-replay",
        )

    async def stop_background_tasks(self) -> None:
        replay_task = self._replay_task
        if replay_task is None:
            return
        self._replay_task = None
        replay_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await replay_task

    async def _replay_loop(self) -> None:
        while True:
            try:
                self.replay_pending()
            except Exception:
                logger.warning("observability replay loop failed", exc_info=True)
                with self._lock:
                    self._set_error_locked("replay_loop_failed")
                self._persist_health_state_best_effort()
            await asyncio.sleep(self.replay_interval_seconds)

    def _append_to_journal_locked(
        self,
        event: ObservabilityEventCreate,
        *,
        error_code: str,
    ) -> ObservabilityCollectionResult:
        journal_sequence = self.journal.append(event)
        self._last_event_recorded_at = utc_now()
        self._set_error_locked(error_code)
        self._persist_health_state_best_effort()
        return ObservabilityCollectionResult(
            event_id=event.id,
            target="journal",
            journal_sequence=journal_sequence,
        )

    def _enqueue_memory_locked(
        self,
        event: ObservabilityEventCreate,
    ) -> ObservabilityCollectionResult:
        self._last_event_recorded_at = utc_now()
        self._set_error_locked("memory_queue_active")
        if len(self._memory_queue) >= self.memory_queue_limit:
            self._dropped_metrics_count += 1
            self._persist_health_state_best_effort()
            return ObservabilityCollectionResult(event_id=event.id, target="memory")
        self._memory_queue.append(event)
        self._persist_health_state_best_effort()
        return ObservabilityCollectionResult(event_id=event.id, target="memory")

    def _project_pending(self) -> None:
        try:
            while True:
                result = self.projector.project_next_batch(limit=self.replay_batch_size)
                if result.processed_count == 0:
                    break
                with self._lock:
                    self._last_projection_at = utc_now()
        except Exception:
            logger.warning("observability projection failed", exc_info=True)
            with self._lock:
                self._set_error_locked("projection_failed")
            self._persist_health_state_best_effort()
            return

        lag_count = self._load_projection_lag_count()
        with self._lock:
            self._last_projection_at = utc_now()
            self._last_projection_lag_count = lag_count
            if lag_count == 0 and not self._memory_queue and not self.journal.has_backlog():
                self._last_error_code = None
        self._persist_health_state_best_effort()

    def _load_projection_lag_count(self) -> int:
        try:
            with self.db.get_session() as db_session:
                max_sequence = (
                    db_session.query(func.max(ObservabilityEventModel.sequence)).scalar() or 0
                )
                checkpoint = db_session.get(ObservabilityProjectionCheckpointModel, "core")
                checkpoint_sequence = checkpoint.last_projected_sequence if checkpoint else 0
        except Exception:
            logger.warning("observability health projection lag query failed", exc_info=True)
            with self._lock:
                self._set_error_locked("health_query_failed")
                return self._last_projection_lag_count

        lag_count = max(
            0,
            int(max_sequence) - int(checkpoint_sequence),
        )
        with self._lock:
            self._last_projection_lag_count = lag_count
        return lag_count

    def _persist_health_state_best_effort(self) -> None:
        snapshot = self.get_health()
        payload = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=True, sort_keys=True)
        try:
            temp_path = self.health_state_path.with_suffix(".tmp")
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.health_state_path)
        except Exception:
            logger.warning("observability health state write failed", exc_info=True)

    def _set_error_locked(self, error_code: str) -> None:
        self._last_error_code = error_code
        self._last_error_at = utc_now()

    def repair_hanging_records(self) -> int:
        repaired = 0
        now = utc_now()
        with self.db.get_session() as db_session:
            logical_calls = (
                db_session.query(LLMLogicalCallModel)
                .filter(LLMLogicalCallModel.status == "running")
                .all()
            )
            provider_requests = (
                db_session.query(LLMProviderRequestModel)
                .filter(LLMProviderRequestModel.status == "running")
                .all()
            )
            tool_calls = (
                db_session.query(ToolCallMetricModel)
                .filter(
                    ToolCallMetricModel.status.in_(["running", "waiting_for_approval"]),
                )
                .all()
            )
            logical_payloads = [
                {
                    "id": logical_call.id,
                    "project_id": logical_call.project_id,
                    "session_id": logical_call.session_id,
                    "run_id": logical_call.run_id,
                    "started_at": logical_call.started_at,
                    "entity_version": logical_call.last_entity_version + 1,
                }
                for logical_call in logical_calls
                if self._should_repair(logical_call.updated_at)
            ]
            request_payloads = [
                {
                    "id": request.id,
                    "logical_call_id": request.logical_call_id,
                    "request_attempt_index": request.request_attempt_index,
                    "provider_id": request.provider_id,
                    "model_id": request.model_id,
                    "started_at": request.started_at,
                    "entity_version": request.last_entity_version + 1,
                }
                for request in provider_requests
                if self._should_repair(request.updated_at)
            ]
            tool_payloads = [
                {
                    "id": tool.id,
                    "invocation_id": tool.invocation_id,
                    "tool_call_id": tool.tool_call_id,
                    "source_run_id_hash": tool.source_run_id_hash,
                    "tool_name": tool.tool_name,
                    "status": tool.status,
                    "project_id": tool.project_id,
                    "session_id": tool.session_id,
                    "run_id": tool.run_id,
                    "started_at": tool.started_at,
                    "execution_started_at": tool.execution_started_at,
                    "approval_wait_ms": tool.approval_wait_ms,
                    "execution_duration_ms": tool.execution_duration_ms,
                    "total_duration_ms": tool.total_duration_ms,
                    "entity_version": tool.last_entity_version + 1,
                }
                for tool in tool_calls
                if self._should_repair(tool.updated_at)
            ]

        for logical_call in logical_payloads:
            self.record(
                ObservabilityEventCreate(
                    entity_type="logical_call",
                    entity_id=logical_call["id"],
                    entity_version=logical_call["entity_version"],
                    event_type="logical.interrupted",
                    payload_json={
                        "status": "interrupted",
                        "duration_ms": self._duration_ms(logical_call["started_at"], now),
                        "error_code": "collector_restart",
                        "error_message": "record recovered after restart",
                    },
                    subject_project_id=logical_call["project_id"],
                    subject_session_id=logical_call["session_id"],
                    subject_run_id=logical_call["run_id"],
                    occurred_at=now,
                )
            )
            repaired += 1

        for request in request_payloads:
            self.record(
                ObservabilityEventCreate(
                    entity_type="provider_request",
                    entity_id=request["id"],
                    entity_version=request["entity_version"],
                    event_type="request.interrupted",
                    payload_json={
                        "logical_call_id": request["logical_call_id"],
                        "request_attempt_index": request["request_attempt_index"],
                        "provider_id": request["provider_id"],
                        "model_id": request["model_id"],
                        "status": "interrupted",
                        "duration_ms": self._duration_ms(request["started_at"], now),
                        "error_code": "collector_restart",
                        "error_message": "record recovered after restart",
                    },
                    subject_project_id=None,
                    subject_session_id=None,
                    subject_run_id=None,
                    occurred_at=now,
                )
            )
            repaired += 1

        for tool in tool_payloads:
            approval_wait_ms = tool["approval_wait_ms"]
            execution_duration_ms = tool["execution_duration_ms"]
            total_duration_ms = tool["total_duration_ms"] or self._duration_ms(tool["started_at"], now)
            if tool["status"] == "waiting_for_approval":
                approval_wait_ms = self._duration_ms(tool["started_at"], now)
                execution_duration_ms = None
            elif tool["execution_started_at"] is not None:
                execution_duration_ms = self._duration_ms(tool["execution_started_at"], now)

            self.record(
                ObservabilityEventCreate(
                    entity_type="tool_call",
                    entity_id=tool["id"],
                    entity_version=tool["entity_version"],
                    event_type="tool.interrupted",
                    payload_json={
                        "invocation_id": tool["invocation_id"],
                        "tool_call_id": tool["tool_call_id"],
                        "source_run_id_hash": tool["source_run_id_hash"],
                        "tool_name": tool["tool_name"],
                        "status": "interrupted",
                        "approval_wait_ms": approval_wait_ms,
                        "execution_duration_ms": execution_duration_ms,
                        "total_duration_ms": total_duration_ms,
                        "error_category": "interrupted",
                        "error_message": "record recovered after restart",
                        "terminal_reason": "recovered_after_restart",
                    },
                    subject_project_id=tool["project_id"],
                    subject_session_id=tool["session_id"],
                    subject_run_id=tool["run_id"],
                    occurred_at=now,
                )
            )
            repaired += 1

        if repaired:
            logger.info("observability repaired hanging records: %s", repaired)
        return repaired

    @staticmethod
    def _duration_ms(started_at, finished_at) -> int:
        if started_at.tzinfo is None and finished_at.tzinfo is not None:
            started_at = started_at.replace(tzinfo=finished_at.tzinfo)
        if finished_at.tzinfo is None and started_at.tzinfo is not None:
            finished_at = finished_at.replace(tzinfo=started_at.tzinfo)
        return max(0, int((finished_at - started_at).total_seconds() * 1000))

    def _should_repair(self, value) -> bool:
        if value is None:
            return True
        normalized = value
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=UTC)
        return normalized < self._created_at

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
