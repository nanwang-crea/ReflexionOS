import pytest
from app.tools.shell_tool import ShellTool
from app.security.shell_security import ShellSecurity, ShellSecurityError


class TestShellTool:
    
    @pytest.fixture
    def shell_tool(self):
        security = ShellSecurity()
        return ShellTool(security)
    
    @pytest.mark.asyncio
    async def test_execute_allowed_command(self, shell_tool):
        result = await shell_tool.execute({
            "command": "echo hello"
        })
        
        assert result.success is True
        assert "hello" in result.output
    
    @pytest.mark.asyncio
    async def test_execute_forbidden_command(self, shell_tool):
        result = await shell_tool.execute({
            "command": "rm -rf /"
        })
        
        assert result.success is False
        assert "危险命令" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_python_command(self, shell_tool):
        result = await shell_tool.execute({
            "command": "python --version"
        })
        
        assert result.success is True
        assert "Python" in result.output
