import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.glob_tool import GlobTool


class TestGlobTool:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def glob_tool(self, temp_dir):
        security = PathSecurity([temp_dir], base_dir=temp_dir)
        return GlobTool(security)

    def test_schema_has_required_fields(self, glob_tool):
        schema = glob_tool.get_schema()
        assert schema["name"] == "glob"
        props = schema["parameters"]["properties"]
        assert "pattern" in props
        assert "path" in props
        assert schema["parameters"]["required"] == ["pattern"]

    @pytest.mark.asyncio
    async def test_glob_finds_python_files(self, glob_tool, temp_dir):
        (Path(temp_dir) / "a.py").touch()
        (Path(temp_dir) / "b.py").touch()
        (Path(temp_dir) / "c.js").touch()

        result = await glob_tool.execute({"pattern": "**/*.py", "path": temp_dir})

        assert result.success is True
        paths = [m["path"] for m in result.data["matches"]]
        assert any("a.py" in p for p in paths)
        assert any("b.py" in p for p in paths)
        assert not any("c.js" in p for p in paths)

    @pytest.mark.asyncio
    async def test_glob_finds_in_subdirectory(self, glob_tool, temp_dir):
        sub = Path(temp_dir) / "src"
        sub.mkdir()
        (sub / "main.py").touch()
        (sub / "util.py").touch()

        result = await glob_tool.execute({"pattern": "**/*.py", "path": temp_dir})

        assert result.success is True
        paths = [m["path"] for m in result.data["matches"]]
        assert any("main.py" in p for p in paths)

    @pytest.mark.asyncio
    async def test_glob_no_match(self, glob_tool, temp_dir):
        (Path(temp_dir) / "readme.md").touch()

        result = await glob_tool.execute({"pattern": "**/*.rs", "path": temp_dir})

        assert result.success is True
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_glob_rejects_path_outside_workspace(self, glob_tool):
        result = await glob_tool.execute({"pattern": "*.py", "path": "/etc"})

        assert result.success is False
        assert "不在允许范围内" in result.error
