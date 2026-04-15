import pytest
from app.models.project import Project, ProjectCreate


class TestProject:
    
    def test_create_project(self):
        data = {
            "name": "TestProject",
            "path": "/path/to/project",
            "language": "python"
        }
        project = ProjectCreate(**data)
        
        assert project.name == "TestProject"
        assert project.path == "/path/to/project"
        assert project.language == "python"
    
    def test_project_with_id(self):
        project = Project(
            id="proj-123",
            name="TestProject",
            path="/path/to/project",
            language="python"
        )
        
        assert project.id == "proj-123"
        assert project.name == "TestProject"
