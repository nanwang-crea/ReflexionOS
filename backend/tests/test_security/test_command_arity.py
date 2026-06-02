from app.security.command_arity import extract_prefix_rule


def test_normal_command_uses_first_token():
    assert extract_prefix_rule("npm run dev") == "npm *"


def test_git_uses_first_token():
    assert extract_prefix_rule("git push origin main") == "git *"
    assert extract_prefix_rule("git commit -m 'msg'") == "git *"


def test_simple_command():
    assert extract_prefix_rule("pytest") == "pytest *"
    assert extract_prefix_rule("curl https://example.com") == "curl *"


def test_unknown_command_uses_first_token():
    assert extract_prefix_rule("mycustomtool --flag arg1") == "mycustomtool *"


def test_docker_compose_uses_first_token():
    assert extract_prefix_rule("docker compose up -d") == "docker *"


def test_empty_string():
    assert extract_prefix_rule("") == "*"


def test_rm_is_deny_trust():
    assert extract_prefix_rule("rm file.txt") == "rm file.txt *"


def test_rm_rf_is_deny_trust():
    assert extract_prefix_rule("rm -rf dir") == "rm -rf dir *"


def test_chmod_is_deny_trust():
    assert extract_prefix_rule("chmod 755 file.sh") == "chmod 755 file.sh *"


def test_dd_is_deny_trust():
    assert extract_prefix_rule("dd if=/dev/zero of=/dev/sda") == "dd if=/dev/zero of=/dev/sda *"


def test_normal_command_not_in_deny_list():
    assert extract_prefix_rule("echo hello world") == "echo *"
