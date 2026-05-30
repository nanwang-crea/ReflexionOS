import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.grep_tool import GrepTool


class TestGrepTool:
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)

    @pytest.fixture
    def grep_tool(self, temp_dir):
        security = PathSecurity([temp_dir], base_dir=temp_dir)
        return GrepTool(security)

    def test_schema_has_required_fields(self, grep_tool):
        schema = grep_tool.get_schema()
        assert schema["name"] == "grep"
        props = schema["parameters"]["properties"]
        assert "pattern" in props
        assert "path" in props
        assert "include" in props
        assert schema["parameters"]["required"] == ["pattern"]

    @pytest.mark.asyncio
    async def test_grep_finds_pattern_in_file(self, grep_tool, temp_dir):
        test_file = Path(temp_dir) / "example.py"
        test_file.write_text("def hello():\n    print('hello')\n\ndef world():\n    print('world')")

        result = await grep_tool.execute({"pattern": "def", "path": str(test_file)})

        assert result.success is True
        assert result.data["count"] >= 2

    @pytest.mark.asyncio
    async def test_grep_finds_pattern_in_directory(self, grep_tool, temp_dir):
        (Path(temp_dir) / "a.py").write_text("def alpha(): pass")
        (Path(temp_dir) / "b.py").write_text("def beta(): pass")

        result = await grep_tool.execute({"pattern": "def", "path": temp_dir})

        assert result.success is True
        assert result.data["count"] >= 2

    @pytest.mark.asyncio
    async def test_grep_with_include_filter(self, grep_tool, temp_dir):
        (Path(temp_dir) / "code.py").write_text("target_string here")
        (Path(temp_dir) / "data.json").write_text('{"target_string": true}')

        result = await grep_tool.execute({
            "pattern": "target_string",
            "path": temp_dir,
            "include": "*.py",
        })

        assert result.success is True
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_grep_no_match(self, grep_tool, temp_dir):
        (Path(temp_dir) / "empty.py").write_text("nothing here")

        result = await grep_tool.execute({"pattern": "nonexistent_pattern_xyz", "path": temp_dir})

        assert result.success is True
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_grep_rejects_path_outside_workspace(self, grep_tool):
        result = await grep_tool.execute({"pattern": "test", "path": "/etc/passwd"})

        assert result.success is False
        assert "不在允许范围内" in result.error

    @pytest.mark.asyncio
    async def test_grep_limits_results_globally_to_100_matches(self, grep_tool, temp_dir):
        for index in range(120):
            (Path(temp_dir) / f"file_{index}.py").write_text(f"target_{index} = True\n")

        result = await grep_tool.execute({"pattern": "target_", "path": temp_dir})

        assert result.success is True
        assert result.data["count"] == 100
        assert len(result.data["matches"]) == 100
        output_matches = [
            line for line in result.output.splitlines()
            if ":1:" in line and "target_" in line
        ]
        assert len(output_matches) == 100
