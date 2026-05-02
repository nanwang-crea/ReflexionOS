import os
import tempfile

import pytest

from app.security.path_security import PathSecurity, SecurityError
from app.security.shell_security import ShellSecurity
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
        assert result.approval_required is False
        assert "递归删除" in result.error or "禁止" in result.error

    @pytest.mark.asyncio
    async def test_execute_python_command(self, shell_tool):
        result = await shell_tool.execute({"command": "python --version"})

        assert result.success is True
        assert "Python" in result.output

    @pytest.mark.asyncio
    async def test_execute_command_with_pipe(self, shell_tool):
        result = await shell_tool.execute({"command": "echo hello | wc -c"})

        assert result.approval_required is True
        assert result.approval is not None

    @pytest.mark.asyncio
    async def test_execute_common_command(self, shell_tool):
        result = await shell_tool.execute({"command": "which python"})

        assert result.success is True
        assert "python" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_rejects_path_arguments_outside_project_root(self, shell_tool):
        result = await shell_tool.execute({"command": "cat ~/.ssh/id_rsa"})

        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_rejects_python_inline_code(self, shell_tool):
        result = await shell_tool.execute({"command": "python -c 'print(123)'"})

        assert result.approval_required is True
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_pipe_command_returns_approval_required(self, shell_tool):
        result = await shell_tool.execute({"command": "echo hello | wc -c"})

        assert result.approval_required is True
        assert result.success is False
        assert result.approval is not None
        assert "shell" in result.approval.payload.get("execution_mode", "")
        assert result.approval.tool_name == "shell"

    @pytest.mark.asyncio
    async def test_execute_rm_file_returns_approval_required(self, shell_tool):
        result = await shell_tool.execute({"command": "rm file.txt"})

        assert result.approval_required is True
        assert result.success is False
        assert result.approval is not None
        assert result.approval.payload.get("execution_mode") == "argv"

    @pytest.mark.asyncio
    async def test_execute_rm_rf_root_returns_deny(self, shell_tool):
        result = await shell_tool.execute({"command": "rm -rf /"})

        assert result.success is False
        assert result.approval_required is False
        assert "禁止" in result.error or "deny" in result.error.lower() or "递归删除" in result.error

    @pytest.mark.asyncio
    async def test_execute_python_inline_returns_approval_required(self, shell_tool):
        result = await shell_tool.execute({"command": "python -c 'print(123)'"})

        assert result.approval_required is True
        assert result.success is False

    @pytest.mark.asyncio
    async def test_execute_allowed_command_still_succeeds(self, shell_tool):
        result = await shell_tool.execute({"command": "echo hello"})

        assert result.success is True
        assert "hello" in result.output
        assert result.approval_required is False

    @pytest.mark.asyncio
    async def test_execute_with_approval_id_runs_approved_command(self, shell_tool):
        """When approval_id and approved_decision are provided, execute the stored decision."""
        from app.security.command_policy import CommandAction, CommandDecision, EnvironmentSnapshot

        decision = CommandDecision(
            action=CommandAction.ALLOW,
            execution_mode="argv",
            command="echo approved",
            argv=["echo", "approved"],
            cwd=shell_tool.path_security.base_dir,
            timeout=60,
            environment_snapshot=EnvironmentSnapshot(cwd=shell_tool.path_security.base_dir),
        )
        result = await shell_tool.execute(
            {"command": "echo approved", "_approved_decision": decision.model_dump()}
        )

        assert result.success is True
        assert "approved" in result.output

    @pytest.mark.asyncio
    async def test_execute_approved_shell_mode_command(self, shell_tool):
        """Approved shell-mode command uses create_subprocess_shell."""
        from app.security.command_policy import CommandAction, CommandDecision, EnvironmentSnapshot

        decision = CommandDecision(
            action=CommandAction.ALLOW,
            execution_mode="shell",
            command="echo hello && echo world",
            argv=None,
            cwd=shell_tool.path_security.base_dir,
            timeout=60,
            environment_snapshot=EnvironmentSnapshot(cwd=shell_tool.path_security.base_dir),
        )
        result = await shell_tool.execute(
            {"command": "echo hello && echo world", "_approved_decision": decision.model_dump()}
        )

        assert result.success is True
        assert "hello" in result.output
        assert "world" in result.output

    def test_schema_describes_posix_platform_for_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            tool = ShellTool(
                ShellSecurity(platform_name="darwin"),
                PathSecurity([root_dir], base_dir=root_dir),
            )

            schema = tool.get_schema()

            assert "当前平台: macOS" in schema["description"]
            assert "低风险命令直接执行" in schema["description"]
            assert "高风险命令" in schema["description"]

    def test_schema_describes_windows_platform_for_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            tool = ShellTool(
                ShellSecurity(platform_name="win32"),
                PathSecurity([root_dir], base_dir=root_dir),
            )

            schema = tool.get_schema()

            assert "当前平台: Windows" in schema["description"]
            assert "低风险命令直接执行" in schema["description"]

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
