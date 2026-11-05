"""memory_remember 工具的测试：写入位置/追加语义/校验拒绝（空、多行、超长、机密）。"""
import os
from pathlib import Path

import pytest

from app.tools.memory_remember_tool import MemoryRememberTool


@pytest.fixture
def home_dir(tmp_path, monkeypatch):
    """隔离的全局目录：monkeypatch Path.home 让 global 档写到临时目录。"""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    return fake_home


@pytest.fixture
def project_dir(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    return project


@pytest.mark.asyncio
async def test_project_scope_appends_to_project_memory(home_dir, project_dir):
    tool = MemoryRememberTool(project_root=str(project_dir))
    result = await tool.execute({"content": "用户偏好中文回复", "scope": "project"})

    assert result.success is True
    memory_file = project_dir / ".reflexion" / "memory.md"
    assert memory_file.exists()
    assert "- 用户偏好中文回复" in memory_file.read_text(encoding="utf-8")
    assert result.data["scope"] == "project"


@pytest.mark.asyncio
async def test_global_scope_writes_to_global_reflexion_dir(home_dir, project_dir):
    tool = MemoryRememberTool(project_root=str(project_dir))
    result = await tool.execute({"content": "全局偏好：简洁", "scope": "global"})

    assert result.success is True
    memory_file = home_dir / ".reflexion" / "memory.md"
    assert "- 全局偏好：简洁" in memory_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_appends_preserve_existing_entries(home_dir, project_dir):
    tool = MemoryRememberTool(project_root=str(project_dir))
    await tool.execute({"content": "第一条"})
    await tool.execute({"content": "第二条"})

    memory_file = project_dir / ".reflexion" / "memory.md"
    content = memory_file.read_text(encoding="utf-8")
    assert "- 第一条" in content
    assert "- 第二条" in content


@pytest.mark.asyncio
async def test_project_scope_without_project_root_fails(home_dir):
    tool = MemoryRememberTool(project_root=None)
    result = await tool.execute({"content": "x", "scope": "project"})
    assert result.success is False
    assert "项目" in result.error


@pytest.mark.asyncio
async def test_rejects_empty_and_multiline_and_oversized(home_dir, project_dir):
    tool = MemoryRememberTool(project_root=str(project_dir))

    empty = await tool.execute({"content": "   "})
    assert empty.success is False

    multiline = await tool.execute({"content": "第一行\n第二行"})
    assert multiline.success is False
    assert "单行" in multiline.error

    oversized = await tool.execute({"content": "x" * 501})
    assert oversized.success is False
    assert "500" in oversized.error


@pytest.mark.asyncio
async def test_rejects_secret_like_content(home_dir, project_dir):
    tool = MemoryRememberTool(project_root=str(project_dir))
    for content in [
        "我的 key 是 sk-abcdefghijklmnopqrstuvwxyz123456",
        "password = hunter2secret",
        "-----BEGIN RSA PRIVATE KEY-----",
    ]:
        result = await tool.execute({"content": content})
        assert result.success is False, content
        assert "凭据" in result.error or "机密" in result.error


@pytest.mark.asyncio
async def test_invalid_scope_rejected(home_dir, project_dir):
    tool = MemoryRememberTool(project_root=str(project_dir))
    result = await tool.execute({"content": "x", "scope": "session"})
    assert result.success is False
