from app.security.session_trust_store import SessionTrustStore, TrustRule


def test_trust_store_add_and_match():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))

    assert store.matches("session-1", "shell", "npm run dev") is True
    assert store.matches("session-1", "shell", "npm run build") is True
    assert store.matches("session-1", "shell", "npm install") is False


def test_trust_store_no_match_without_rules():
    store = SessionTrustStore()
    assert store.matches("session-1", "shell", "npm run dev") is False


def test_trust_store_different_sessions_isolated():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))

    assert store.matches("session-1", "shell", "npm run dev") is True
    assert store.matches("session-2", "shell", "npm run dev") is False


def test_trust_store_different_permissions():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))

    assert store.matches("session-1", "file", "npm run dev") is False


def test_trust_store_clear_session():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))
    store.clear_session("session-1")

    assert store.matches("session-1", "shell", "npm run dev") is False


def test_trust_store_get_rules():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))
    store.add_rule("session-1", TrustRule(permission="shell", pattern="git push *"))

    rules = store.get_rules("session-1")
    assert len(rules) == 2
    assert rules[0].pattern == "npm run *"
    assert rules[1].pattern == "git push *"


def test_trust_store_glob_wildcard():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="git *"))

    assert store.matches("session-1", "shell", "git push") is True
    assert store.matches("session-1", "shell", "git commit") is True
    assert store.matches("session-1", "shell", "git log --oneline") is True


def test_trust_store_glob_question_mark():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="pytest ?"))

    assert store.matches("session-1", "shell", "pytest x") is True
    assert store.matches("session-1", "shell", "pytest tests/") is False


def test_trust_store_multiple_rules_match():
    store = SessionTrustStore()
    store.add_rule("session-1", TrustRule(permission="shell", pattern="npm run *"))
    store.add_rule("session-1", TrustRule(permission="shell", pattern="git *"))

    assert store.matches("session-1", "shell", "npm run test") is True
    assert store.matches("session-1", "shell", "git commit") is True
    assert store.matches("session-1", "shell", "curl example.com") is False
