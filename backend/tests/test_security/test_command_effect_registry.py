# backend/tests/test_security/test_command_effect_registry.py
import pytest

from app.security.effect_category import EffectCategory
from app.security.command_effect_registry import (
    CommandEffectEntry,
    CommandEffectRegistry,
)


class TestCommandEffectEntry:
    def test_default_values(self):
        entry = CommandEffectEntry(category=EffectCategory.READ_ONLY)
        assert entry.category == EffectCategory.READ_ONLY
        assert entry.allow_subcommands is False
        assert entry.subcommand_overrides == {}
        assert entry.flag_overrides == {}
        assert entry.platform_overrides == {}

    def test_git_entry(self):
        entry = CommandEffectEntry(
            category=EffectCategory.READ_ONLY,
            allow_subcommands=True,
            subcommand_overrides={
                "add": EffectCategory.WRITE_PROJECT,
                "push": EffectCategory.NETWORK_OUT,
                "reset": EffectCategory.DESTRUCTIVE,
            },
        )
        assert entry.allow_subcommands is True
        assert entry.subcommand_overrides["add"] == EffectCategory.WRITE_PROJECT


class TestRegistryLookup:
    def test_known_command_returns_entry(self):
        registry = CommandEffectRegistry()
        entry = registry.lookup("ls")
        assert entry is not None
        assert entry.category == EffectCategory.READ_ONLY

    def test_unknown_command_returns_none(self):
        registry = CommandEffectRegistry()
        entry = registry.lookup("nonexistent_tool_xyz")
        assert entry is None

    def test_lookup_strips_path_prefix(self):
        registry = CommandEffectRegistry()
        entry = registry.lookup("/usr/bin/ls")
        assert entry is not None
        assert entry.category == EffectCategory.READ_ONLY

    def test_lookup_strips_exe_suffix(self):
        registry = CommandEffectRegistry()
        entry = registry.lookup("python.exe")
        assert entry is not None
        assert entry.category == EffectCategory.WRITE_PROJECT


class TestRegistryDefaultRegistrations:
    """Verify all categories have representative commands registered."""

    @pytest.fixture
    def registry(self):
        return CommandEffectRegistry()

    def test_read_only_commands(self, registry):
        for cmd in ["ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "diff",
                     "sort", "uniq", "which", "pwd", "echo", "env", "uname", "hostname",
                     "whoami", "id", "date", "uptime", "df", "du", "ps", "lsof", "ss"]:
            entry = registry.lookup(cmd)
            assert entry is not None, f"Missing READ_ONLY command: {cmd}"
            assert entry.category == EffectCategory.READ_ONLY, f"{cmd} is {entry.category}, expected READ_ONLY"

    def test_write_project_commands(self, registry):
        for cmd in ["mkdir", "touch", "cp", "mv", "ln", "tar", "unzip", "python",
                     "python3", "node", "make", "cmake", "npm", "pip"]:
            entry = registry.lookup(cmd)
            assert entry is not None, f"Missing WRITE_PROJECT command: {cmd}"
            assert entry.category == EffectCategory.WRITE_PROJECT, f"{cmd} is {entry.category}, expected WRITE_PROJECT"

    def test_write_system_commands(self, registry):
        for cmd in ["apt-get", "apt", "yum", "dnf", "brew", "pacman", "snap", "systemctl"]:
            entry = registry.lookup(cmd)
            assert entry is not None, f"Missing WRITE_SYSTEM command: {cmd}"
            assert entry.category == EffectCategory.WRITE_SYSTEM, f"{cmd} is {entry.category}, expected WRITE_SYSTEM"

    def test_destructive_commands(self, registry):
        for cmd in ["rm", "rmdir", "chmod", "chown", "truncate", "shred"]:
            entry = registry.lookup(cmd)
            assert entry is not None, f"Missing DESTRUCTIVE command: {cmd}"
            assert entry.category == EffectCategory.DESTRUCTIVE, f"{cmd} is {entry.category}, expected DESTRUCTIVE"

    def test_escalate_commands(self, registry):
        for cmd in ["sudo", "su", "eval", "exec", "bash", "sh", "zsh", "fish",
                     "ksh", "csh", "newgrp", "pkexec", "gksudo"]:
            entry = registry.lookup(cmd)
            assert entry is not None, f"Missing ESCALATE command: {cmd}"
            assert entry.category == EffectCategory.ESCALATE, f"{cmd} is {entry.category}, expected ESCALATE"

    def test_network_out_commands(self, registry):
        for cmd in ["curl", "wget", "ssh", "scp", "rsync", "nc", "ncat", "telnet", "ftp"]:
            entry = registry.lookup(cmd)
            assert entry is not None, f"Missing NETWORK_OUT command: {cmd}"
            assert entry.category == EffectCategory.NETWORK_OUT, f"{cmd} is {entry.category}, expected NETWORK_OUT"

    def test_git_subcommand_overrides(self, registry):
        git_entry = registry.lookup("git")
        assert git_entry is not None
        assert git_entry.category == EffectCategory.READ_ONLY
        assert git_entry.allow_subcommands is True
        assert git_entry.subcommand_overrides["add"] == EffectCategory.WRITE_PROJECT
        assert git_entry.subcommand_overrides["push"] == EffectCategory.NETWORK_OUT
        assert git_entry.subcommand_overrides["reset"] == EffectCategory.DESTRUCTIVE
        assert git_entry.subcommand_overrides["commit"] == EffectCategory.WRITE_PROJECT
        assert git_entry.subcommand_overrides["fetch"] == EffectCategory.NETWORK_OUT
        assert git_entry.subcommand_overrides["clone"] == EffectCategory.NETWORK_OUT
        assert git_entry.subcommand_overrides["clean"] == EffectCategory.DESTRUCTIVE

    def test_docker_subcommand_overrides(self, registry):
        docker_entry = registry.lookup("docker")
        assert docker_entry is not None
        assert docker_entry.allow_subcommands is True
        assert docker_entry.subcommand_overrides.get("pull") == EffectCategory.WRITE_SYSTEM
        assert docker_entry.subcommand_overrides.get("run") == EffectCategory.WRITE_SYSTEM
        assert docker_entry.subcommand_overrides.get("build") == EffectCategory.WRITE_PROJECT
        assert docker_entry.subcommand_overrides.get("compose") == EffectCategory.WRITE_PROJECT

    def test_npm_subcommand_overrides(self, registry):
        npm_entry = registry.lookup("npm")
        assert npm_entry is not None
        assert npm_entry.allow_subcommands is True
        assert npm_entry.subcommand_overrides.get("install") == EffectCategory.WRITE_PROJECT
        assert npm_entry.subcommand_overrides.get("run") == EffectCategory.WRITE_PROJECT
        assert npm_entry.subcommand_overrides.get("test") == EffectCategory.WRITE_PROJECT
        assert npm_entry.subcommand_overrides.get("publish") == EffectCategory.NETWORK_OUT
        assert npm_entry.subcommand_overrides.get("list") == EffectCategory.READ_ONLY

    def test_pip_subcommand_overrides(self, registry):
        pip_entry = registry.lookup("pip")
        assert pip_entry is not None
        assert pip_entry.allow_subcommands is True
        assert pip_entry.subcommand_overrides.get("install") == EffectCategory.WRITE_PROJECT
        assert pip_entry.subcommand_overrides.get("list") == EffectCategory.READ_ONLY
        assert pip_entry.subcommand_overrides.get("show") == EffectCategory.READ_ONLY
        assert pip_entry.subcommand_overrides.get("download") == EffectCategory.NETWORK_OUT

    def test_windows_overrides(self, registry):
        for cmd in ["del", "erase", "rd", "format", "diskpart", "cmd", "powershell", "pwsh"]:
            entry = registry.lookup(cmd)
            assert entry is not None, f"Missing Windows command: {cmd}"
            assert EffectCategory.ESCALATE in entry.platform_overrides.get("win32", entry.category) or \
                   entry.platform_overrides.get("win32") == EffectCategory.ESCALATE or \
                   entry.category == EffectCategory.ESCALATE or \
                   entry.category == EffectCategory.DESTRUCTIVE, \
                   f"Windows command {cmd} should be ESCALATE or DESTRUCTIVE"

    def test_flag_overrides_for_interpreters(self, registry):
        """Interpreters with inline-eval flags should have flag_overrides for CODE_GEN."""
        for interp in ["python", "python3"]:
            entry = registry.lookup(interp)
            assert entry is not None
            assert "-c" in entry.flag_overrides, f"{interp} should have -c flag override"
            assert entry.flag_overrides["-c"] == EffectCategory.CODE_GEN

        node_entry = registry.lookup("node")
        assert node_entry is not None
        assert "-e" in node_entry.flag_overrides
        assert "--eval" in node_entry.flag_overrides
        assert node_entry.flag_overrides["-e"] == EffectCategory.CODE_GEN

        for interp in ["perl", "ruby"]:
            entry = registry.lookup(interp)
            assert entry is not None
            assert "-e" in entry.flag_overrides, f"{interp} should have -e flag override"
            assert entry.flag_overrides["-e"] == EffectCategory.CODE_GEN

        php_entry = registry.lookup("php")
        assert php_entry is not None
        assert "-r" in php_entry.flag_overrides
        assert php_entry.flag_overrides["-r"] == EffectCategory.CODE_GEN

    def test_shell_interpreter_base_is_escalate(self, registry):
        """Shell interpreters should have ESCALATE base category."""
        for interp in ["bash", "sh", "zsh", "fish", "ksh", "csh"]:
            entry = registry.lookup(interp)
            assert entry is not None, f"Missing shell interpreter: {interp}"
            assert entry.category == EffectCategory.ESCALATE, f"{interp} should be ESCALATE base"
            assert "-c" in entry.flag_overrides, f"{interp} should have -c flag override -> CODE_GEN"
            assert entry.flag_overrides["-c"] == EffectCategory.CODE_GEN


class TestRegistryCustomRegistration:
    def test_register_custom_command(self):
        registry = CommandEffectRegistry()
        registry.register("my-custom-tool", CommandEffectEntry(
            category=EffectCategory.WRITE_PROJECT,
        ))
        entry = registry.lookup("my-custom-tool")
        assert entry is not None
        assert entry.category == EffectCategory.WRITE_PROJECT

    def test_register_overrides_default(self):
        registry = CommandEffectRegistry()
        # Override ls to be DESTRUCTIVE (unlikely but possible)
        registry.register("ls", CommandEffectEntry(
            category=EffectCategory.DESTRUCTIVE,
        ))
        entry = registry.lookup("ls")
        assert entry is not None
        assert entry.category == EffectCategory.DESTRUCTIVE
