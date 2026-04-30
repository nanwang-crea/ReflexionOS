import pytest

from app.memory.curated_store import CuratedEntry, CuratedMemoryStore
from app.tools.memory_tool import MemoryTool


async def _add_entry(tool: MemoryTool, *, project_id: str, entry: CuratedEntry):
    return await tool.execute(
        {
            "action": "add",
            "project_id": project_id,
            "entry": entry.model_dump(mode="json"),
        }
    )


async def _replace_entry(
    tool: MemoryTool,
    *,
    project_id: str,
    target: str,
    old_summary: str,
    entry: CuratedEntry,
):
    return await tool.execute(
        {
            "action": "replace",
            "project_id": project_id,
            "target": target,
            "old_summary": old_summary,
            "entry": entry.model_dump(mode="json"),
        }
    )


async def _remove_entry(tool: MemoryTool, *, project_id: str, target: str, summary: str):
    return await tool.execute(
        {
            "action": "remove",
            "project_id": project_id,
            "target": target,
            "summary": summary,
        }
    )


def test_memory_tool_schema_includes_actions():
    tool = MemoryTool(store=CuratedMemoryStore(base_dir="__unused__"))
    schema = tool.get_schema()
    assert schema["name"] == "memory"
    assert "add" in schema["parameters"]["properties"]["action"]["enum"]
    assert "replace" in schema["parameters"]["properties"]["action"]["enum"]
    assert "remove" in schema["parameters"]["properties"]["action"]["enum"]


@pytest.mark.asyncio
async def test_memory_tool_add_writes_user_markdown(tmp_path):
    store = CuratedMemoryStore(base_dir=tmp_path)
    tool = MemoryTool(store=store)

    entry = CuratedEntry(
        target="user",
        type="preference",
        scope="project",
        source="user_explicit",
        confidence="high",
        status="active",
        source_refs=["msg-1"],
        summary="默认使用中文回复。",
    )

    result = await _add_entry(tool, project_id="project-1", entry=entry)
    assert result.success is True
    assert result.data is not None
    assert result.data["success"] is True

    rendered = (tmp_path / "projects" / "project-1" / "USER.md").read_text(encoding="utf-8")
    assert "默认使用中文回复。" in rendered


@pytest.mark.asyncio
async def test_memory_tool_add_returns_conflict_when_rule_drifts(tmp_path):
    store = CuratedMemoryStore(base_dir=tmp_path)
    tool = MemoryTool(store=store)

    first = CuratedEntry(
        target="memory",
        type="constraint",
        scope="project",
        source="derived",
        confidence="high",
        status="active",
        source_refs=["msg-1"],
        summary="默认不要直接写入用户仓库。",
    )
    await _add_entry(tool, project_id="project-1", entry=first)

    second = first.model_copy(
        update={"summary": "默认直接写入用户仓库。", "source_refs": ["msg-2"]}
    )
    result = await _add_entry(tool, project_id="project-1", entry=second)

    assert result.success is False
    assert result.data is not None
    assert result.data["conflict"] is True


@pytest.mark.asyncio
async def test_memory_tool_replace_supersedes_old_entry(tmp_path):
    store = CuratedMemoryStore(base_dir=tmp_path)
    tool = MemoryTool(store=store)

    old_entry = CuratedEntry(
        target="user",
        type="preference",
        scope="project",
        source="user_explicit",
        confidence="high",
        status="active",
        source_refs=["msg-1"],
        summary="默认使用中文回复。",
    )
    await _add_entry(tool, project_id="project-1", entry=old_entry)

    new_entry = old_entry.model_copy(
        update={"summary": "默认使用英文回复。", "source_refs": ["msg-2"]}
    )
    result = await _replace_entry(
        tool,
        project_id="project-1",
        target="user",
        old_summary="默认使用中文回复。",
        entry=new_entry,
    )

    assert result.success is True

    rendered = (tmp_path / "projects" / "project-1" / "USER.md").read_text(encoding="utf-8")
    assert "默认使用英文回复。" in rendered
    assert "默认使用中文回复。" not in rendered


@pytest.mark.asyncio
async def test_memory_tool_remove_hides_entry_from_markdown(tmp_path):
    store = CuratedMemoryStore(base_dir=tmp_path)
    tool = MemoryTool(store=store)

    entry = CuratedEntry(
        target="user",
        type="preference",
        scope="project",
        source="user_explicit",
        confidence="high",
        status="active",
        source_refs=["msg-1"],
        summary="默认使用中文回复。",
    )
    await _add_entry(tool, project_id="project-1", entry=entry)

    removed = await _remove_entry(
        tool,
        project_id="project-1",
        target="user",
        summary="默认使用中文回复。",
    )
    assert removed.success is True
    assert removed.data is not None
    assert removed.data["removed"] is True

    rendered = (tmp_path / "projects" / "project-1" / "USER.md").read_text(encoding="utf-8")
    assert "默认使用中文回复。" not in rendered


@pytest.mark.asyncio
async def test_memory_tool_uses_settings_base_dir_by_default(monkeypatch, tmp_path):
    # Make sure we don't write into the actual home directory during tests.
    from app.config.settings import config_manager

    monkeypatch.setattr(
        config_manager.settings.memory, "base_dir", str(tmp_path / "configured-memory")
    )

    tool = MemoryTool()  # store + base_dir should resolve from settings

    entry = CuratedEntry(
        target="user",
        type="preference",
        scope="project",
        source="user_explicit",
        confidence="high",
        status="active",
        source_refs=["msg-1"],
        summary="默认使用中文回复。",
    )
    result = await _add_entry(tool, project_id="project-1", entry=entry)
    assert result.success is True

    rendered_path = tmp_path / "configured-memory" / "projects" / "project-1" / "USER.md"
    assert rendered_path.exists()
    assert "默认使用中文回复。" in rendered_path.read_text(encoding="utf-8")
