import os
import sys
import tempfile
from pathlib import Path

import pytest

from app.errors import SecurityError
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.effect_category import EffectCategory
from app.security.path_security import PathSecurity, ExternalPathError
from app.security.sandbox.factory import NullSandbox
from app.security.session_trust_store import SessionTrustStore, TrustRule
from app.security.shell_security import ShellSecurity
from app.tools.shell_tool import ShellTool


class TestShellTool:
    @pytest.fixture
    def shell_tool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            path_security = PathSecurity([root_dir], base_dir=root_dir)
            security = ShellSecurity()
            registry = CommandEffectRegistry()
            sandbox = NullSandbox()
            yield ShellTool(security, path_security, registry, sandbox)

    @pytest.fixture
    def trust_store(self):
        return SessionTrustStore()

    @pytest.fixture
    def shell_tool_with_trust(self, trust_store):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            path_security = PathSecurity([root_dir], base_dir=root_dir)
            security = ShellSecurity()
            registry = CommandEffectRegistry()
            sandbox = NullSandbox()
            yield ShellTool(
                security, path_security, registry, sandbox,
                session_id="session-1", trust_store=trust_store,
            )

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
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 第一阶段不支持管道 |")
    async def test_execute_command_with_pipe(self, shell_tool):
        # READ_ONLY pipe chain (echo | wc) is now ALLOW under effect classification
        result = await shell_tool.execute({"command": "echo hello | wc -c"})

        assert result.success is True
        assert result.approval_required is False

    @pytest.mark.asyncio
    async def test_execute_common_command(self, shell_tool):
        # 跨平台兼容：Windows 用 where，Unix/Linux/macOS 用 which
        import platform
        command = "where python" if platform.system() == "Windows" else "which python"
        result = await shell_tool.execute({"command": command})

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
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 第一阶段只支持 git 命令，rm 会被拒绝")
    async def test_execute_pipe_command_returns_approval_required(self, shell_tool):
        # Destructive pipe chain (rm | something) requires approval
        result = await shell_tool.execute({"command": "rm file.txt && echo done"})

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
                CommandEffectRegistry(),
                NullSandbox(),
            )

            schema = tool.get_schema()

            assert "current platform: macOS" in schema["description"]
            assert "Low-risk commands execute directly" in schema["description"]
            assert "high-risk commands" in schema["description"]

    def test_schema_describes_windows_platform_for_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = os.path.realpath(tmpdir)
            tool = ShellTool(
                ShellSecurity(platform_name="win32"),
                PathSecurity([root_dir], base_dir=root_dir),
                CommandEffectRegistry(),
                NullSandbox(),
            )

            schema = tool.get_schema()

            assert "current platform: Windows" in schema["description"]
            assert "Low-risk commands execute directly" in schema["description"]

    def test_validate_relative_cwd_within_project_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = os.path.realpath(tmpdir)
            nested_dir = os.path.join(project_root, "nested")
            os.makedirs(nested_dir)

            security = PathSecurity([project_root], base_dir=project_root)

            assert security.validate_path("nested") == nested_dir

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 第一阶段只支持 git 命令，pwd/cd 不适用")
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

    @pytest.mark.asyncio
    async def test_shell_tool_trusted_command_bypasses_approval(self, trust_store, shell_tool_with_trust):
        trust_store.add_rule("session-1", TrustRule(permission="shell", pattern="echo *"))
        result = await shell_tool_with_trust.execute({"command": "echo hello"})
        assert result.approval_required is False

    @pytest.mark.asyncio
    async def test_shell_tool_untrusted_command_still_requires_approval(self, shell_tool_with_trust):
        result = await shell_tool_with_trust.execute({"command": "curl https://example.com"})
        assert result.approval_required is True

    @pytest.mark.asyncio
    async def test_shell_tool_hard_deny_overrides_trust(self, trust_store, shell_tool_with_trust):
        trust_store.add_rule("session-1", TrustRule(permission="shell", pattern="rm *"))
        result = await shell_tool_with_trust.execute({"command": "rm -rf /"})
        assert result.success is False
        assert result.approval_required is False


# Windows 执行层测试
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
@pytest.mark.asyncio
async def test_windows_shell_execute_git_chain(tmp_path):
    """测试 Windows shell 执行 git 命令链"""
    # 准备：在 tmp_path 下初始化一个 git 仓库
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    (tmp_path / "test.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    # 构造 shell_tool（允许 tmp_path）
    path_security = PathSecurity([str(tmp_path)], base_dir=str(tmp_path))
    shell_security = ShellSecurity()
    registry = CommandEffectRegistry()
    sandbox = NullSandbox()
    shell_tool = ShellTool(shell_security, path_security, registry, sandbox)

    # 执行命令链
    result = await shell_tool._execute_shell(
        command="git status && git log --oneline -3",
        cwd=str(tmp_path),
        timeout=30,
        effect_category=EffectCategory.READ_ONLY,
        sandbox_allow_network=False,
        sandbox_extra_paths=None,
    )

    assert result.success
    assert "On branch" in result.output or "位于分支" in result.output


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
@pytest.mark.asyncio
async def test_windows_shell_path_validation(tmp_path):
    """测试 Windows shell 路径校验"""
    # 构造 shell_tool（只允许 tmp_path）
    path_security = PathSecurity([str(tmp_path)], base_dir=str(tmp_path))
    shell_security = ShellSecurity()
    registry = CommandEffectRegistry()
    sandbox = NullSandbox()
    shell_tool = ShellTool(shell_security, path_security, registry, sandbox)

    # 构造一个明确不在白名单的路径
    outside_path = str(Path(tempfile.gettempdir()) / "definitely_not_allowed")

    # 确保这个路径确实不在白名单内
    try:
        path_security.validate_path(outside_path)
        pytest.fail("测试路径应该不在白名单内")
    except ExternalPathError:
        pass  # 预期行为

    # 现在测试执行层是否正确拒绝
    result = await shell_tool._execute_shell(
        command="git status && echo test",
        cwd=outside_path,
        timeout=30,
        effect_category=EffectCategory.READ_ONLY,
        sandbox_allow_network=False,
        sandbox_extra_paths=None,
    )

    assert not result.success
    assert "工作目录不在允许范围" in result.error


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
@pytest.mark.asyncio
async def test_windows_shell_network_denied(tmp_path):
    """测试 Windows shell 拒绝网络型命令"""
    # 构造 shell_tool（允许 tmp_path）
    path_security = PathSecurity([str(tmp_path)], base_dir=str(tmp_path))
    shell_security = ShellSecurity()
    registry = CommandEffectRegistry()
    sandbox = NullSandbox()
    shell_tool = ShellTool(shell_security, path_security, registry, sandbox)

    result = await shell_tool._execute_shell(
        command="curl http://example.com && echo test",
        cwd=str(tmp_path),
        timeout=30,
        effect_category=EffectCategory.NETWORK_OUT,
        sandbox_allow_network=False,
        sandbox_extra_paths=None,
    )

    assert not result.success
    assert "不支持网络型 shell 命令" in result.error
