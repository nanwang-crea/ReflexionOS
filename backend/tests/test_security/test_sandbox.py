# backend/tests/test_security/test_sandbox.py
import shlex
from unittest.mock import patch

import pytest

from app.security.sandbox.base import SandboxProvider
from app.security.sandbox.factory import NullSandbox, create_sandbox
from app.security.sandbox.landlock import LandlockSandbox
from app.security.sandbox.landlock_profile import LandlockProfileBuilder
from app.security.sandbox.profile_builder import ProfileBuilder
from app.security.sandbox.seatbelt import SeatbeltSandbox
from app.security.sandbox.seatbelt_profile import SeatbeltProfileBuilder
from app.security.sandbox.sandbox_policy import SandboxLevel, SandboxPolicy


# ---------------------------------------------------------------------------
# SandboxLevel enum
# ---------------------------------------------------------------------------

class TestSandboxLevel:
    def test_str_enum_dev(self):
        assert SandboxLevel("dev") == SandboxLevel.DEV

    def test_str_enum_strict(self):
        assert SandboxLevel("strict") == SandboxLevel.STRICT

    def test_str_enum_permissive(self):
        assert SandboxLevel("permissive") == SandboxLevel.PERMISSIVE

    def test_string_value(self):
        assert SandboxLevel.DEV.value == "dev"


# ---------------------------------------------------------------------------
# SandboxPolicy
# ---------------------------------------------------------------------------

class TestSandboxPolicy:
    def test_strict_disables_everything(self):
        p = SandboxPolicy.from_level(SandboxLevel.STRICT)
        assert not p.allow_process_exec_all
        assert not p.allow_ipc
        assert not p.allow_mach
        assert not p.allow_user_read
        assert not p.allow_user_write
        assert not p.allow_user_exec
        assert not p.allow_network

    def test_dev_enables_user_and_ipc(self):
        p = SandboxPolicy.from_level(SandboxLevel.DEV)
        assert p.allow_process_exec_all
        assert p.allow_ipc
        assert p.allow_mach
        assert p.allow_user_read
        assert p.allow_user_write
        assert p.allow_user_exec

    def test_permissive_same_as_dev(self):
        """PERMISSIVE currently has the same base flags as DEV."""
        p_dev = SandboxPolicy.from_level(SandboxLevel.DEV)
        p_perm = SandboxPolicy.from_level(SandboxLevel.PERMISSIVE)
        # All boolean flags match (paths/network differ by caller overrides)
        assert p_perm.allow_process_exec_all == p_dev.allow_process_exec_all
        assert p_perm.allow_ipc == p_dev.allow_ipc
        assert p_perm.allow_mach == p_dev.allow_mach
        assert p_perm.allow_user_read == p_dev.allow_user_read
        assert p_perm.allow_user_write == p_dev.allow_user_write
        assert p_perm.allow_user_exec == p_dev.allow_user_exec

    def test_network_override(self):
        p = SandboxPolicy.from_level(SandboxLevel.DEV, allow_network=True)
        assert p.allow_network is True

    def test_network_default_off(self):
        p = SandboxPolicy.from_level(SandboxLevel.DEV)
        assert p.allow_network is False

    def test_allowed_paths_override(self):
        p = SandboxPolicy.from_level(SandboxLevel.DEV, allowed_paths=["/project"])
        assert p.allowed_paths == ["/project"]

    def test_read_only_paths_override(self):
        p = SandboxPolicy.from_level(SandboxLevel.DEV, read_only_paths=["/opt/data"])
        assert p.read_only_paths == ["/opt/data"]

    def test_default_empty_paths(self):
        p = SandboxPolicy.from_level(SandboxLevel.DEV)
        assert p.allowed_paths == []
        assert p.read_only_paths == []


# ---------------------------------------------------------------------------
# ProfileBuilder ABC
# ---------------------------------------------------------------------------

class TestProfileBuilderABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            ProfileBuilder(SandboxPolicy())  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# SeatbeltProfileBuilder
# ---------------------------------------------------------------------------

class TestSeatbeltProfileBuilder:
    def _profile(self, level=SandboxLevel.DEV, **kwargs):
        policy = SandboxPolicy.from_level(level, **kwargs)
        return SeatbeltProfileBuilder(policy).build()

    # -- header --

    def test_has_deny_default(self):
        p = self._profile()
        assert "(deny default)" in p

    def test_has_version_header(self):
        p = self._profile()
        assert "(version 1)" in p

    # -- system paths --

    def test_system_binary_reads(self):
        p = self._profile()
        for prefix in ("/usr", "/bin", "/sbin", "/lib", "/System", "/dev"):
            assert f'(allow file-read* (subpath "{prefix}"))' in p

    def test_etc_read_allowed(self):
        p = self._profile()
        assert '(allow file-read* (subpath "/etc"))' in p

    def test_file_map_executable(self):
        p = self._profile()
        assert "(allow file-map-executable)" in p

    # -- temp dirs --

    def test_allows_var_folders(self):
        p = self._profile()
        assert '(allow file-read* file-write* (subpath "/var/folders"))' in p

    def test_allows_private_tmp(self):
        p = self._profile()
        assert '(allow file-read* file-write* (subpath "/private/tmp"))' in p

    def test_allows_tmp(self):
        p = self._profile()
        assert '(allow file-read* file-write* (subpath "/tmp"))' in p

    # -- user paths --

    def test_dev_allows_user_read(self):
        p = self._profile(level=SandboxLevel.DEV)
        assert '(allow file-read* (subpath "/Users"))' in p

    def test_dev_allows_user_write(self):
        p = self._profile(level=SandboxLevel.DEV)
        assert '(allow file-write* (subpath "/Users"))' in p

    def test_dev_allows_user_exec(self):
        p = self._profile(level=SandboxLevel.DEV)
        assert '(allow process-exec (subpath "/Users"))' in p

    def test_strict_denies_user_paths(self):
        p = self._profile(level=SandboxLevel.STRICT)
        assert '(allow file-read* (subpath "/Users"))' not in p
        assert '(allow file-write* (subpath "/Users"))' not in p
        assert '(allow process-exec (subpath "/Users"))' not in p

    # -- project paths --

    def test_allows_project_write(self):
        p = self._profile(allowed_paths=["/home/user/project"])
        assert '(allow file-read* file-write* (subpath "/home/user/project"))' in p

    def test_read_only_paths(self):
        p = self._profile(read_only_paths=["/opt/data"])
        assert '(allow file-read* (subpath "/opt/data"))' in p
        assert 'file-write* (subpath "/opt/data")' not in p

    # -- process --

    def test_dev_allows_unrestricted_process_exec(self):
        p = self._profile(level=SandboxLevel.DEV)
        assert "(allow process-exec)" in p

    def test_strict_restricts_process_exec_to_system(self):
        p = self._profile(level=SandboxLevel.STRICT)
        assert "(allow process-exec)" not in p
        for prefix in ("/usr", "/bin", "/sbin"):
            assert f'(allow process-exec (subpath "{prefix}"))' in p

    def test_process_fork_allowed(self):
        p = self._profile()
        assert "(allow process-fork)" in p

    def test_process_info_allowed(self):
        p = self._profile()
        assert "(allow process-info*)" in p

    # -- IPC --

    def test_dev_allows_ipc(self):
        p = self._profile(level=SandboxLevel.DEV)
        assert "(allow ipc*)" in p

    def test_dev_allows_mach(self):
        p = self._profile(level=SandboxLevel.DEV)
        assert "(allow mach*)" in p

    def test_strict_denies_ipc(self):
        p = self._profile(level=SandboxLevel.STRICT)
        assert "(allow ipc*)" not in p
        assert "(allow mach*)" not in p

    # -- network --

    def test_network_deny_by_default(self):
        p = self._profile(allow_network=False)
        assert "(deny network*)" in p

    def test_network_allow_when_requested(self):
        p = self._profile(allow_network=True)
        assert "(allow network*)" in p

    # -- misc --

    def test_signal_and_sysctl(self):
        p = self._profile()
        assert "(allow signal)" in p
        assert "(allow sysctl-read)" in p


# ---------------------------------------------------------------------------
# LandlockProfileBuilder
# ---------------------------------------------------------------------------

class TestLandlockProfileBuilder:
    def _args(self, level=SandboxLevel.DEV, cwd="/project", **kwargs):
        policy = SandboxPolicy.from_level(level, **kwargs)
        return LandlockProfileBuilder(policy, cwd=cwd).build()

    def test_unshare_all(self):
        args = self._args()
        assert "--unshare-all" in args

    def test_die_with_parent(self):
        args = self._args()
        assert "--die-with-parent" in args

    def test_tmpfs(self):
        args = self._args()
        assert "--tmpfs" in args
        tmpfs_idx = args.index("--tmpfs")
        assert args[tmpfs_idx + 1] == "/tmp"

    def test_proc_and_dev(self):
        args = self._args()
        assert "--proc" in args
        assert "--dev" in args

    def test_unshare_net_when_no_network(self):
        args = self._args(allow_network=False)
        assert "--unshare-net" in args

    def test_no_unshare_net_when_network_allowed(self):
        args = self._args(allow_network=True)
        assert "--unshare-net" not in args

    def test_bind_allowed_paths(self):
        args = self._args(allowed_paths=["/project/src"])
        # Find the --bind entry for /project/src specifically
        # (there may be other --bind entries like /home from policy)
        found = False
        for i in range(len(args) - 2):
            if args[i] == "--bind" and args[i + 1] == "/project/src":
                assert args[i + 2] == "/project/src"
                found = True
                break
        assert found, "/project/src not found as --bind target"

    def test_ro_bind_read_only_paths(self):
        with patch("app.security.sandbox.landlock_profile.os.path.isdir", return_value=True):
            args = self._args(read_only_paths=["/opt/data"])
        found = False
        for i in range(len(args) - 2):
            if args[i] == "--ro-bind" and args[i + 1] == "/opt/data":
                assert args[i + 2] == "/opt/data"
                found = True
                break
        assert found, "/opt/data not found as --ro-bind target"

    def test_chdir(self):
        args = self._args(cwd="/my/work")
        assert "--chdir" in args
        chdir_idx = args.index("--chdir")
        assert args[chdir_idx + 1] == "/my/work"

    def test_dev_home_writable(self):
        with patch("app.security.sandbox.landlock_profile.os.path.isdir", return_value=True):
            args = self._args(level=SandboxLevel.DEV)
        # DEV allows user read+write, so /home should be --bind (writable)
        found = False
        for i in range(len(args) - 2):
            if args[i] == "--bind" and args[i + 1] == "/home":
                found = True
                break
        assert found, "/home should be writable (--bind) in DEV mode"

    def test_strict_home_not_writable(self):
        with patch("app.security.sandbox.landlock_profile.os.path.isdir", return_value=True):
            args = self._args(level=SandboxLevel.STRICT)
        # STRICT: allow_user_read=False, allow_user_write=False → /home absent
        for i in range(len(args) - 2):
            if args[i] in ("--bind", "--ro-bind") and args[i + 1] == "/home":
                pytest.fail("/home should NOT be mounted in STRICT mode")


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

    def test_level_propagated_to_seatbelt(self):
        with patch.object(SeatbeltSandbox, "is_available", return_value=True):
            sandbox = create_sandbox(level=SandboxLevel.STRICT)
            assert isinstance(sandbox, SeatbeltSandbox)
            assert sandbox.level == SandboxLevel.STRICT

    def test_level_propagated_to_landlock(self):
        with patch.object(SeatbeltSandbox, "is_available", return_value=False), \
             patch.object(LandlockSandbox, "is_available", return_value=True):
            sandbox = create_sandbox(level=SandboxLevel.STRICT)
            assert isinstance(sandbox, LandlockSandbox)
            assert sandbox.level == SandboxLevel.STRICT

    def test_default_level_is_dev(self):
        with patch.object(SeatbeltSandbox, "is_available", return_value=True):
            sandbox = create_sandbox()
            assert sandbox.level == SandboxLevel.DEV


# ---------------------------------------------------------------------------
# SeatbeltSandbox
# ---------------------------------------------------------------------------

class TestSeatbeltSandbox:
    def _make_sandbox(self, level=SandboxLevel.DEV):
        return SeatbeltSandbox(level=level)

    def test_default_level_is_dev(self):
        sandbox = SeatbeltSandbox()
        assert sandbox.level == SandboxLevel.DEV

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

    def test_wrap_command_strict_profile(self):
        sandbox = self._make_sandbox(level=SandboxLevel.STRICT)
        result = sandbox.wrap_command(
            ["python", "-c", "print('hi')"],
            cwd="/tmp",
            allowed_paths=["/project"],
        )
        profile = result[2]
        assert "(allow ipc*)" not in profile
        assert "(allow mach*)" not in profile

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
    def _make_sandbox(self, level=SandboxLevel.DEV):
        return LandlockSandbox(level=level)

    def test_default_level_is_dev(self):
        sandbox = LandlockSandbox()
        assert sandbox.level == SandboxLevel.DEV

    def test_is_not_available_on_non_linux(self):
        sandbox = self._make_sandbox()
        with patch("app.security.sandbox.landlock.sys") as mock_sys:
            mock_sys.platform = "darwin"
            assert sandbox.is_available() is False

    def test_wrap_command_prepends_bwrap(self):
        sandbox = self._make_sandbox()
        with patch.object(sandbox, "_check_bwrap_support", return_value=True), \
             patch("app.security.sandbox.landlock_profile.os.path.isdir", return_value=True):
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

    def test_wrap_command_strict_level(self):
        sandbox = self._make_sandbox(level=SandboxLevel.STRICT)
        with patch.object(sandbox, "_check_bwrap_support", return_value=True), \
             patch("app.security.sandbox.landlock_profile.os.path.isdir", return_value=True):
            result = sandbox.wrap_command(
                ["ls"],
                cwd="/project",
                allowed_paths=["/project"],
            )
            assert result[0] == "bwrap"

    def test_wrap_shell_command(self):
        sandbox = self._make_sandbox()
        with patch.object(sandbox, "_check_bwrap_support", return_value=True), \
             patch("app.security.sandbox.landlock_profile.os.path.isdir", return_value=True):
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
