# backend/app/security/session_trust_store.py
# 会话级信任规则存储：保存用户在某次审批时选择"以后信任此前缀"而生成的规则，
# 供 path_security.py（外部路径信任）和 command_policy.py（shell 命令信任）
# 在下次遇到相似操作时查询，从而免去重复审批。信任规则只在内存中按 session_id 隔离存放，
# 不做持久化——进程重启或会话结束后信任关系自动失效，避免"一次批准，永久放行"的风险积累。
from fnmatch import fnmatch
from threading import RLock
from typing import Literal

from pydantic import BaseModel


class TrustRule(BaseModel):
    """一条会话级信任规则。

    字段：
        permission: 规则适用的权限类别（如 "shell"、"external_path"），
            与 matches() 调用时传入的 permission 精确匹配（不做模糊匹配）。
        pattern: fnmatch 风格的匹配模式（如 "git *"、"/tmp/foo/*"）。
        action: 目前恒为 "allow"（Literal 类型约束），信任规则只表达"放行"，
            不支持用信任规则表达拒绝。
    """
    permission: str
    pattern: str
    action: Literal["allow"] = "allow"


class SessionTrustStore:
    """按会话 ID 隔离存储信任规则，支持并发读写。"""

    def __init__(self) -> None:
        """初始化空的规则存储，用 RLock 保护内部字典的并发访问。"""
        self._rules: dict[str, list[TrustRule]] = {}
        self._lock = RLock()

    def add_rule(self, session_id: str, rule: TrustRule) -> None:
        """为指定会话追加一条信任规则。

        参数：
            session_id: 会话 ID。
            rule: 待添加的 TrustRule。

        逻辑：
            加锁后若该会话尚无规则列表则先初始化为空列表，再把新规则追加进去
            （不去重、不覆盖同类规则，允许同一会话下累积多条规则）。

        返回：
            无返回值。
        """
        with self._lock:
            if session_id not in self._rules:
                self._rules[session_id] = []
            self._rules[session_id].append(rule)

    def get_rules(self, session_id: str) -> list[TrustRule]:
        """获取指定会话当前的全部信任规则。

        参数：
            session_id: 会话 ID。

        逻辑：
            加锁读取后返回列表的浅拷贝，避免调用方拿到内部列表引用后
            在锁外修改造成并发问题。

        返回：
            该会话的信任规则列表；会话不存在时返回空列表（不抛异常）。
        """
        with self._lock:
            return list(self._rules.get(session_id, []))

    def clear_session(self, session_id: str) -> None:
        """清空指定会话的全部信任规则（如会话结束时调用，避免信任规则无限累积）。

        参数：
            session_id: 会话 ID。

        返回：
            无返回值。会话不存在时静默忽略（pop 带默认值，不抛异常）。
        """
        with self._lock:
            self._rules.pop(session_id, None)

    def matches(self, session_id: str, permission: str, target: str) -> bool:
        """判断目标字符串是否命中该会话下某条信任规则。

        参数：
            session_id: 会话 ID。
            permission: 权限类别（如 "shell"、"external_path"），需与规则的 permission
                字段精确相等才参与匹配。
            target: 待匹配的目标字符串（命令原文或路径）。

        逻辑：
            加锁遍历该会话下的所有规则，permission 相等且 target 命中
            规则的 fnmatch pattern（glob 风格通配，如 "*"、"git *"）即判定命中，
            一旦命中立即返回 True（短路，不继续遍历剩余规则）。

        返回：
            是否命中任一条规则；该会话无规则或都不匹配时返回 False。
        """
        with self._lock:
            rules = self._rules.get(session_id, [])
            for rule in rules:
                if rule.permission == permission and fnmatch(target, rule.pattern):
                    return True
            return False
