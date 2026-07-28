import threading
from contextlib import ExitStack

from sqlalchemy import func

from app.models.observability import (
    ObservabilityEvent,
    ObservabilityEventCreate,
    redact_observability_payload,
    subject_hash,
    utc_now,
)
from app.storage.models import ObservabilityEventModel

from .base_repo import BaseRepository


class ObservabilityEventRepository(BaseRepository[ObservabilityEvent]):
    _locks_guard = threading.Lock()
    _entity_locks: dict[tuple[str, str, str], threading.RLock] = {}

    def __init__(self, db):
        super().__init__(db, ObservabilityEvent)

    def append(
        self,
        event: ObservabilityEventCreate,
        *,
        db_session=None,
    ) -> ObservabilityEvent:
        with ExitStack() as stack:
            for lock in self._locks_for_event(event):
                stack.enter_context(lock)
            if db_session is None:
                db_session = stack.enter_context(self.db.get_session())
            return self._append_locked(event, db_session=db_session)

    def _append_locked(
        self,
        event: ObservabilityEventCreate,
        *,
        db_session,
    ) -> ObservabilityEvent:

        existing = db_session.query(ObservabilityEventModel).filter_by(id=event.id).first()
        if existing is not None:
            return self._to_domain(existing)

        event, privacy_redacted_at = self._apply_tombstone_if_needed(event, db_session)
        entity_version = event.entity_version
        if entity_version is None:
            current_version = (
                db_session.query(func.max(ObservabilityEventModel.entity_version))
                .filter(
                    ObservabilityEventModel.entity_type == event.entity_type,
                    ObservabilityEventModel.entity_id == event.entity_id,
                )
                .scalar()
            )
            entity_version = int(current_version or 0) + 1

        model = ObservabilityEventModel(
            **event.model_dump(exclude={"entity_version"}),
            entity_version=entity_version,
            recorded_at=utc_now(),
            privacy_redacted_at=privacy_redacted_at,
        )
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    @classmethod
    def subject_lock(cls, db, subject_type: str, subject_id: str) -> threading.RLock:
        return cls._lock_for_key((db.db_path, f"subject:{subject_type}", subject_id))

    @classmethod
    def _lock_for_key(cls, key: tuple[str, str, str]) -> threading.RLock:
        with cls._locks_guard:
            lock = cls._entity_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                cls._entity_locks[key] = lock
            return lock

    def _locks_for_event(self, event: ObservabilityEventCreate) -> list[threading.RLock]:
        keys = {(self.db.db_path, event.entity_type, event.entity_id)}
        for subject_type, subject_id in (
            ("project", event.subject_project_id),
            ("session", event.subject_session_id),
            ("run", event.subject_run_id),
        ):
            if subject_id:
                keys.add((self.db.db_path, f"subject:{subject_type}", subject_id))
        return [self._lock_for_key(key) for key in sorted(keys)]

    @staticmethod
    def _apply_tombstone_if_needed(event: ObservabilityEventCreate, db_session):
        if event.entity_type == "privacy_tombstone":
            return event, None

        candidates = [
            ("run", event.subject_run_id),
            ("session", event.subject_session_id),
            ("project", event.subject_project_id),
        ]
        if event.subject_type and event.subject_key_hash:
            hashes = [(event.subject_type, event.subject_key_hash)]
        else:
            hashes = [
                (subject_type, subject_hash(subject_type, subject_id))
                for subject_type, subject_id in candidates
                if subject_id
            ]

        for subject_type, key_hash in hashes:
            tombstone = (
                db_session.query(ObservabilityEventModel)
                .filter(
                    ObservabilityEventModel.entity_type == "privacy_tombstone",
                    ObservabilityEventModel.subject_type == subject_type,
                    ObservabilityEventModel.subject_key_hash == key_hash,
                )
                .first()
            )
            if tombstone is None:
                continue
            sensitive_values = {value for _, value in candidates if value}
            return (
                event.model_copy(
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
                ),
                utc_now(),
            )
        return event, None

    def list_after(
        self,
        sequence: int,
        *,
        limit: int = 100,
        db_session=None,
    ) -> list[ObservabilityEvent]:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.list_after(sequence, limit=limit, db_session=managed_session)

        models = (
            db_session.query(ObservabilityEventModel)
            .filter(ObservabilityEventModel.sequence > sequence)
            .order_by(ObservabilityEventModel.sequence.asc())
            .limit(limit)
            .all()
        )
        return self._to_domain_list(models)
