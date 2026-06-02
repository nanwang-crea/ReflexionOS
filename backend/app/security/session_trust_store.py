from fnmatch import fnmatch
from threading import RLock
from typing import Literal

from pydantic import BaseModel


class TrustRule(BaseModel):
    permission: str
    pattern: str
    action: Literal["allow"] = "allow"


class SessionTrustStore:
    def __init__(self) -> None:
        self._rules: dict[str, list[TrustRule]] = {}
        self._lock = RLock()

    def add_rule(self, session_id: str, rule: TrustRule) -> None:
        with self._lock:
            if session_id not in self._rules:
                self._rules[session_id] = []
            self._rules[session_id].append(rule)

    def get_rules(self, session_id: str) -> list[TrustRule]:
        with self._lock:
            return list(self._rules.get(session_id, []))

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._rules.pop(session_id, None)

    def matches(self, session_id: str, permission: str, target: str) -> bool:
        with self._lock:
            rules = self._rules.get(session_id, [])
            for rule in rules:
                if rule.permission == permission and fnmatch(target, rule.pattern):
                    return True
            return False
