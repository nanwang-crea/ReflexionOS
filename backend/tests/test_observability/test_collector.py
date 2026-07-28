from app.models.observability import ObservabilityEventCreate
from app.observability.collector import ObservabilityCollector
from app.storage.database import Database
from app.storage.models import (
    LLMLogicalCallModel,
    LLMProviderRequestModel,
    ObservabilityEventModel,
)


def _event(event_id: str, *, entity_id: str | None = None) -> ObservabilityEventCreate:
    return ObservabilityEventCreate(
        id=event_id,
        entity_type="logical_call",
        entity_id=entity_id or event_id,
        event_type="logical.started",
        payload_json={
            "status": "running",
            "call_kind": "main",
            "session_title_snapshot": "敏感会话",
            "details": {
                "message": "sensitive error",
                "items": [{"path": "/private/code.py"}, {"note": "session-1 keeps running"}],
            },
        },
        subject_project_id="project-1",
        subject_session_id="session-1",
        subject_run_id="run-1",
    )


def test_collector_records_to_database_and_projects(tmp_path):
    db = Database(str(tmp_path / "collector.db"))
    collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")

    result = collector.record(_event("event-1"))
    health = collector.get_health()

    assert result.target == "database"
    assert result.event_sequence is not None
    assert health.status == "healthy"
    assert health.fallback_backlog_count == 0
    assert health.projection_lag_count == 0
    assert health.last_projection_at is not None


def test_database_failure_falls_back_to_journal_and_replay_recovers(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "collector-fallback.db"))
    collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
    original_append = collector.event_repo.append

    def fail_once(event, *, db_session=None):
        raise RuntimeError("database down")

    monkeypatch.setattr(collector.event_repo, "append", fail_once)

    first = collector.record(_event("event-1"))
    second = collector.record(_event("event-2"))

    assert first.target == "journal"
    assert second.target == "journal"
    assert collector.get_health().fallback_backlog_count == 2

    monkeypatch.setattr(collector.event_repo, "append", original_append)

    replayed = collector.replay_pending()
    health = collector.get_health()

    assert replayed == 2
    assert health.status == "healthy"
    assert health.fallback_backlog_count == 0

    with db.get_session() as db_session:
        events = (
            db_session.query(ObservabilityEventModel)
            .order_by(ObservabilityEventModel.sequence.asc())
            .all()
        )
        assert [event.id for event in events] == ["event-1", "event-2"]


def test_memory_queue_fallback_and_drop_count(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "collector-memory.db"))
    collector = ObservabilityCollector(
        db,
        journal_dir=tmp_path / "journal",
        memory_queue_limit=1,
    )

    def fail_db(event, *, db_session=None):
        raise RuntimeError("database down")

    def fail_journal(event):
        raise RuntimeError("disk down")

    monkeypatch.setattr(collector.event_repo, "append", fail_db)
    monkeypatch.setattr(collector.journal, "append", fail_journal)

    first = collector.record(_event("event-1"))
    second = collector.record(_event("event-2"))
    health = collector.get_health()

    assert first.target == "memory"
    assert second.target == "memory"
    assert health.status == "critical"
    assert health.memory_queue_depth == 1
    assert health.dropped_metrics_count == 1


def test_redact_subject_rewrites_journal_backlog_before_replay(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "collector-redact.db"))
    collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
    original_append = collector.event_repo.append

    def fail_db(event, *, db_session=None):
        raise RuntimeError("database down")

    monkeypatch.setattr(collector.event_repo, "append", fail_db)
    collector.record(_event("event-1"))
    collector.redact_subject("session", "session-1")
    monkeypatch.setattr(collector.event_repo, "append", original_append)

    collector.replay_pending()

    with db.get_session() as db_session:
        stored = db_session.get(ObservabilityEventModel, 1)
        assert stored is not None
        assert stored.subject_session_id is None
        assert stored.subject_project_id is None
        assert stored.subject_run_id is None
        assert stored.subject_type == "session"
        assert stored.payload_json.get("session_title_snapshot") is None
        assert stored.payload_json["details"]["items"][0].get("path") is None
        assert "session-1" not in stored.payload_json["details"]["items"][1]["note"]


def test_journal_repairs_meta_from_existing_segments(tmp_path):
    db = Database(str(tmp_path / "collector-journal-repair.db"))
    collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
    original_append = collector.event_repo.append

    def fail_db(event, *, db_session=None):
        raise RuntimeError("database down")

    collector.event_repo.append = fail_db  # type: ignore[method-assign]
    collector.record(_event("event-1"))

    meta_path = tmp_path / "journal" / "journal-meta.json"
    meta_path.write_text(
        '{"next_sequence": 1, "active_segment_start": null, "active_segment_count": 0}',
        encoding="utf-8",
    )

    collector.record(_event("event-2"))
    collector.event_repo.append = original_append  # type: ignore[method-assign]

    entries = collector.journal.list_entries(limit=10)
    assert [entry.journal_sequence for entry in entries] == [1, 2]


def test_collector_repairs_hanging_llm_records_on_startup(tmp_path):
    db = Database(str(tmp_path / "collector-repair.db"))
    with db.get_session() as db_session:
        db_session.add(
            LLMLogicalCallModel(
                id="logical-1",
                project_id="project-1",
                session_id="session-1",
                run_id="run-1",
                turn_id="turn-1",
                provider_id="provider-1",
                model_id="model-1",
                call_kind="main",
                status="running",
                request_count=0,
                total_cost_nano_usd=0,
                last_entity_version=1,
                started_at=_event("seed").occurred_at,
                updated_at=_event("seed").occurred_at,
            )
        )
        db_session.add(
            LLMProviderRequestModel(
                id="request-1",
                logical_call_id="logical-1",
                request_attempt_index=0,
                provider_id="provider-1",
                model_id="model-1",
                input_usage_source="unavailable",
                output_usage_source="unavailable",
                cached_usage_source="unavailable",
                cost_status="unpriced",
                status="running",
                last_entity_version=1,
                started_at=_event("seed").occurred_at,
                updated_at=_event("seed").occurred_at,
            )
        )

    collector = ObservabilityCollector(db, journal_dir=tmp_path / "journal")
    repaired = collector.repair_hanging_records()

    assert repaired == 2
    with db.get_session() as db_session:
        logical_call = db_session.get(LLMLogicalCallModel, "logical-1")
        provider_request = db_session.get(LLMProviderRequestModel, "request-1")
        assert logical_call.status == "interrupted"
        assert provider_request.status == "interrupted"
