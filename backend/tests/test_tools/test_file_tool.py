import os
import tempfile
from pathlib import Path

import pytest

from app.security.path_security import PathSecurity
from app.tools.file_tool import FileTool


class TestFileTool:
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)
    
    @pytest.fixture
    def file_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return FileTool(security)

    def test_schema_exposes_read_limit_for_model_calls(self, file_tool):
        read_schema = self._schema_for_action(file_tool, "read")
        limit_schema = read_schema["properties"]["limit"]

        assert limit_schema["minimum"] == 30
        assert limit_schema["maximum"] == 100
        assert limit_schema["default"] == 80
        assert "start_line" in limit_schema["description"]

    def test_schema_scopes_parameters_by_action(self, file_tool):
        read_props = self._schema_for_action(file_tool, "read")["properties"]
        search_props = self._schema_for_action(file_tool, "search")["properties"]
        write_props = self._schema_for_action(file_tool, "write")["properties"]

        assert {"action", "path", "start_line", "limit", "line", "context"} == set(read_props)
        assert "end_line" not in read_props
        assert {"action", "path", "query"} == set(search_props)
        assert {"action", "path", "content"} == set(write_props)

    def _schema_for_action(self, file_tool, action: str) -> dict:
        variants = file_tool.get_schema()["parameters"]["oneOf"]
        return next(
            variant
            for variant in variants
            if variant["properties"]["action"]["enum"] == [action]
        )
    
    @pytest.mark.asyncio
    async def test_read_file_success(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("print('hello')")
        
        result = await file_tool.execute({
            "action": "read",
            "path": str(test_file)
        })
        
        assert result.success is True
        assert "print('hello')" in result.data["content"]
        assert result.data["total_lines"] == 1
    
    @pytest.mark.asyncio
    async def test_read_file_with_line_range(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("line1\nline2\nline3\nline4\nline5")
        
        result = await file_tool.execute({
            "action": "read",
            "path": str(test_file),
            "start_line": 2,
            "end_line": 4
        })
        
        assert result.success is True
        assert result.data["start_line"] == 2
        assert result.data["end_line"] == 4
        assert "line2" in result.data["content"]
        assert "line4" in result.data["content"]

    @pytest.mark.asyncio
    async def test_read_file_uses_limit_and_ignores_zero_line_hint(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        lines = [f"line{i}" for i in range(1, 121)]
        test_file.write_text("\n".join(lines))

        result = await file_tool.execute({
            "action": "read",
            "path": str(test_file),
            "start_line": 1,
            "limit": 30,
            "line": 0,
            "context": 0
        })

        assert result.success is True
        assert result.data["start_line"] == 1
        assert result.data["end_line"] == 30
        assert "line1" in result.data["content"]
        assert "line30" in result.data["content"]
        assert "line31" not in result.data["content"]

    @pytest.mark.asyncio
    async def test_read_file_clamps_limit_between_30_and_100(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        lines = [f"line{i}" for i in range(1, 121)]
        test_file.write_text("\n".join(lines))

        small_limit = await file_tool.execute({
            "action": "read",
            "path": str(test_file),
            "start_line": 1,
            "limit": 1
        })
        large_limit = await file_tool.execute({
            "action": "read",
            "path": str(test_file),
            "start_line": 1,
            "limit": 500
        })

        assert small_limit.success is True
        assert small_limit.data["end_line"] == 30
        assert large_limit.success is True
        assert large_limit.data["end_line"] == 100

    @pytest.mark.asyncio
    async def test_read_file_rejects_invalid_line_range(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("line1\nline2")

        result = await file_tool.execute({
            "action": "read",
            "path": str(test_file),
            "start_line": 1,
            "end_line": 0
        })

        assert result.success is False
        assert "结束行号必须大于等于起始行号" in result.error
    
    @pytest.mark.asyncio
    async def test_read_file_with_context(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        lines = [f"line{i}" for i in range(1, 21)]
        test_file.write_text("\n".join(lines))
        
        result = await file_tool.execute({
            "action": "read",
            "path": str(test_file),
            "line": 10,
            "context": 2
        })
        
        assert result.success is True
        assert "line8" in result.data["content"]
        assert "line10" in result.data["content"]
        assert "line12" in result.data["content"]
    
    @pytest.mark.asyncio
    async def test_search_in_file(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n\ndef world():\n    print('world')")
        
        result = await file_tool.execute({
            "action": "search",
            "path": str(test_file),
            "query": "def"
        })
        
        assert result.success is True
        assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_search_requires_query(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("line1\nline2")

        result = await file_tool.execute({
            "action": "search",
            "path": str(test_file),
            "query": ""
        })

        assert result.success is False
        assert "缺少 query 参数" in result.error
    
    @pytest.mark.asyncio
    async def test_read_file_outside_workspace(self, file_tool):
        result = await file_tool.execute({
            "action": "read",
            "path": "/etc/passwd"
        })
        assert result.success is False
        assert "不在允许范围内" in result.error
    
    @pytest.mark.asyncio
    async def test_write_file_success(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "output.txt"
        
        result = await file_tool.execute({
            "action": "write",
            "path": str(test_file),
            "content": "Hello World"
        })
        
        assert result.success is True
        assert test_file.read_text() == "Hello World"
    
    @pytest.mark.asyncio
    async def test_list_directory(self, file_tool, temp_dir):
        (Path(temp_dir) / "file1.txt").touch()
        (Path(temp_dir) / "file2.py").touch()
        
        result = await file_tool.execute({
            "action": "list",
            "path": temp_dir
        })
        
        assert result.success is True
        assert len(result.data["files"]) == 2
    
    @pytest.mark.asyncio
    async def test_delete_file(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "delete_me.txt"
        test_file.write_text("delete me")
        
        result = await file_tool.execute({
            "action": "delete",
            "path": str(test_file)
        })
        
        assert result.success is True
        assert not test_file.exists()
