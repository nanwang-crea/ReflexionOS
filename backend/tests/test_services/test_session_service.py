from pathlib import Path

import pytest

from app.models.project import Project
from app.models.session import Session
from app.services.conversation_service import ConversationService
from app.services.session_service import SessionCreate, SessionService, SessionUpdate
from app.storage.database import Database
from app.storage.repositories.conversation_event_repo import ConversationEventRepository
from app.storage.repositories.message_repo import MessageRepository
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.run_repo import RunRepository
from app.storage.repositories.session_repo import SessionRepository
from app.storage.repositories.turn_repo import TurnRepository


class FakeSessionRepo:
    def __init__(self):
        self.created_sessions: list[Session] = []

    def create(self, session: Session) -> Session:
        self.created_sessions.append(session)
        return session

    def list_by_project(self, project_id: str) -> list[Session]:
        return [session for session in self.created_sessions if session.project_id == project_id]

    def get(self, session_id: str, *, db_session=None) -> Session | None:
        return next(
            (session for session in self.created_sessions if session.id == session_id),
            None,
        )

    def update(self, session: Session) -> Session:
        for index, existing in enumerate(self.created_sessions):
            if existing.id == session.id:
                self.created_sessions[index] = session
                return session
        raise AssertionError(f"missing session {session.id}")

    def delete(self, session_id: str, *, db_session=None) -> bool:
        for index, session in enumerate(self.created_sessions):
            if session.id == session_id:
                del self.created_sessions[index]
                return True
        return False


class FakeProjectRepo:
    def __init__(self, project: Project | None):
        self.project = project

    def get(self, project_id: str) -> Project | None:
        if self.project and self.project.id == project_id:
            return self.project
        return None


def test_session_defaults_updated_at_to_created_at():
    session = Session(id="session-1", project_id="project-1")

    assert session.created_at == session.updated_at


def test_create_session_rejects_missing_project():
    service = SessionService(
        session_repo=FakeSessionRepo(),
        project_repo=FakeProjectRepo(project=None),
    )

    with pytest.raises(ValueError, match="项目不存在"):
        service.create_session("missing-project", SessionCreate(title="新建聊天"))


def test_create_session_persists_defaults_for_existing_project():
    service = SessionService(
        session_repo=FakeSessionRepo(),
        project_repo=FakeProjectRepo(
            project=Project(
                id="project-1",
                name="ReflexionOS",
                path=str(Path("/tmp/reflexion")),
            )
        ),
    )

    created = service.create_session("project-1", SessionCreate())

    assert created.project_id == "project-1"
    assert created.title == "新建聊天"
    assert created.id.startswith("session-")


def test_list_project_sessions_returns_repository_sessions():
    repo = FakeSessionRepo()
    project = Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion")))
    service = SessionService(session_repo=repo, project_repo=FakeProjectRepo(project=project))
    created = service.create_session("project-1", SessionCreate(title="需求讨论"))

    sessions = service.list_project_sessions("project-1")

    assert [session.id for session in sessions] == [created.id]
    assert sessions[0].title == "需求讨论"


def test_list_project_sessions_rejects_missing_project():
    service = SessionService(
        session_repo=FakeSessionRepo(),
        project_repo=FakeProjectRepo(project=None),
    )

    with pytest.raises(ValueError, match="项目不存在"):
        service.list_project_sessions("missing-project")


def test_get_session_returns_existing_session():
    repo = FakeSessionRepo()
    project = Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion")))
    service = SessionService(session_repo=repo, project_repo=FakeProjectRepo(project=project))
    created = service.create_session("project-1", SessionCreate(title="需求讨论"))

    loaded = service.get_session(created.id)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.title == "需求讨论"


def test_update_session_updates_existing_session_fields():
    repo = FakeSessionRepo()
    project = Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion")))
    service = SessionService(session_repo=repo, project_repo=FakeProjectRepo(project=project))
    created = service.create_session(
        "project-1",
        SessionCreate(
            title="旧标题",
            preferred_provider_id="provider-a",
            preferred_model_id="model-a",
        ),
    )

    updated = service.update_session(
        created.id,
        SessionUpdate(title="新标题", preferred_provider_id="provider-b", preferred_model_id=None),
    )

    assert updated.id == created.id
    assert updated.title == "新标题"
    assert updated.preferred_provider_id == "provider-b"
    assert updated.preferred_model_id is None


def test_update_session_preserves_omitted_preference_fields():
    repo = FakeSessionRepo()
    project = Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion")))
    service = SessionService(session_repo=repo, project_repo=FakeProjectRepo(project=project))
    created = service.create_session(
        "project-1",
        SessionCreate(
            title="旧标题",
            preferred_provider_id="provider-a",
            preferred_model_id="model-a",
        ),
    )

    updated = service.update_session(created.id, SessionUpdate(title="只改标题"))

    assert updated.id == created.id
    assert updated.title == "只改标题"
    assert updated.preferred_provider_id == "provider-a"
    assert updated.preferred_model_id == "model-a"


def test_update_session_rejects_missing_session():
    service = SessionService(
        session_repo=FakeSessionRepo(),
        project_repo=FakeProjectRepo(project=None),
    )

    with pytest.raises(ValueError, match="会话不存在"):
        service.update_session("missing-session", SessionUpdate(title="新标题"))


def test_delete_session_removes_existing_session():
    repo = FakeSessionRepo()
    project = Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion")))
    service = SessionService(session_repo=repo, project_repo=FakeProjectRepo(project=project))
    created = service.create_session("project-1", SessionCreate(title="需求讨论"))

    deleted = service.delete_session(created.id)

    assert deleted is True
    assert service.get_session(created.id) is None


def test_delete_session_rejects_missing_session():
    service = SessionService(
        session_repo=FakeSessionRepo(),
        project_repo=FakeProjectRepo(project=None),
    )

    with pytest.raises(ValueError, match="会话不存在"):
        service.delete_session("missing-session")


def test_delete_session_cleans_up_conversation_history(tmp_path):
    db = Database(str(tmp_path / "session-delete-cleanup.db"))
    project_repo = ProjectRepository(db)
    session_repo = SessionRepository(db)
    turn_repo = TurnRepository(db)
    run_repo = RunRepository(db)
    message_repo = MessageRepository(db)
    event_repo = ConversationEventRepository(db)

    project_repo.save(Project(id="project-1", name="ReflexionOS", path=str(Path("/tmp/reflexion"))))
    session_service = SessionService(session_repo=session_repo, project_repo=project_repo)
    conversation_service = ConversationService(
        db=db,
        session_repo=session_repo,
        turn_repo=turn_repo,
        run_repo=run_repo,
        message_repo=message_repo,
        event_repo=event_repo,
    )

    session = session_service.create_session("project-1", SessionCreate(title="需求讨论"))
    conversation_service.start_turn(
        session_id=session.id,
        content="帮我分析这个问题",
        provider_id="provider-a",
        model_id="model-a",
        workspace_ref=None,
    )

    assert turn_repo.list_by_session(session.id)
    assert run_repo.list_by_session(session.id)
    assert message_repo.list_by_session(session.id)
    assert event_repo.list_after_seq(session.id, after_seq=0)

    deleted = session_service.delete_session(session.id)

    assert deleted is True
    assert session_service.get_session(session.id) is None
    assert turn_repo.list_by_session(session.id) == []
    assert run_repo.list_by_session(session.id) == []
    assert message_repo.list_by_session(session.id) == []
    assert event_repo.list_after_seq(session.id, after_seq=0) == []
