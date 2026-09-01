import contextlib
import os
import subprocess
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def git_project(client):
    """Create a temporary git repo with a test file"""
    created_project_ids = []

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmpdir, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmpdir, check=True, capture_output=True,
        )

        file_path = os.path.join(tmpdir, "example.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=tmpdir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=tmpdir, check=True, capture_output=True,
        )

        class ProjectHelper:
            def __init__(self, path):
                self.path = path

            def create_project(self):
                pid = _create_project(client, self.path)
                created_project_ids.append(pid)
                return pid

        yield ProjectHelper(tmpdir)

    for pid in created_project_ids:
        _delete_project(client, pid)


def _create_project(client, path):
    resp = client.post("/api/projects", json={"name": "test", "path": path})
    assert resp.status_code == 200
    return resp.json()["id"]


def _delete_project(client, project_id):
    # 测试清理：删除项目失败可忽略（如已被其他用例清理）
    with contextlib.suppress(Exception):
        client.delete(f"/api/projects/{project_id}")


class TestFileContentAPI:
    def test_get_file_content_existing(self, client, git_project):
        project_id = git_project.create_project()
        resp = client.get("/api/files/content", params={"project_id": project_id, "path": "example.py"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert "def hello()" in data["content"]
        assert data["language"] == "python"

    def test_get_file_content_nonexistent(self, client, git_project):
        project_id = git_project.create_project()
        resp = client.get("/api/files/content", params={"project_id": project_id, "path": "nope.py"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["content"] == ""

    def test_get_file_content_path_traversal_blocked(self, client, git_project):
        project_id = git_project.create_project()
        resp = client.get("/api/files/content", params={"project_id": project_id, "path": "../etc/passwd"})
        assert resp.status_code in (400, 403)

    def test_get_diff_content_modified_file(self, client, git_project):
        project_id = git_project.create_project()

        file_path = os.path.join(git_project.path, "example.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("def hello():\n    return 'changed'\n")

        resp = client.get("/api/files/diff-content", params={"project_id": project_id, "path": "example.py"})
        assert resp.status_code == 200
        data = resp.json()
        assert "'world'" in data["original"]
        assert "'changed'" in data["modified"]
        assert data["language"] == "python"

    def test_get_diff_content_new_file(self, client, git_project):
        project_id = git_project.create_project()

        new_file = os.path.join(git_project.path, "new.ts")
        with open(new_file, "w", encoding="utf-8") as f:
            f.write("const x = 1;\n")

        resp = client.get("/api/files/diff-content", params={"project_id": project_id, "path": "new.ts"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["original"] == ""
        assert "const x = 1" in data["modified"]
        assert data["language"] == "typescript"

    def test_write_file_content(self, client, git_project):
        project_id = git_project.create_project()
        resp = client.post("/api/files/write", json={
            "project_id": project_id,
            "path": "written.py",
            "content": "print('hello')\n",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        file_path = os.path.join(git_project.path, "written.py")
        with open(file_path, encoding="utf-8") as f:
            assert f.read() == "print('hello')\n"

    def test_get_file_tree(self, client, git_project):
        project_id = git_project.create_project()

        resp = client.get("/api/files/tree", params={"project_id": project_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "tree" in data
        tree = data["tree"]
        names = [n["name"] for n in tree]
        assert "example.py" in names

        example_node = next(n for n in tree if n["name"] == "example.py")
        assert example_node["type"] == "file"
        assert example_node["path"] == "example.py"

    def test_write_file_content_sensitive_blocked(self, client, git_project):
        project_id = git_project.create_project()
        resp = client.post("/api/files/write", json={
            "project_id": project_id,
            "path": ".env",
            "content": "SECRET=abc\n",
        })
        assert resp.status_code in (400, 403)
