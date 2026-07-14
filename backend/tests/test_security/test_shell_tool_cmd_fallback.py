# Windows cmd 内部命令降级执行单测。
#
# 验证：
# - is_cmd_internal_command 清单覆盖正确（命中 cmd 内部、排除有 exe 的）
# - shell_tool._execute_decision 在 Windows 上 argv[0] 为 cmd 内部命令时
#   走 run_shell_command，真 .exe 走 run_command

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.security.sandbox.windows_cmd import is_cmd_internal_command, CMD_INTERNAL_COMMANDS


# ==================== is_cmd_internal_command 清单覆盖 ====================

class TestIsCmdInternalCommand:
    def test_hits_cmd_internal_commands(self):
        """常见 cmd 内部命令应返回 True"""
        for cmd in ["if", "for", "mkdir", "md", "copy", "xcopy", "move",
                    "ren", "rename", "del", "erase", "type", "dir", "cd",
                    "chdir", "echo", "set", "cls", "ver", "start", "call",
                    "pushd", "popd", "exit", "mklink"]:
            assert is_cmd_internal_command(cmd) is True, f"{cmd} 应在清单中"

    def test_case_insensitive(self):
        """清单应大小写不敏感（cmd 不区分大小写）"""
        assert is_cmd_internal_command("IF") is True
        assert is_cmd_internal_command("Mkdir") is True
        assert is_cmd_internal_command("ECHO") is True

    def test_empty_and_none(self):
        """空值 / None 不应命中"""
        assert is_cmd_internal_command("") is False
        assert is_cmd_internal_command(None) is False

    def test_excludes_commands_with_exe(self):
        """System32 下有独立 .exe 的命令不应命中（这些 argv 能跑）"""
        for cmd in ["findstr", "find", "robocopy", "where",
                    "tasklist", "taskkill", "reg", "sc", "net",
                    "wmic", "ping", "ipconfig"]:
            assert is_cmd_internal_command(cmd) is False, f"{cmd} 有独立 exe，不应命中"

    def test_excludes_unix_and_real_exes(self):
        """Unix 命令 / 有 exe 的 Windows 命令不命中"""
        for cmd in ["git", "python", "python3", "node", "npm", "pnpm",
                    "ls", "cat", "rm", "bash", "sh", "curl"]:
            assert is_cmd_internal_command(cmd) is False


# ==================== shell_tool 降级分发 ====================

class TestShellToolCmdFallback:
    @pytest.fixture
    def shell_tool(self):
        """构造一个最小 shell_tool（真实 command_policy + mock sandbox）"""
        from app.security.path_security import PathSecurity
        from app.tools.shell_tool import ShellTool

        ps = PathSecurity(["/tmp/test-project"], base_dir="/tmp/test-project")
        tool = ShellTool(MagicMock(), ps, sandbox=MagicMock())
        tool.sandbox.is_available.return_value = True
        return tool

    def _make_decision(self, *, command: str, argv: list[str], execution_mode: str = "argv"):
        """构造一个假的 CommandDecision"""
        from app.security.command_policy import CommandDecision, EnvironmentSnapshot
        from app.security.effect_category import EffectCategory
        return CommandDecision(
            action="allow",
            command=command,
            argv=argv,
            cwd="/tmp/test-project",
            timeout=30,
            execution_mode=execution_mode,
            effect_category=EffectCategory.WRITE_PROJECT,
            environment_snapshot=EnvironmentSnapshot(cwd="/tmp/test-project"),
        )

    @pytest.mark.asyncio
    async def test_cmd_internal_command_on_windows_calls_run_shell_command(self, shell_tool):
        """Windows 上 argv[0]=mkdir 应走 _execute_shell（内部走 run_shell_command）"""
        with patch.object(sys, "platform", "win32"):
            shell_tool._execute_shell = AsyncMock(return_value=MagicMock(success=True))
            decision = self._make_decision(
                command='mkdir docs\\plans\\features',
                argv=["mkdir", "docs\\plans\\features"],
            )
            await shell_tool._execute_decision(decision)

        shell_tool._execute_shell.assert_awaited_once()
        call_args = shell_tool._execute_shell.call_args[0]
        assert call_args[0] == 'mkdir docs\\plans\\features', "应复用原始 command 字符串"

    @pytest.mark.asyncio
    async def test_real_exe_on_windows_calls_run_command(self, shell_tool):
        """Windows 上 argv[0]=git 应走 _execute_argv（内部走 run_command）"""
        shell_tool._execute_shell = AsyncMock()
        shell_tool._execute_argv = AsyncMock(return_value=MagicMock(success=True))
        with patch.object(sys, "platform", "win32"):
            decision = self._make_decision(
                command="git status",
                argv=["git", "status"],
            )
            await shell_tool._execute_decision(decision)

        shell_tool._execute_argv.assert_awaited_once()
        shell_tool._execute_shell.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cmd_internal_on_unix_does_not_fallback(self, shell_tool):
        """非 Windows 平台不触发降级（if 在 Unix 下不存在，走 argv 让上层报 127）"""
        shell_tool._execute_shell = AsyncMock()
        shell_tool._execute_argv = AsyncMock(return_value=MagicMock(success=True))
        with patch.object(sys, "platform", "linux"):
            decision = self._make_decision(
                command="if true; then echo x; fi",
                argv=["if", "true;", "then", "echo", "x;", "fi"],
            )
            await shell_tool._execute_decision(decision)

        shell_tool._execute_argv.assert_awaited_once()
        shell_tool._execute_shell.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shell_mode_unchanged(self, shell_tool):
        """原本就是 shell 模式（含元字符）时，仍走 _execute_shell"""
        with patch.object(sys, "platform", "win32"):
            shell_tool._execute_shell = AsyncMock(return_value=MagicMock(success=True))
            decision = self._make_decision(
                command="git status && echo ok",
                argv=["git", "status"],
                execution_mode="shell",
            )
            await shell_tool._execute_decision(decision)

        shell_tool._execute_shell.assert_awaited_once()
