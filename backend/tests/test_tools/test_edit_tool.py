import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.edit_tool import EditTool


class TestEditToolStrReplace:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def edit_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return EditTool(security)

    @pytest.mark.asyncio
    async def test_exact_match(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("def hello():\n    print('hello')\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "print('hello')",
            "new_string": "print('hello world')",
        })
        assert result.success is True
        assert "hello world" in f.read_text()

    @pytest.mark.asyncio
    async def test_whitespace_flex_match(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("def hello():\n    print('hello')\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "def hello():\nprint('hello')",
            "new_string": "def hello():\nprint('world')",
        })
        assert result.success is True
        assert "world" in f.read_text()

    @pytest.mark.asyncio
    async def test_anchor_match(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("class Foo:\n    def bar(self):\n        pass\n\n    def baz(self):\n        pass\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "class Foo:\n    def bar(self):\n        something_different\n\n    def baz(self):\n        pass",
            "new_string": "class Foo:\n    def bar(self):\n        new_implementation\n\n    def baz(self):\n        pass",
        })
        assert result.success is True
        assert "new_implementation" in f.read_text()

    @pytest.mark.asyncio
    async def test_replace_all(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("old_value\nkeep\nold_value\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "old_value",
            "new_string": "new_value",
            "replace_all": True,
        })
        assert result.success is True
        content = f.read_text()
        assert content.count("new_value") == 2
        assert "old_value" not in content

    @pytest.mark.asyncio
    async def test_not_found(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("line1\nline2\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "nonexistent",
            "new_string": "replacement",
        })
        assert result.success is False
        assert "未找到" in result.error

    @pytest.mark.asyncio
    async def test_multiple_matches_rejects(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("repeat\nkeep\nrepeat\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "repeat",
            "new_string": "changed",
        })
        assert result.success is False
        assert "多个位置" in result.error

    @pytest.mark.asyncio
    async def test_empty_old_string_creates_file(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "new_file.py"
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "",
            "new_string": "print('created')\n",
        })
        assert result.success is True
        assert f.read_text() == "print('created')\n"

    @pytest.mark.asyncio
    async def test_empty_old_string_appends(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("existing\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "",
            "new_string": "appended\n",
        })
        assert result.success is True
        content = f.read_text()
        assert "existing" in content
        assert "appended" in content

    @pytest.mark.asyncio
    async def test_crlf_preserved(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_bytes(b"line1\r\nline2\r\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "line1",
            "new_string": "line_one",
        })
        assert result.success is True
        content = f.read_bytes()
        assert content == b"line_one\r\nline2\r\n"

    @pytest.mark.asyncio
    async def test_same_old_new_rejected(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("hello\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "hello",
            "new_string": "hello",
        })
        assert result.success is False
        assert "不能相同" in result.error

    @pytest.mark.asyncio
    async def test_missing_action(self, edit_tool):
        result = await edit_tool.execute({"path": "/tmp/test.py"})
        assert result.success is False
        assert "action" in result.error

    @pytest.mark.asyncio
    async def test_missing_path(self, edit_tool):
        result = await edit_tool.execute({"action": "str_replace"})
        assert result.success is False
        assert "path" in result.error

    @pytest.mark.asyncio
    async def test_missing_old_string(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("hello\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "new_string": "world",
        })
        assert result.success is False
        assert "old_string" in result.error

    @pytest.mark.asyncio
    async def test_escape_normalizer_match(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("hello\tworld\n")
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(f),
            "old_string": "hello\\tworld",
            "new_string": "hello\tuniverse",
        })
        assert result.success is True
        assert "hello\tuniverse" in f.read_text()

    @pytest.mark.asyncio
    async def test_file_not_found(self, edit_tool, temp_dir):
        result = await edit_tool.execute({
            "action": "str_replace",
            "path": str(Path(temp_dir) / "nonexistent.py"),
            "old_string": "foo",
            "new_string": "bar",
        })
        assert result.success is False
        assert "文件不存在" in result.error


class TestEditToolWrite:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def edit_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return EditTool(security)

    @pytest.mark.asyncio
    async def test_write_creates_new_file(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "new.py"
        result = await edit_tool.execute({
            "action": "write",
            "path": str(f),
            "content": "hello",
        })
        assert result.success is True
        assert f.read_text() == "hello"

    @pytest.mark.asyncio
    async def test_write_missing_content(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "new.py"
        result = await edit_tool.execute({
            "action": "write",
            "path": str(f),
        })
        assert result.success is False
        assert "content" in result.error

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "sub" / "dir" / "new.py"
        result = await edit_tool.execute({
            "action": "write",
            "path": str(f),
            "content": "nested",
        })
        assert result.success is True
        assert f.read_text() == "nested"


class TestEditToolPatch:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def edit_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return EditTool(security)

    @pytest.mark.asyncio
    async def test_unified_diff(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.py"
        f.write_text("def hello():\n    print('hello')\n")
        patch = f"""--- a/{f}
+++ b/{f}
@@ -1,2 +1,2 @@
 def hello():
-    print('hello')
+    print('hello world')
"""
        result = await edit_tool.execute({"action": "patch", "path": str(f), "patch": patch})
        assert result.success is True
        assert "hello world" in f.read_text()

    @pytest.mark.asyncio
    async def test_codex_style_update(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "test.txt"
        f.write_text("alpha\nbeta\ngamma\n")
        patch = f"""*** Begin Patch
*** Update File: {f}
@@
 alpha
-beta
+changed
 gamma
*** End Patch
"""
        result = await edit_tool.execute({"action": "patch", "path": str(f), "patch": patch})
        assert result.success is True
        assert f.read_text() == "alpha\nchanged\ngamma\n"

    @pytest.mark.asyncio
    async def test_codex_style_add(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "new.txt"
        patch = f"""*** Begin Patch
*** Add File: {f}
+line one
+line two
*** End Patch
"""
        result = await edit_tool.execute({"action": "patch", "path": str(f), "patch": patch})
        assert result.success is True
        assert f.read_text() == "line one\nline two\n"

    @pytest.mark.asyncio
    async def test_codex_style_delete(self, edit_tool, temp_dir):
        f = Path(temp_dir) / "delete_me.txt"
        f.write_text("remove me\n")
        patch = f"""*** Begin Patch
*** Delete File: {f}
*** End Patch
"""
        result = await edit_tool.execute({"action": "patch", "path": str(f), "patch": patch})
        assert result.success is True
        assert not f.exists()

    @pytest.mark.asyncio
    async def test_patch_missing_parameter(self, edit_tool):
        result = await edit_tool.execute({"action": "patch", "path": "/tmp/test.py"})
        assert result.success is False
        assert "patch" in result.error

    @pytest.mark.asyncio
    async def test_unknown_action(self, edit_tool):
        result = await edit_tool.execute({"action": "invalid", "path": "/tmp/test.py"})
        assert result.success is False
        assert "未知" in result.error
