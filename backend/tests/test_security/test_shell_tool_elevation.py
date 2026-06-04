import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.security.command_effect_registry import CommandEffectRegistry
from app.security.command_policy import CommandAction, CommandDecision
from app.security.sandbox.error_detector import SandboxErrorInfo, SandboxErrorType
from app.security.effect_category import EffectCategory
from app.tools.base import ToolResult


@pytest.fixture
def shell_tool():
    from app.tools.shell_tool import ShellTool
    from app.security.shell_security import ShellSecurity
    from app.security.path_security import PathSecurity
    from app.security.command_effect_registry import CommandEffectRegistry
    from app.security.sandbox.factory import NullSandbox
    from app.security.session_trust_store import SessionTrustStore

    security = MagicMock(spec=ShellSecurity)
    security.platform_label = "darwin"
    security._is_windows.return_value = False
    security._command_name = lambda x: x.replace("\\", "/").split("/")[-1].lower()
    security.validate_command = MagicMock()
    path_security = MagicMock(spec=PathSecurity)
    path_security.base_dir = "/project"
    path_security.allowed_base_paths = ["/project"]
    path_security.validate_path = MagicMock(return_value="/project")
    registry = CommandEffectRegistry()
    trust_store = SessionTrustStore()

    tool = ShellTool(
        security=security,
        path_security=path_security,
        registry=registry,
        sandbox=NullSandbox(),
        session_id="test-session",
        trust_store=trust_store,
    )
    return tool


class TestCreateApprovalResultElevation:
    def test_network_elevation_approval(self, shell_tool):
        from app.security.command_policy import CommandDecision
        from app.security.effect_category import CommandAction

        decision = CommandDecision(
            action=CommandAction.ALLOW,
            execution_mode="argv",
            command="pip install requests",
            argv=["pip", "install", "requests"],
            effect_category=EffectCategory.WRITE_PROJECT,
        )
        elevation = SandboxErrorInfo(
            error_type=SandboxErrorType.NETWORK_DENIED,
            confidence="high",
        )
        result = shell_tool._create_approval_result(decision, elevation=elevation)
        assert result.approval_required is True
        assert result.approval is not None
        assert result.approval.payload["approval_kind"] == "sandbox_network_elevation"
        assert result.approval.payload["elevation_request"]["type"] == "network"

    def test_path_elevation_approval(self, shell_tool):
        from app.security.command_policy import CommandDecision
        from app.security.effect_category import CommandAction

        decision = CommandDecision(
            action=CommandAction.ALLOW,
            execution_mode="shell",
            command="cat /etc/hosts",
            effect_category=EffectCategory.READ_ONLY,
        )
        elevation = SandboxErrorInfo(
            error_type=SandboxErrorType.PATH_DENIED,
            denied_paths=["/etc"],
            confidence="high",
        )
        result = shell_tool._create_approval_result(decision, elevation=elevation)
        assert result.approval_required is True
        assert result.approval is not None
        assert result.approval.payload["approval_kind"] == "sandbox_path_elevation"
        assert result.approval.payload["elevation_request"]["type"] == "path"
        assert result.approval.payload["elevation_request"]["denied_paths"] == ["/etc"]

    def test_no_elevation_shell_command_approval(self, shell_tool):
        from app.security.command_policy import CommandDecision
        from app.security.effect_category import CommandAction

        decision = CommandDecision(
            action=CommandAction.REQUIRE_APPROVAL,
            execution_mode="argv",
            command="curl https://example.com",
            argv=["curl", "https://example.com"],
            approval_kind="shell_command",
            effect_category=EffectCategory.NETWORK_OUT,
        )
        result = shell_tool._create_approval_result(decision)
        assert result.approval is not None
        assert result.approval.payload["approval_kind"] == "shell_command"
        assert result.approval.payload.get("elevation_request") is None


class TestExecuteApprovedDecisionElevation:
    @pytest.mark.asyncio
    async def test_network_elevation_sets_flag(self, shell_tool):
        decision_data = {
            "action": "allow",
            "execution_mode": "argv",
            "command": "pip install requests",
            "argv": ["pip", "install", "requests"],
            "effect_category": "write_project",
            "approval_kind": "shell_command",
            "timeout": 600,
            "reasons": [],
            "risks": [],
            "elevation_request": {"type": "network", "denied_paths": []},
        }

        with patch.object(shell_tool, '_execute_decision', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(success=True, output="ok")
            await shell_tool._execute_approved_decision(decision_data, 600)
            call_args = mock_exec.call_args[0][0]
            assert getattr(call_args, '_sandbox_allow_network', False) is True

    @pytest.mark.asyncio
    async def test_path_elevation_sets_flag(self, shell_tool):
        decision_data = {
            "action": "allow",
            "execution_mode": "argv",
            "command": "cat /etc/hosts",
            "argv": ["cat", "/etc/hosts"],
            "effect_category": "read_only",
            "approval_kind": "shell_command",
            "timeout": 600,
            "reasons": [],
            "risks": [],
            "elevation_request": {"type": "path", "denied_paths": ["/etc"]},
        }

        with patch.object(shell_tool, '_execute_decision', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ToolResult(success=True, output="ok")
            await shell_tool._execute_approved_decision(decision_data, 600)
            call_args = mock_exec.call_args[0][0]
            assert getattr(call_args, '_sandbox_extra_paths', []) == ["/etc"]


class TestSessionTrustElevation:
    def test_network_trust_auto_elevates(self, shell_tool):
        from app.security.session_trust_store import TrustRule
        shell_tool.trust_store.add_rule(
            "test-session",
            TrustRule(permission="sandbox_network", pattern="*"),
        )
        assert shell_tool.trust_store.matches("test-session", "sandbox_network", "*")

    def test_path_trust_matches_pattern(self, shell_tool):
        from app.security.session_trust_store import TrustRule
        shell_tool.trust_store.add_rule(
            "test-session",
            TrustRule(permission="sandbox_path", pattern="/etc/*"),
        )
        assert shell_tool.trust_store.matches("test-session", "sandbox_path", "/etc/hosts")
        assert not shell_tool.trust_store.matches("test-session", "sandbox_path", "/var/log")


class TestRequiresNetworkParam:
    @pytest.mark.asyncio
    async def test_requires_network_creates_proactive_approval(self, shell_tool):
        from app.security.sandbox.base import SandboxProvider

        class AvailableSandbox(SandboxProvider):
            def is_available(self):
                return True
            def wrap_command(self, argv, **kw):
                return argv
            def wrap_shell_command(self, command, **kw):
                return command

        shell_tool.sandbox = AvailableSandbox()
        result = await shell_tool.execute({
            "command": "pip install requests",
            "requires_network": True,
        })
        assert result.approval_required is True
        assert result.approval.payload["approval_kind"] == "sandbox_network_elevation"
        assert result.approval.summary.startswith("命令需要网络访问")

    @pytest.mark.asyncio
    async def test_often_needs_network_auto_triggers_approval(self, shell_tool):
        decision = CommandDecision(
            action=CommandAction.ALLOW,
            execution_mode="argv",
            command="pip install requests",
            argv=["pip", "install", "requests"],
            effect_category=EffectCategory.WRITE_PROJECT,
        )
        from app.security.sandbox.base import SandboxProvider

        class AvailableSandbox(SandboxProvider):
            def is_available(self):
                return True
            def wrap_command(self, argv, **kw):
                return argv
            def wrap_shell_command(self, command, **kw):
                return command

        shell_tool.sandbox = AvailableSandbox()
        assert shell_tool._needs_network_approval(decision, requires_network=False) is True

    @pytest.mark.asyncio
    async def test_non_network_command_no_approval(self, shell_tool):
        decision = CommandDecision(
            action=CommandAction.ALLOW,
            execution_mode="argv",
            command="echo hello",
            argv=["echo", "hello"],
            effect_category=EffectCategory.READ_ONLY,
        )
        from app.security.sandbox.base import SandboxProvider

        class AvailableSandbox(SandboxProvider):
            def is_available(self):
                return True
            def wrap_command(self, argv, **kw):
                return argv
            def wrap_shell_command(self, command, **kw):
                return command

        shell_tool.sandbox = AvailableSandbox()
        assert shell_tool._needs_network_approval(decision, requires_network=False) is False

    @pytest.mark.asyncio
    async def test_network_out_category_no_duplicate_approval(self, shell_tool):
        decision = CommandDecision(
            action=CommandAction.REQUIRE_APPROVAL,
            execution_mode="argv",
            command="curl https://example.com",
            argv=["curl", "https://example.com"],
            approval_kind="shell_command",
            effect_category=EffectCategory.NETWORK_OUT,
        )
        from app.security.sandbox.base import SandboxProvider

        class AvailableSandbox(SandboxProvider):
            def is_available(self):
                return True
            def wrap_command(self, argv, **kw):
                return argv
            def wrap_shell_command(self, command, **kw):
                return command

        shell_tool.sandbox = AvailableSandbox()
        assert shell_tool._needs_network_approval(decision, requires_network=False) is False
