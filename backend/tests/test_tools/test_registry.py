import os
import tempfile

import pytest

from app.security.path_security import PathSecurity
from app.security.shell_security import ShellSecurity
from app.tools.file_tool import FileTool
from app.tools.registry import ToolRegistry
from app.tools.shell_tool import ShellTool


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
        path_security = PathSecurity([os.getcwd()])
        security = ShellSecurity()
        return ShellTool(security, path_security)
    
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

    def test_get_tool_definitions_include_parameters(self, registry, file_tool, shell_tool):
        registry.register(file_tool)
        registry.register(shell_tool)

        definitions = registry.get_tool_definitions()
        definitions_by_name = {definition.name: definition for definition in definitions}
        file_variants = definitions_by_name["file"].parameters["oneOf"]
        file_read_schema = next(
            variant
            for variant in file_variants
            if variant["properties"]["action"]["enum"] == ["read"]
        )

        assert file_read_schema["properties"]["action"]["enum"] == ["read"]
        assert file_read_schema["properties"]["path"]["type"] == "string"
        assert file_read_schema["properties"]["limit"]["minimum"] == 30
        assert definitions_by_name["shell"].parameters["properties"]["command"]["type"] == "string"
        assert definitions_by_name["shell"].parameters["properties"]["cwd"]["type"] == "string"

    def test_get_tool_definitions_include_shell_platform_guidance(self, registry, temp_dir):
        shell_tool = ShellTool(
            ShellSecurity(platform_name="darwin"),
            PathSecurity([temp_dir], base_dir=temp_dir),
        )
        registry.register(shell_tool)

        [definition] = registry.get_tool_definitions()

        assert "当前平台: macOS" in definition.description
        assert "which python" in definition.parameters["properties"]["command"]["description"]
