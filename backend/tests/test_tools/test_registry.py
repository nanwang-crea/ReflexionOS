import pytest
import tempfile
import os
from app.tools.registry import ToolRegistry
from app.tools.file_tool import FileTool
from app.tools.shell_tool import ShellTool
from app.security.path_security import PathSecurity
from app.security.shell_security import ShellSecurity


class TestToolRegistry:
    
    @pytest.fixture
    def registry(self):
        return ToolRegistry()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)
    
    @pytest.fixture
    def file_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return FileTool(security)
    
    @pytest.fixture
    def shell_tool(self):
        security = ShellSecurity()
        return ShellTool(security)
    
    def test_register_tool(self, registry, file_tool):
        registry.register(file_tool)
        
        assert "file" in registry.tools
        assert registry.tools["file"] == file_tool
    
    def test_register_multiple_tools(self, registry, file_tool, shell_tool):
        registry.register(file_tool)
        registry.register(shell_tool)
        
        assert len(registry.tools) == 2
        assert "file" in registry.tools
        assert "shell" in registry.tools
    
    def test_get_tool_schema(self, registry, file_tool):
        registry.register(file_tool)
        
        schema = registry.get_tool_schema("file")
        
        assert schema["name"] == "file"
        assert "description" in schema
    
    def test_get_all_schemas(self, registry, file_tool, shell_tool):
        registry.register(file_tool)
        registry.register(shell_tool)
        
        schemas = registry.get_all_schemas()
        
        assert len(schemas) == 2
        assert any(s["name"] == "file" for s in schemas)
        assert any(s["name"] == "shell" for s in schemas)
    
    def test_list_tools(self, registry, file_tool, shell_tool):
        registry.register(file_tool)
        registry.register(shell_tool)
        
        tools = registry.list_tools()
        
        assert len(tools) == 2
        assert "file" in tools
        assert "shell" in tools
