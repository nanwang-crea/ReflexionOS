# backend/tests/test_security/test_sandbox.py
import shlex
from unittest.mock import patch

import pytest

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.factory import NullSandbox, create_sandbox
from app.security.sandbox.landlock import LandlockSandbox
from app.security.sandbox.seatbelt import SeatbeltSandbox
from app.security.sandbox.seatbelt_profile import build_seatbelt_profile


# ---------------------------------------------------------------------------
# SandboxProvider ABC
# ---------------------------------------------------------------------------

class TestSandboxProviderABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            SandboxProvider()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# NullSandbox
# ---------------------------------------------------------------------------

class TestNullSandbox:
    def setup_method(self):
        self.sandbox = NullSandbox()

    def test_not_available(self):
        assert self.sandbox.is_available() is False

    def test_wrap_command_passthrough(self):
        argv = ["python", "-c", "print('hi')"]
        result = self.sandbox.wrap_command(argv, cwd="/tmp")
        assert result == argv

    def test_wrap_shell_command_passthrough(self):
        cmd = "echo hello"
        result = self.sandbox.wrap_shell_command(cmd, cwd="/tmp")
        assert result == cmd

    def test_wrap_command_preserves_argv_copy(self):
        argv = ["ls", "-la"]
        result = self.sandbox.wrap_command(argv, cwd="/tmp")
        assert result == argv
        assert result is not argv  # should be a new list


# ---------------------------------------------------------------------------
# Sandbox factory
# ---------------------------------------------------------------------------

class TestSandboxFactory:
    def test_returns_sandbox_provider_instance(self):
        sandbox = create_sandbox()
        assert isinstance(sandbox, SandboxProvider)

    def test_fallback_to_null_sandbox(self):
        """When no real sandbox is available, factory returns NullSandbox."""
        with patch.object(SeatbeltSandbox, "is_available", return_value=False), \
             patch.object(LandlockSandbox, "is_available", return_value=False):
            sandbox = create_sandbox()
            assert isinstance(sandbox, NullSandbox)

    def test_prefers_seatbelt_when_available(self):
        with patch.object(SeatbeltSandbox, "is_available", return_value=True):
            sandbox = create_sandbox()
            assert isinstance(sandbox, SeatbeltSandbox)

    def test_uses_landlock_when_seatbelt_unavailable(self):
        with patch.object(SeatbeltSandbox, "is_available", return_value=False), \
             patch.object(LandlockSandbox, "is_available", return_value=True):
            sandbox = create_sandbox()
            assert isinstance(sandbox, LandlockSandbox)


# ---------------------------------------------------------------------------
# Seatbelt profile builder
# ---------------------------------------------------------------------------

class TestSeatbeltProfile:
    def _profile(self, **kwargs):
        return build_seatbelt_profile(**kwargs)

    def test_has_deny_default(self):
        p = self._profile()
        assert "(deny default)" in p

    def test_has_version_header(self):
        p = self._profile()
        assert "(version 1)" in p

    def test_allows_project_write(self):
        p = self._profile(allowed_paths=["/home/user/project"])
        assert '(allow file-read* file-write* (subpath "/home/user/project"))' in p

    def test_allows_var_folders(self):
        p = self._profile()
        assert '(allow file-read* file-write* (subpath "/var/folders"))' in p

    def test_allows_private_tmp(self):
        p = self._profile()
        assert '(allow file-read* file-write* (subpath "/private/tmp"))' in p

    def test_network_deny_by_default(self):
        p = self._profile(allow_network=False)
        assert "(deny network*)" in p

    def test_network_allow_when_requested(self):
        p = self._profile(allow_network=True)
        assert "(allow network*)" in p

    def test_process_fork_allowed(self):
        p = self._profile()
        assert "(allow process-fork)" in p

    def test_etc_read_allowed(self):
        p = self._profile()
        assert '(allow file-read* (subpath "/etc"))' in p

    def test_read_only_paths(self):
        p = self._profile(read_only_paths=["/opt/data"])
        assert '(allow file-read* (subpath "/opt/data"))' in p
        # should NOT have write for read-only paths
        assert 'file-write* (subpath "/opt/data")' not in p

    def test_system_binary_reads(self):
        p = self._profile()
        for prefix in ("/usr", "/bin", "/sbin", "/lib", "/System", "/dev"):
            assert f'(allow file-read* (subpath "{prefix}"))' in p

    def test_process_exec_allowed(self):
        p = self._profile()
        for prefix in ("/usr", "/bin", "/sbin"):
            assert f'(allow process-exec (subpath "{prefix}"))' in p

    def test_signal_and_sysctl(self):
        p = self._profile()
        assert "(allow signal)" in p
        assert "(allow sysctl-read)" in p


# ---------------------------------------------------------------------------
# SeatbeltSandbox
# ---------------------------------------------------------------------------

class TestSeatbeltSandbox:
    def _make_sandbox(self):
        return SeatbeltSandbox()

    def test_wrap_command_prepends_sandbox_exec(self):
        sandbox = self._make_sandbox()
        result = sandbox.wrap_command(
            ["python", "-c", "print('hi')"],
            cwd="/tmp",
            allowed_paths=["/project"],
        )
        assert result[0] == "/usr/bin/sandbox-exec"
        assert result[1] == "-p"
        # result[2] is the profile string
        assert result[3] == "--"
        assert result[4:] == ["python", "-c", "print('hi')"]

    def test_wrap_shell_command_includes_sandbox_exec(self):
        sandbox = self._make_sandbox()
        result = sandbox.wrap_shell_command(
            "echo hello",
            cwd="/tmp",
            allowed_paths=["/project"],
        )
        assert result.startswith("/usr/bin/sandbox-exec -p ")
        assert result.endswith(" -- echo hello")

    def test_wrap_shell_command_profile_is_quoted(self):
        sandbox = self._make_sandbox()
        result = sandbox.wrap_shell_command(
            "ls",
            cwd="/tmp",
        )
        # The profile string should be shell-quoted
        parts = result.split(" ", 3)
        assert parts[0] == "/usr/bin/sandbox-exec"
        assert parts[1] == "-p"

    def test_is_available_on_macos_with_sandbox_exec(self):
        sandbox = self._make_sandbox()
        with patch("app.security.sandbox.seatbelt.sys") as mock_sys, \
             patch("app.security.sandbox.seatbelt.os.path.exists") as mock_exists:
            mock_sys.platform = "darwin"
            mock_exists.return_value = True
            assert sandbox.is_available() is True

    def test_is_not_available_on_linux(self):
        sandbox = self._make_sandbox()
        with patch("app.security.sandbox.seatbelt.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert sandbox.is_available() is False


# ---------------------------------------------------------------------------
# LandlockSandbox
# ---------------------------------------------------------------------------

class TestLandlockSandbox:
    def _make_sandbox(self):
        return LandlockSandbox()

    def test_is_not_available_on_non_linux(self):
        sandbox = self._make_sandbox()
        with patch("app.security.sandbox.landlock.sys") as mock_sys:
            mock_sys.platform = "darwin"
            assert sandbox.is_available() is False

    def test_wrap_command_prepends_bwrap(self):
        sandbox = self._make_sandbox()
        with patch.object(sandbox, "_check_bwrap_support", return_value=True), \
             patch("app.security.sandbox.landlock.os.path.isdir", return_value=True):
            result = sandbox.wrap_command(
                ["python", "-c", "print('hi')"],
                cwd="/project",
                allowed_paths=["/project"],
            )
            assert result[0] == "bwrap"
            # "--" is the separator before the user command
            sep_idx = len(result) - len(["python", "-c", "print('hi')"]) - 1
            assert result[sep_idx] == "--"
            assert result[sep_idx + 1:] == ["python", "-c", "print('hi')"]

    def test_bwrap_args_include_unshare_all(self):
        sandbox = self._make_sandbox()
        args = sandbox._build_bwrap_args(cwd="/project")
        assert "--unshare-all" in args

    def test_bwrap_args_include_tmpfs(self):
        sandbox = self._make_sandbox()
        args = sandbox._build_bwrap_args(cwd="/project")
        assert "--tmpfs" in args
        tmpfs_idx = args.index("--tmpfs")
        assert args[tmpfs_idx + 1] == "/tmp"

    def test_bwrap_args_include_proc_and_dev(self):
        sandbox = self._make_sandbox()
        args = sandbox._build_bwrap_args(cwd="/project")
        assert "--proc" in args
        assert "--dev" in args

    def test_bwrap_args_unshare_net_when_no_network(self):
        sandbox = self._make_sandbox()
        args = sandbox._build_bwrap_args(cwd="/project", allow_network=False)
        assert "--unshare-net" in args

    def test_bwrap_args_no_unshare_net_when_network_allowed(self):
        sandbox = self._make_sandbox()
        args = sandbox._build_bwrap_args(cwd="/project", allow_network=True)
        assert "--unshare-net" not in args

    def test_bwrap_args_bind_allowed_paths(self):
        sandbox = self._make_sandbox()
        args = sandbox._build_bwrap_args(
            cwd="/project",
            allowed_paths=["/project/src"],
        )
        bind_idx = args.index("--bind")
        assert args[bind_idx + 1] == "/project/src"
        assert args[bind_idx + 2] == "/project/src"

    def test_bwrap_args_ro_bind_read_only_paths(self):
        sandbox = self._make_sandbox()
        with patch("app.security.sandbox.landlock.os.path.isdir", return_value=True):
            args = sandbox._build_bwrap_args(
                cwd="/project",
                read_only_paths=["/opt/data"],
            )
        # Find the --ro-bind entry for /opt/data specifically
        # Pattern: --ro-bind <src> <dst> where <src> == "/opt/data"
        found = False
        for i in range(len(args) - 2):
            if args[i] == "--ro-bind" and args[i + 1] == "/opt/data":
                assert args[i + 2] == "/opt/data"
                found = True
                break
        assert found, "/opt/data not found as --ro-bind target"

    def test_bwrap_args_include_chdir(self):
        sandbox = self._make_sandbox()
        args = sandbox._build_bwrap_args(cwd="/my/work")
        assert "--chdir" in args
        chdir_idx = args.index("--chdir")
        assert args[chdir_idx + 1] == "/my/work"

    def test_wrap_shell_command(self):
        sandbox = self._make_sandbox()
        with patch.object(sandbox, "_check_bwrap_support", return_value=True), \
             patch("app.security.sandbox.landlock.os.path.isdir", return_value=True):
            result = sandbox.wrap_shell_command(
                "echo hello",
                cwd="/project",
                allowed_paths=["/project"],
            )
            assert result.startswith("bwrap ")
            assert result.endswith(" -- echo hello")

    def test_check_bwrap_support_returns_false_on_error(self):
        sandbox = self._make_sandbox()
        with patch("app.security.sandbox.landlock.subprocess.run", side_effect=OSError):
            assert sandbox._check_bwrap_support() is False
