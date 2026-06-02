from app.security.command_arity import extract_prefix_rule


def test_extract_prefix_rule_npm_run():
    assert extract_prefix_rule("npm run dev") == "npm run *"


def test_extract_prefix_rule_npm_run_with_flags():
    assert extract_prefix_rule("npm run dev --flag") == "npm run *"


def test_extract_prefix_rule_git_push():
    assert extract_prefix_rule("git push origin main") == "git push *"


def test_extract_prefix_rule_curl():
    assert extract_prefix_rule("curl https://example.com") == "curl *"


def test_extract_prefix_rule_simple_command():
    assert extract_prefix_rule("pytest") == "pytest *"


def test_extract_prefix_rule_python_script():
    assert extract_prefix_rule("python script.py") == "python *"


def test_extract_prefix_rule_unknown_command():
    assert extract_prefix_rule("mycustomtool --flag arg1") == "mycustomtool *"


def test_extract_prefix_rule_docker_compose():
    assert extract_prefix_rule("docker compose up -d") == "docker compose *"


def test_extract_prefix_rule_make_target():
    assert extract_prefix_rule("make build") == "make *"


def test_extract_prefix_rule_empty_string():
    assert extract_prefix_rule("") == "*"
