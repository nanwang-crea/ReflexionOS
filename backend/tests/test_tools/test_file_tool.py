import pytest
import tempfile
import os
from pathlib import Path
from app.tools.file_tool import FileTool
from app.security.path_security import PathSecurity, SecurityError


class TestFileTool:
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)
    
    @pytest.fixture
    def file_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return FileTool(security)
    
    @pytest.mark.asyncio
    async def test_read_file_success(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("print('hello')")
        
        result = await file_tool.execute({
            "action": "read",
            "path": str(test_file)
        })
        
        assert result.success is True
        assert result.data["content"] == "print('hello')"
    
    @pytest.mark.asyncio
    async def test_read_file_outside_workspace(self, file_tool):
        result = await file_tool.execute({
            "action": "read",
            "path": "/etc/passwd"
        })
        assert result.success is False
        assert "不在允许的访问范围内" in result.error
    
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
