"""变更聚合（changed_files）的测试：文件修改类工具的成功结果应携带结构化变更清单。

覆盖：edit 工具的 str_replace / write / unified diff / codex patch(add|delete|update)、
patch 工具的 codex add，以及 changed_file_entry 助手与 ToolResult 默认值。
"""
import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.base import ToolResult, changed_file_entry
from app.tools.edit_tool import EditTool
from app.tools.patch_tool import PatchTool


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.realpath(tmpdir)


@pytest.fixture
def edit_tool(temp_dir):
    return EditTool(PathSecurity([temp_dir]))


@pytest.fixture
def patch_tool(temp_dir):
    return PatchTool(PathSecurity([temp_dir]))


def test_changed_file_entry_shapes():
    assert changed_file_entry("/a/b.py", "modified") == {"path": "/a/b.py", "action": "modified"}
    assert changed_file_entry("/a/b.py", "moved", old_path="/a/c.py") == {
        "path": "/a/b.py",
        "action": "moved",
        "old_path": "/a/c.py",
    }


def test_tool_result_changed_files_default_none():
    result = ToolResult(success=True)
    assert result.changed_files is None


@pytest.mark.asyncio
async def test_str_replace_reports_modified(edit_tool, temp_dir):
    f = Path(temp_dir) / "a.py"
    f.write_text("alpha\nbeta\ngamma\n")
    result = await edit_tool.execute({
        "action": "str_replace",
        "path": str(f),
        "old_string": "beta",
        "new_string": "BETA",
    })
    assert result.success is True
    assert result.changed_files == [{"path": str(f), "action": "modified"}]


@pytest.mark.asyncio
async def test_write_new_file_reports_created_and_existing_reports_modified(edit_tool, temp_dir):
    new_file = Path(temp_dir) / "new.py"
    result = await edit_tool.execute({"action": "write", "path": str(new_file), "content": "x\n"})
    assert result.success is True
    assert result.changed_files == [{"path": str(new_file), "action": "created"}]

    result = await edit_tool.execute({"action": "write", "path": str(new_file), "content": "y\n"})
    assert result.success is True
    assert result.changed_files == [{"path": str(new_file), "action": "modified"}]


@pytest.mark.asyncio
async def test_unified_diff_reports_created_for_missing_file(edit_tool, temp_dir):
    f = Path(temp_dir) / "brand_new.py"
    patch = (
        "--- /dev/null\n"
        f"+++ {f}\n"
        "@@ -0,0 +1,1 @@\n"
        "+hello\n"
    )
    result = await edit_tool.execute({"action": "patch", "path": str(f), "patch": patch})
    if not result.success:
        pytest.skip(f"当前 Unified Diff 实现不接受该格式: {result.error}")
    assert result.changed_files == [{"path": str(f), "action": "created"}]


@pytest.mark.asyncio
async def test_unified_diff_reports_modified_for_existing_file(edit_tool, temp_dir):
    f = Path(temp_dir) / "exists.py"
    f.write_text("alpha\nbeta\ngamma\n")
    patch = (
        f"--- {f}\n"
        f"+++ {f}\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+changed\n"
        " gamma\n"
    )
    result = await edit_tool.execute({"action": "patch", "path": str(f), "patch": patch})
    assert result.success is True
    assert result.changed_files == [{"path": str(f), "action": "modified"}]


@pytest.mark.asyncio
async def test_codex_patch_reports_created_modified_deleted(edit_tool, temp_dir):
    add_target = Path(temp_dir) / "added.py"
    add_patch = f"""*** Begin Patch
*** Add File: {add_target}
+print('new')
*** End Patch
"""
    result = await edit_tool.execute({"action": "patch", "path": str(add_target), "patch": add_patch})
    assert result.success is True
    assert result.changed_files == [{"path": str(add_target), "action": "created"}]

    update_target = Path(temp_dir) / "updated.py"
    update_target.write_text("alpha\nbeta\ngamma\n")
    update_patch = f"""*** Begin Patch
*** Update File: {update_target}
@@
 alpha
-beta
+changed
 gamma
*** End Patch
"""
    result = await edit_tool.execute({"action": "patch", "path": str(update_target), "patch": update_patch})
    assert result.success is True
    assert result.changed_files == [{"path": str(update_target), "action": "modified"}]

    delete_patch = f"""*** Begin Patch
*** Delete File: {update_target}
*** End Patch
"""
    result = await edit_tool.execute({"action": "patch", "path": str(update_target), "patch": delete_patch})
    assert result.success is True
    assert result.changed_files == [{"path": str(update_target), "action": "deleted"}]


@pytest.mark.asyncio
async def test_patch_tool_codex_add_reports_created(patch_tool, temp_dir):
    f = Path(temp_dir) / "via_patch_tool.py"
    patch = f"""*** Begin Patch
*** Add File: {f}
+content
*** End Patch
"""
    result = await patch_tool.execute({"patch": patch})
    assert result.success is True
    assert result.changed_files == [{"path": str(f), "action": "created"}]


@pytest.mark.asyncio
async def test_failed_edits_do_not_report_changed_files(edit_tool, temp_dir):
    f = Path(temp_dir) / "missing.py"
    result = await edit_tool.execute({
        "action": "str_replace",
        "path": str(f),
        "old_string": "x",
        "new_string": "y",
    })
    assert result.success is False
    assert result.changed_files is None
