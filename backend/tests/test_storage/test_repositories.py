import pytest
from pathlib import Path
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.storage.repositories.execution_repo import ExecutionRepository
from app.models.project import Project
from app.models.execution import Execution, ExecutionStatus


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
