"""
记忆召回服务模块。

在 message_search_documents（消息归一化后的搜索索引表，见 message_normalizer）
之上实现一个确定性的文本召回：不依赖向量库/embedding，纯靠词汇重合度 + 角色/
消息类型/时间新鲜度的启发式加权来给候选消息打分排序，返回与 query 最相关的
若干条历史消息作为“回忆”结果，供对话时注入上下文使用。
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.llm.base import MessageRole
from app.models.conversation import MessageType
from app.storage.database import db as default_db
from app.storage.models import MessageSearchDocumentModel, SessionModel


class _MessageSearchDocumentSnapshot(BaseModel):
    """从 message_search_documents 表读出的一条搜索文档快照（只读，用于打分排序）。"""

    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    role: str
    message_type: str
    search_text: str
    created_at: datetime


class RecallResult(BaseModel):
    """一条召回结果：命中消息的定位信息、打分及供展示的摘要/证据。"""

    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    score: float
    summary: str
    evidence: list[str]


class RecallService:
    """
    基于派生表 message_search_documents 的确定性召回服务。

    - 严格按 project_id 过滤（通过 join sessions.project_id 限定范围）
    - 不使用向量库/embedding，纯文本词汇重合度 + 启发式加权，结果可复现
    """

    _ascii_word_re = re.compile(r"[A-Za-z0-9_]+")

    def __init__(
        self,
        *,
        db=default_db,
        now: Callable[[], datetime] | None = None,
    ):
        """
        参数：
            db: 数据库访问对象，默认使用全局单例 db；测试时可注入替身。
            now: 获取当前时间的可调用对象，默认 datetime.now；测试时可注入固定时间以保证可复现。
        """
        self.db = db
        self._now = now or datetime.now

    def search(self, *, project_id: str, query: str, limit: int = 3, session_id: str | None = None) -> list[RecallResult]:
        """
        对指定项目（可选限定会话）执行一次文本召回检索。

        参数：
            project_id: 项目 ID，必填，用于限定候选消息范围。
            query: 查询文本；为空时直接返回空列表。
            limit: 期望返回的最大结果数，默认 3。
            session_id: 可选，指定后只在该会话内召回。
        逻辑：
            1. 校验 project_id/query/limit 合法性，任一无效则提前返回；
            2. 取该项目下最多 200 条候选文档（按创建时间倒序）；
            3. 对每条候选调用 _score_document 打分，分数为 0 的视为不相关；
            4. 按 (分数, 创建时间, message_id) 三元组降序排序，取分数 > 0 的前 limit 条；
        返回：
            按相关度降序排列的 RecallResult 列表，可能为空。
        """
        if not project_id:
            raise ValueError("project_id is required")
        if not query:
            return []

        resolved_limit = self._resolve_limit(limit)
        if resolved_limit <= 0:
            return []

        now = self._now()
        candidates = self._list_project_documents(project_id=project_id, session_id=session_id, max_candidates=200)

        scored: list[tuple[float, datetime, str, _MessageSearchDocumentSnapshot]] = []
        for document in candidates:
            score = self._score_document(document, query=query, now=now)
            # Deterministic tiebreakers: prefer newer docs, then stable message_id ordering.
            # Note: avoid datetime.timestamp() for naive datetimes (timezone-dependent).
            scored.append((score, document.created_at, document.message_id, document))

        ranked = sorted(scored, key=lambda item: (item[0], item[1], item[2]), reverse=True)
        results: list[RecallResult] = []
        for score, _created_at, _message_id, document in ranked:
            if score <= 0:
                continue
            results.append(self._to_result(document, score=score))
            if len(results) >= resolved_limit:
                break
        return results

    def _list_project_documents(
        self, *, project_id: str, max_candidates: int, session_id: str | None = None
    ) -> list[_MessageSearchDocumentSnapshot]:
        """
        查询指定项目（可选指定会话）下最近的搜索文档候选集。

        参数：
            project_id: 项目 ID，通过 join SessionModel 过滤。
            max_candidates: 最多返回的候选条数（按创建时间倒序取前 N 条）。
            session_id: 可选，指定后仅返回该会话内的文档。
        返回：
            _MessageSearchDocumentSnapshot 列表，按 created_at 倒序。
        """
        with self.db.get_session() as db_session:
            q = (
                db_session.query(
                    MessageSearchDocumentModel.message_id,
                    MessageSearchDocumentModel.session_id,
                    MessageSearchDocumentModel.role,
                    MessageSearchDocumentModel.message_type,
                    MessageSearchDocumentModel.search_text,
                    MessageSearchDocumentModel.created_at,
                )
                .join(SessionModel, MessageSearchDocumentModel.session_id == SessionModel.id)
                .filter(SessionModel.project_id == project_id)
            )
            if session_id:
                q = q.filter(MessageSearchDocumentModel.session_id == session_id)
            rows = (
                q.order_by(MessageSearchDocumentModel.created_at.desc())
                .limit(max_candidates)
                .all()
            )
            return [
                _MessageSearchDocumentSnapshot(
                    message_id=row[0],
                    session_id=row[1],
                    role=row[2],
                    message_type=row[3],
                    search_text=row[4] or "",
                    created_at=row[5],
                )
                for row in rows
            ]

    def _score_document(
        self, document: _MessageSearchDocumentSnapshot, *, query: str, now: datetime
    ) -> float:
        """
        计算单条候选文档相对 query 的最终得分。

        参数：
            document: 候选搜索文档快照。
            query: 查询文本。
            now: 当前时间，用于计算新鲜度衰减。
        逻辑：
            基础分 = 词汇重合度（_match_score），为 0 则直接返回 0（不相关）；
            在此基础上叠加三类启发式加权：
              - role_boost：用户消息（role=user）权重更高，因为通常承载用户意图；
              - type_boost：USER_MESSAGE/SYSTEM_NOTICE 类型权重更高；
              - recency_boost：越新的消息权重越高，30 天内线性衰减，最低不低于 0.5。
        返回：
            四项相乘得到的最终得分（float），未命中时为 0.0。
        """
        match_score = self._match_score(query=query, text=document.search_text or "")
        if match_score <= 0:
            return 0.0

        role_boost = 2.0 if (document.role or "").lower() == MessageRole.USER else 1.0
        boosted_types = {MessageType.USER_MESSAGE.value, MessageType.SYSTEM_NOTICE.value}
        type_boost = 1.5 if document.message_type in boosted_types else 1.0

        age_seconds = max((now - document.created_at).total_seconds(), 0.0)
        age_days = age_seconds / 86400.0
        recency_boost = max(0.5, 1.5 - min(age_days, 30.0) * 0.03)

        return float(match_score * role_boost * type_boost * recency_boost)

    def _resolve_limit(self, limit: int) -> int:
        """将外部传入的 limit 安全转为 int；非法值（无法转换）视为 0（即不返回结果）。"""
        try:
            return int(limit)
        except (TypeError, ValueError):
            return 0

    def _match_score(self, *, query: str, text: str) -> float:
        """
        计算 query 与 text 的词汇重合度得分。

        参数：
            query: 查询文本。
            text: 候选文档正文。
        逻辑：
            分别对 query/text 分词（_tokens），取交集词数 matches；
            用 matches / sqrt(|query_tokens| * |text_tokens|) 归一化，
            使分数不因文档长度差异而失真，结果落在 (0, 1] 区间内。
        返回：
            重合度得分；任一方无有效词或无交集时返回 0.0。
        """
        q_tokens = self._tokens(query)
        if not q_tokens:
            return 0.0

        t_tokens = self._tokens(text)
        if not t_tokens:
            return 0.0

        matches = len(q_tokens.intersection(t_tokens))
        if matches <= 0:
            return 0.0

        # Favor covering more of the query while keeping the score stable across doc length.
        # This yields (0, 1] roughly, and is deterministic.
        return matches / math.sqrt(len(q_tokens) * len(t_tokens))

    def _tokens(self, text: str) -> set[str]:
        """
        将文本切分为词汇集合，兼容英文单词与中文单字。

        参数：
            text: 待分词文本。
        逻辑：
            - 英文/数字/下划线部分用正则 _ascii_word_re 提取为单词（小写化后）；
            - 中日韩统一表意文字（CJK，Unicode 0x4E00-0x9FFF）逐字加入，
              避免引入分词库依赖，粒度为单字。
        返回：
            词汇集合（set[str]），空文本返回空集合。
        """
        tokens: set[str] = set()
        if not text:
            return tokens

        lowered = text.lower()
        tokens.update(self._ascii_word_re.findall(lowered))

        # Add individual CJK characters so queries can match without segmentation libs.
        for char in lowered:
            codepoint = ord(char)
            if 0x4E00 <= codepoint <= 0x9FFF:
                tokens.add(char)

        return tokens

    def _to_result(self, document: _MessageSearchDocumentSnapshot, *, score: float) -> RecallResult:
        """将打分后的文档快照转换为对外的 RecallResult（含摘要与证据字段）。"""
        summary = self._format_summary(document)
        evidence = self._format_evidence(document)
        return RecallResult(
            message_id=document.message_id,
            session_id=document.session_id,
            score=score,
            summary=summary,
            evidence=evidence,
        )

    def _format_summary(self, document: _MessageSearchDocumentSnapshot) -> str:
        """生成一行简短摘要：`[角色/消息类型] 正文摘录（最多140字符）`。"""
        excerpt = self._excerpt(document.search_text or "", max_chars=140)
        return f"[{document.role}/{document.message_type}] {excerpt}".strip()

    def _format_evidence(self, document: _MessageSearchDocumentSnapshot) -> list[str]:
        """生成召回证据列表：session_id/message_id/created_at/role/type/excerpt 各一行，便于追溯来源。"""
        excerpt = self._excerpt(document.search_text or "", max_chars=240)
        created_at = document.created_at.isoformat(timespec="seconds")
        return [
            f"session_id={document.session_id}",
            f"message_id={document.message_id}",
            f"created_at={created_at}",
            f"role={document.role}",
            f"type={document.message_type}",
            f"excerpt={excerpt}",
        ]

    def _excerpt(self, text: str, *, max_chars: int) -> str:
        """将文本折叠为单行（合并空白）并截断到 max_chars，超长部分以 "…" 结尾。"""
        collapsed = " ".join((text or "").split())
        if len(collapsed) <= max_chars:
            return collapsed
        return collapsed[: max(0, max_chars - 1)] + "…"

    # Test helper: seed derived docs without needing the full conversation projection.
    def seed_document(
        self,
        *,
        message_id: str,
        project_id: str,
        session_id: str,
        role: str,
        message_type: str,
        search_text: str,
        turn_index: int,
        turn_message_index: int,
        created_at: str,
    ) -> None:
        """
        测试辅助方法：直接向 message_search_documents（及缺失的 session）写入一条搜索文档，
        无需走完整的会话/消息投影流程，便于单元测试快速构造召回候选数据。

        参数：
            message_id: 消息 ID，作为文档的唯一定位键（存在则更新，不存在则插入）。
            project_id: 所属项目 ID；若对应 session 不存在会一并创建一条占位 session。
            session_id: 所属会话 ID。
            role: 消息角色（如 user/assistant）。
            message_type: 消息类型（对应 MessageType 的取值）。
            search_text: 归一化后的搜索正文。
            turn_index: 所属轮次序号，用于生成 turn_id。
            turn_message_index: 该消息在轮次内的序号。
            created_at: ISO 格式的创建时间字符串，会被解析为 datetime。
        返回：
            无（直接写库）。
        """
        created = datetime.fromisoformat(created_at)
        with self.db.get_session() as db_session:
            existing_session = db_session.query(SessionModel).filter_by(id=session_id).first()
            if existing_session is None:
                db_session.add(
                    SessionModel(
                        id=session_id,
                        project_id=project_id,
                        title="seeded",
                        preferred_provider_id=None,
                        preferred_model_id=None,
                        last_event_seq=0,
                        active_turn_id=None,
                        created_at=created,
                        updated_at=created,
                    )
                )
                db_session.flush()

            model = (
                db_session.query(MessageSearchDocumentModel)
                .filter_by(message_id=message_id)
                .first()
            )
            turn_id = f"turn-{session_id}-{turn_index}"
            now = created
            if model is None:
                model = MessageSearchDocumentModel(
                    message_id=message_id,
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=None,
                    role=role,
                    message_type=message_type,
                    turn_index=turn_index,
                    turn_message_index=turn_message_index,
                    search_text=search_text,
                    created_at=created,
                    updated_at=now,
                )
                db_session.add(model)
            else:
                model.session_id = session_id
                model.turn_id = turn_id
                model.run_id = None
                model.role = role
                model.message_type = message_type
                model.turn_index = turn_index
                model.turn_message_index = turn_message_index
                model.search_text = search_text
                model.created_at = created
                model.updated_at = now

            db_session.flush()
