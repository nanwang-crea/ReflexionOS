import pytest
from datetime import datetime, timedelta
from pathlib import Path
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.conversation_repo import ConversationRepository
from app.storage.repositories.execution_repo import ExecutionRepository
from app.models.conversation import ConversationMessage
from app.models.project import Project
from app.models.execution import Execution, ExecutionStatus, ExecutionStep, StepStatus


class TestProjectRepository:
    
    @pytest.fixture
    def db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        return Database(db_path)
    
    @pytest.fixture
    def repo(self, db):
        return ProjectRepository(db)
    
    def test_save_project(self, repo):
        project = Project(
            id="proj-123",
            name="TestProject",
            path="/tmp/test"
        )
        
        result = repo.save(project)
        
        assert result.id == "proj-123"
        assert result.name == "TestProject"
    
    def test_get_project(self, repo):
        project = Project(
            id="proj-456",
            name="TestProject2",
            path="/tmp/test2"
        )
        repo.save(project)
        
        result = repo.get("proj-456")
        
        assert result is not None
        assert result.name == "TestProject2"
    
    def test_get_by_path(self, repo):
        project = Project(
            id="proj-789",
            name="TestProject3",
            path="/tmp/test3"
        )
        repo.save(project)
        
        result = repo.get_by_path("/tmp/test3")
        
        assert result is not None
        assert result.id == "proj-789"
    
    def test_list_all(self, repo):
        for i in range(3):
            project = Project(
                id=f"proj-{i}",
                name=f"Project{i}",
                path=f"/tmp/test{i}"
            )
            repo.save(project)
        
        result = repo.list_all()
        
        assert len(result) == 3
    
    def test_delete_project(self, repo):
        project = Project(
            id="proj-delete",
            name="ToDelete",
            path="/tmp/delete"
        )
        repo.save(project)
        
        result = repo.delete("proj-delete")
        
        assert result is True
        assert repo.get("proj-delete") is None


class TestExecutionRepository:
    
    @pytest.fixture
    def db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        return Database(db_path)
    
    @pytest.fixture
    def repo(self, db):
        return ExecutionRepository(db)
    
    def test_save_execution(self, repo):
        execution = Execution(
            id="exec-123",
            project_id="proj-123",
            task="测试任务"
        )
        
        result = repo.save(execution)
        
        assert result.id == "exec-123"
        assert result.task == "测试任务"
    
    def test_get_execution(self, repo):
        execution = Execution(
            id="exec-456",
            project_id="proj-456",
            task="测试任务2"
        )
        repo.save(execution)
        
        result = repo.get("exec-456")
        
        assert result is not None
        assert result.task == "测试任务2"

    def test_save_execution_with_session_id(self, repo):
        execution = Execution(
            id="exec-session",
            project_id="proj-session",
            session_id="session-123",
            task="带会话的任务"
        )

        repo.save(execution)

        result = repo.get("exec-session")

        assert result is not None
        assert result.session_id == "session-123"
    
    def test_list_by_project(self, repo):
        for i in range(3):
            execution = Execution(
                id=f"exec-{i}",
                project_id="proj-list",
                task=f"任务{i}"
            )
            repo.save(execution)
        
        result = repo.list_by_project("proj-list")
        
        assert len(result) == 3
    
    def test_update_execution_status(self, repo):
        execution = Execution(
            id="exec-update",
            project_id="proj-update",
            task="更新测试",
            status=ExecutionStatus.RUNNING
        )
        repo.save(execution)
        
        # 更新状态
        execution.status = ExecutionStatus.COMPLETED
        execution.result = "执行完成"
        repo.save(execution)
        
        result = repo.get("exec-update")
        
        assert result.status == ExecutionStatus.COMPLETED
        assert result.result == "执行完成"

    def test_save_execution_with_step_timestamp_serializes_cleanly(self, repo):
        execution = Execution(
            id="exec-step-ts",
            project_id="proj-step-ts",
            task="带时间戳步骤的任务",
            steps=[
                ExecutionStep(
                    step_number=1,
                    tool="shell",
                    args={"command": "pwd"},
                    status=StepStatus.SUCCESS,
                )
            ]
        )

        repo.save(execution)

        result = repo.get("exec-step-ts")

        assert result is not None
        assert result.steps[0].tool == "shell"


class TestConversationRepository:

    @pytest.fixture
    def db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        return Database(db_path)

    @pytest.fixture
    def repo(self, db):
        return ConversationRepository(db)

    def test_save_and_list_by_session(self, repo):
        repo.save_messages([
            ConversationMessage(
                id="msg-1",
                execution_id="exec-1",
                session_id="session-a",
                project_id="proj-1",
                item_type="user-message",
                content="hello",
                receipt_status=None,
                details_json=[],
                sequence=0,
                created_at=__import__('datetime').datetime.now(),
            ),
            ConversationMessage(
                id="msg-2",
                execution_id="exec-1",
                session_id="session-a",
                project_id="proj-1",
                item_type="assistant-message",
                content="world",
                receipt_status=None,
                details_json=[],
                sequence=1,
                created_at=__import__('datetime').datetime.now(),
            ),
        ])

        result = repo.list_by_session("session-a")

        assert [message.id for message in result] == ["msg-1", "msg-2"]
        assert [message.item_type for message in result] == ["user-message", "assistant-message"]

    def test_save_and_list_transcript_items_with_receipts(self, repo):
        repo.save_messages([
            ConversationMessage(
                id="receipt-1",
                execution_id="exec-1",
                session_id="session-a",
                project_id="proj-1",
                item_type="action-receipt",
                content="",
                receipt_status="completed",
                details_json=[{"title": "Read file", "status": "success"}],
                sequence=2,
                created_at=__import__('datetime').datetime.now(),
            )
        ])

        result = repo.list_by_session("session-a")

        assert result[0].item_type == "action-receipt"
        assert result[0].receipt_status == "completed"
        assert result[0].details_json == [{"title": "Read file", "status": "success"}]

    def test_list_by_session_orders_turns_by_timestamp_then_sequence(self, repo):
        start = datetime.now()

        repo.save_messages([
            ConversationMessage(
                id="turn-1-user",
                execution_id="exec-1",
                session_id="session-order",
                project_id="proj-1",
                item_type="user-message",
                content="first question",
                receipt_status=None,
                details_json=[],
                sequence=0,
                created_at=start,
            ),
            ConversationMessage(
                id="turn-1-assistant",
                execution_id="exec-1",
                session_id="session-order",
                project_id="proj-1",
                item_type="assistant-message",
                content="first answer",
                receipt_status=None,
                details_json=[],
                sequence=3,
                created_at=start + timedelta(seconds=1),
            ),
            ConversationMessage(
                id="turn-2-user",
                execution_id="exec-2",
                session_id="session-order",
                project_id="proj-1",
                item_type="user-message",
                content="second question",
                receipt_status=None,
                details_json=[],
                sequence=0,
                created_at=start + timedelta(seconds=2),
            ),
            ConversationMessage(
                id="turn-2-assistant",
                execution_id="exec-2",
                session_id="session-order",
                project_id="proj-1",
                item_type="assistant-message",
                content="second answer",
                receipt_status=None,
                details_json=[],
                sequence=3,
                created_at=start + timedelta(seconds=3),
            ),
        ])

        result = repo.list_by_session("session-order")

        assert [message.id for message in result] == [
            "turn-1-user",
            "turn-1-assistant",
            "turn-2-user",
            "turn-2-assistant",
        ]
