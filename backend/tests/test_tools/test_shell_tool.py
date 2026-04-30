import os
import tempfile

import pytest

from app.security.path_security import PathSecurity, SecurityError
from app.security.shell_security import ShellSecurity, ShellSecurityError
from app.tools.shell_tool import ShellTool


class TestShellTool:
    @pytest.fixture
    def shell_tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            path_security = PathSecurity([root_dir], base_dir=root_dir)
            security = ShellSecurity()
            yield ShellTool(security, path_security)

    @pytest.mark.asyncio
    async def test_execute_allowed_command(self, shell_tool):
        result = await shell_tool.execute({"command": "echo hello"})

        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_execute_forbidden_command(self, shell_tool):
        result = await shell_tool.execute({"command": "rm -rf /"})

        assert result.success is False
        assert "危险命令" in result.error

    @pytest.mark.asyncio
    async def test_execute_python_command(self, shell_tool):
        result = await shell_tool.execute({"command": "python --version"})

        assert result.success is True
        assert "Python" in result.output

    @pytest.mark.asyncio
    async def test_execute_command_with_pipe(self, shell_tool):
        result = await shell_tool.execute({"command": "echo hello | wc -c"})

        assert result.success is False
        assert "Shell 元语法" in result.error

    @pytest.mark.asyncio
    async def test_execute_common_command(self, shell_tool):
        result = await shell_tool.execute({"command": "which python"})

        assert result.success is True
        assert "python" in result.output.lower()

    def test_validate_dangerous_eval_command(self):
        security = ShellSecurity()

        with pytest.raises(ShellSecurityError, match="危险命令"):
            security.validate_command("eval echo hello")

    @pytest.mark.asyncio
    async def test_execute_rejects_path_arguments_outside_project_root(self, shell_tool):
        result = await shell_tool.execute({"command": "cat ~/.ssh/id_rsa"})

        assert result.success is False
        assert "路径不在允许范围内" in result.error

    @pytest.mark.asyncio
    async def test_execute_rejects_python_inline_code(self, shell_tool):
        result = await shell_tool.execute({"command": "python -c 'print(123)'"})

        assert result.success is False
        assert "危险命令" in result.error

    def test_validate_windows_delete_command(self):
        security = ShellSecurity(platform_name="win32")

        with pytest.raises(ShellSecurityError, match="危险命令"):
            security.validate_command("del C:\\Users\\me\\secret.txt")

    def test_validate_windows_shell_command(self):
        security = ShellSecurity(platform_name="win32")

        with pytest.raises(ShellSecurityError, match="危险命令"):
            security.validate_command("powershell -Command Get-ChildItem")

    def test_schema_describes_posix_platform_for_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            tool = ShellTool(
                ShellSecurity(platform_name="darwin"),
                PathSecurity([root_dir], base_dir=root_dir),
            )

            schema = tool.get_schema()

            assert "当前平台: macOS" in schema["description"]
            assert "pwd" in schema["parameters"]["properties"]["command"]["description"]
            assert "which python" in schema["parameters"]["properties"]["command"]["description"]

    def test_schema_describes_windows_platform_for_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            tool = ShellTool(
                ShellSecurity(platform_name="win32"),
                PathSecurity([root_dir], base_dir=root_dir),
            )

            schema = tool.get_schema()

            assert "当前平台: Windows" in schema["description"]
            assert "where python" in schema["parameters"]["properties"]["command"]["description"]
            assert "cmd /c" in schema["parameters"]["properties"]["command"]["description"]

    def test_validate_relative_cwd_within_project_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = os.path.realpath(tmpdir)
            nested_dir = os.path.join(project_root, "nested")
            os.makedirs(nested_dir)

            security = PathSecurity([project_root], base_dir=project_root)

            assert security.validate_path("nested") == nested_dir

    @pytest.mark.asyncio
    async def test_execute_uses_project_base_dir_by_default(self, shell_tool):
        result = await shell_tool.execute({"command": "pwd"})

        assert result.success is True
        assert result.output.strip() == shell_tool.path_security.base_dir

    @pytest.mark.asyncio
    async def test_execute_rejects_cwd_outside_project_root(self, shell_tool):
        result = await shell_tool.execute({"command": "pwd", "cwd": "/tmp"})

        assert result.success is False
        assert "路径不在允许范围内" in result.error

    def test_validate_sibling_path_outside_project_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parent_dir = os.path.realpath(tmpdir)
            project_root = os.path.join(parent_dir, "project")
            sibling_dir = os.path.join(parent_dir, "project-evil")
            os.makedirs(project_root)
            os.makedirs(sibling_dir)

            security = PathSecurity([project_root], base_dir=project_root)

            with pytest.raises(SecurityError, match="不在允许范围内"):
                security.validate_path(sibling_dir)
