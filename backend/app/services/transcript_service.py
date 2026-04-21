from typing import Optional

from app.models.session_history import (
    SessionHistoryItemDto,
    SessionHistoryResponse,
    SessionHistoryRoundDto,
)
from app.storage.database import db
from app.storage.repositories.conversation_repo import ConversationRepository
from app.storage.repositories.session_repo import SessionRepository

class TranscriptService:
    def __init__(
        self,
        conversation_repo: Optional[ConversationRepository] = None,
        session_repo: Optional[SessionRepository] = None,
    ):
        self.conversation_repo = conversation_repo or ConversationRepository(db)
        self.session_repo = session_repo or SessionRepository(db)

    def build_session_history(self, session_id: str) -> SessionHistoryResponse:
        session = self.session_repo.get(session_id)
        if not session:
            raise ValueError("会话不存在")

        items = self.conversation_repo.list_by_session(session_id)
        rounds: list[SessionHistoryRoundDto] = []
        current_round: Optional[SessionHistoryRoundDto] = None

        for item in items:
            item_response = self._to_item_response(item)
            if item.item_type == "user-message":
                current_round = SessionHistoryRoundDto(
                    id=f"round-{item.id}",
                    created_at=item.created_at,
                    items=[item_response],
                )
                rounds.append(current_round)
                continue

            if current_round is not None:
                current_round.items.append(item_response)

        return SessionHistoryResponse(
            session_id=session_id,
            project_id=session.project_id,
            rounds=rounds,
        )

    def _to_item_response(self, item) -> SessionHistoryItemDto:
        return SessionHistoryItemDto(
            id=item.id,
            type=item.item_type,
            content=item.content,
            receipt_status=item.receipt_status,
            details=item.details_json,
            created_at=item.created_at,
        )


transcript_service = TranscriptService()
