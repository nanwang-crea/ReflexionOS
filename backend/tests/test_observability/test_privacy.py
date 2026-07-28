from pathlib import Path

from app.models.observability import ObservabilityEventCreate
from app.models.project import Project
from app.models.session import SessionCreate
from app.observability import ObservabilityProjector
from app.services.session_service import SessionService
from app.storage.database import Database
from app.storage.models import (
    LLMLogicalCallModel,
    ObservabilityEventModel,
    ToolApprovalEventModel,
    ToolCallMetricModel,
)
from app.storage.repositories.observability_event_repo import ObservabilityEventRepository
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.session_repo import SessionRepository


def test_session_delete_redacts_events_and_projects_tombstone(tmp_path):
    db = Database(str(tmp_path / "privacy.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(
        Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/privacy-project")))
    )
    service = SessionService(db=db, session_repo=session_repo, project_repo=project_repo)
    session = service.create_session("project-1", SessionCreate(title="敏感会话标题"))
    repo = ObservabilityEventRepository(db)
    repo.append(
        ObservabilityEventCreate(
            entity_type="logical_call",
            entity_id="logical-1",
            event_type="logical.started",
            payload_json={
                "status": "running",
                "call_kind": "main",
                "session_title_snapshot": "敏感会话标题",
                "error_message": "敏感路径 /private/project",
            },
            subject_project_id="project-1",
            subject_session_id=session.id,
            subject_run_id="run-1",
        )
    )
    ObservabilityProjector(db).project_next_batch()

    service.delete_session(session.id)
    ObservabilityProjector(db).project_next_batch()

    with db.get_session() as db_session:
        events = (
            db_session.query(ObservabilityEventModel)
            .order_by(ObservabilityEventModel.sequence)
            .all()
        )
        source_event, tombstone = events
        logical = db_session.get(LLMLogicalCallModel, "logical-1")
        assert source_event.subject_session_id is None
        assert source_event.payload_json.get("session_title_snapshot") is None
        assert source_event.payload_json.get("error_message") is None
        assert source_event.privacy_redacted_at is not None
        assert tombstone.entity_type == "privacy_tombstone"
        assert tombstone.subject_type == "session"
        assert tombstone.subject_key_hash == source_event.subject_key_hash
        assert logical.session_id is None
        assert logical.session_title_snapshot is None
        assert logical.source_deleted_at is not None


def test_late_event_is_redacted_by_persisted_tombstone(tmp_path):
    db = Database(str(tmp_path / "late-privacy.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(
        Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/late-privacy")))
    )
    service = SessionService(db=db, session_repo=session_repo, project_repo=project_repo)
    session = service.create_session("project-1", SessionCreate(title="即将删除"))
    service.delete_session(session.id)

    late = ObservabilityEventRepository(db).append(
        ObservabilityEventCreate(
            entity_type="logical_call",
            entity_id="logical-late",
            event_type="logical.completed",
            payload_json={
                "status": "completed",
                "call_kind": "main",
                "session_title_snapshot": "即将删除",
                "details": {
                    "error": {"message": f"session {session.id} failed"},
                    "items": [
                        {"path": "/private/source.py"},
                        {"note": f"belongs to {session.id}"},
                    ],
                },
            },
            subject_project_id="project-1",
            subject_session_id=session.id,
            subject_run_id="run-late",
        )
    )

    assert late.subject_project_id is None
    assert late.subject_session_id is None
    assert late.subject_run_id is None
    assert late.subject_type == "session"
    assert late.privacy_redacted_at is not None
    assert "session_title_snapshot" not in late.payload_json
    assert "error" not in late.payload_json["details"]
    assert "path" not in late.payload_json["details"]["items"][0]
    assert session.id not in late.payload_json["details"]["items"][1]["note"]

    ObservabilityProjector(db).project_next_batch()
    with db.get_session() as db_session:
        logical = db_session.get(LLMLogicalCallModel, "logical-late")
        assert logical.session_id is None
        assert logical.run_id is None
        assert logical.session_title_snapshot is None


def test_session_delete_redacts_tool_metrics_and_approval_reasons(tmp_path):
    db = Database(str(tmp_path / "tool-privacy.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    project_repo.save(
        Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/tool-privacy")))
    )
    service = SessionService(db=db, session_repo=session_repo, project_repo=project_repo)
    session = service.create_session("project-1", SessionCreate(title="工具敏感会话"))
    repo = ObservabilityEventRepository(db)
    repo.append(
        ObservabilityEventCreate(
            entity_type="tool_call",
            entity_id="tool-metric-1",
            event_type="tool.running",
            payload_json={
                "invocation_id": "tool-invocation-1",
                "tool_call_id": "call-1",
                "source_run_id_hash": "hash-1",
                "tool_name": "shell",
                "status": "running",
                "project_name_snapshot": "ReflexionOS",
                "session_title_snapshot": "工具敏感会话",
                "error_message": "敏感命令 rm -rf /private",
            },
            subject_project_id="project-1",
            subject_session_id=session.id,
            subject_run_id="run-1",
        )
    )
    repo.append(
        ObservabilityEventCreate(
            entity_type="approval",
            entity_id="approval-1",
            event_type="approval.denied",
            payload_json={
                "tool_call_metric_id": "tool-metric-1",
                "approval_id": "approval-1",
                "event_type": "denied",
                "actor_type": "user",
                "reason": "不要执行这个命令",
            },
            subject_project_id="project-1",
            subject_session_id=session.id,
            subject_run_id="run-1",
        )
    )
    ObservabilityProjector(db).project_next_batch()

    service.delete_session(session.id)
    ObservabilityProjector(db).project_next_batch()

    with db.get_session() as db_session:
        tool_metric = db_session.get(ToolCallMetricModel, "tool-metric-1")
        approvals = db_session.query(ToolApprovalEventModel).all()

        assert tool_metric.session_id is None
        assert tool_metric.run_id is None
        assert tool_metric.session_title_snapshot is None
        assert tool_metric.error_message is None
        assert tool_metric.source_deleted_at is not None
        assert approvals[0].reason is None
