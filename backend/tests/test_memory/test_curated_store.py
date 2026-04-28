from app.memory.curated_store import CuratedEntry, CuratedMemoryStore


def test_add_user_preference_renders_markdown(tmp_path):
    store = CuratedMemoryStore(base_dir=tmp_path)
    store.add_entry(
        project_id="project-1",
        entry=CuratedEntry(
            target="user",
            type="preference",
            scope="project",
            source="user_explicit",
            confidence="high",
            status="active",
            source_refs=["msg-1"],
            summary="默认使用中文回复。",
        ),
    )

    rendered = (tmp_path / "projects" / "project-1" / "USER.md").read_text(encoding="utf-8")
    assert "默认使用中文回复。" in rendered


def test_add_entry_returns_conflict_when_active_rule_disagrees(tmp_path):
    store = CuratedMemoryStore(base_dir=tmp_path)
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
    store.add_entry(project_id="project-1", entry=first)

    second = first.model_copy(update={"summary": "默认直接写入用户仓库。", "source_refs": ["msg-2"]})
    result = store.add_entry(project_id="project-1", entry=second)

    assert result.conflict is True
    assert result.conflicting_entry is not None
    assert result.conflicting_entry.summary == "默认不要直接写入用户仓库。"

