from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Callable

from pydantic import BaseModel, ConfigDict

from app.llm.base import MessageRole
from app.models.conversation import MessageType
from app.storage.database import db as default_db
from app.storage.models import MessageSearchDocumentModel, SessionModel


class _MessageSearchDocumentSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    role: str
    message_type: str
    search_text: str
    created_at: datetime


class RecallResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    score: float
    summary: str
    evidence: list[str]


class RecallService:
    """
    Deterministic recall service over derived message_search_documents.

    - Strictly scoped by project_id via join through sessions.project_id
    - No embeddings / vector DB; pure text overlap + heuristic boosts
    """

    _ascii_word_re = re.compile(r"[A-Za-z0-9_]+")

    def __init__(
        self,
        *,
        db=default_db,
        now: Callable[[], datetime] | None = None,
    ):
        self.db = db
        self._now = now or datetime.now

    def search(self, *, project_id: str, query: str, limit: int = 3) -> list[RecallResult]:
        if not project_id:
            raise ValueError("project_id is required")
        if not query:
            return []

        resolved_limit = self._resolve_limit(limit)
        if resolved_limit <= 0:
            return []

        now = self._now()
        candidates = self._list_project_documents(project_id=project_id, max_candidates=200)

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

    def _list_project_documents(self, *, project_id: str, max_candidates: int) -> list[_MessageSearchDocumentSnapshot]:
        with self.db.get_session() as db_session:
            # Strict scoping: documents do not carry project_id directly, so we join via sessions.
            rows = (
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
                .order_by(MessageSearchDocumentModel.created_at.desc())
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

    def _score_document(self, document: _MessageSearchDocumentSnapshot, *, query: str, now: datetime) -> float:
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
        try:
            return int(limit)
        except (TypeError, ValueError):
            return 0

    def _match_score(self, *, query: str, text: str) -> float:
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
        tokens: set[str] = set()
        if not text:
            return tokens

        lowered = text.lower()
        tokens.update(self._ascii_word_re.findall(lowered))

        # Add individual CJK characters so "记忆" queries can match without requiring segmentation libs.
        for char in lowered:
            codepoint = ord(char)
            if 0x4E00 <= codepoint <= 0x9FFF:
                tokens.add(char)

        return tokens

    def _to_result(self, document: _MessageSearchDocumentSnapshot, *, score: float) -> RecallResult:
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
        excerpt = self._excerpt(document.search_text or "", max_chars=140)
        return f"[{document.role}/{document.message_type}] {excerpt}".strip()

    def _format_evidence(self, document: _MessageSearchDocumentSnapshot) -> list[str]:
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

            model = db_session.query(MessageSearchDocumentModel).filter_by(message_id=message_id).first()
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
