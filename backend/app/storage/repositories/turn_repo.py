from datetime import datetime

from app.errors import NotFoundValueError
from app.models.conversation import Turn
from app.storage.models import TurnModel

from .base_repo import BaseRepository


class TurnRepository(BaseRepository[Turn]):
    def __init__(self, db):
        super().__init__(db, Turn)

    def create(self, turn: Turn, *, db_session=None) -> Turn:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(turn, db_session=managed_session)

        model = TurnModel(**turn.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def get(self, turn_id: str, *, db_session=None) -> Turn | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(turn_id, db_session=managed_session)

        model = db_session.query(TurnModel).filter_by(id=turn_id).first()
        return self._to_domain(model)

    def list_by_session(self, session_id: str) -> list[Turn]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(TurnModel)
                .filter_by(session_id=session_id)
                .order_by(TurnModel.turn_index.asc())
                .all()
            )
            return self._to_domain_list(models)

    def list_by_session_latest(self, session_id: str, limit: int) -> list[Turn]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(TurnModel)
                .filter(TurnModel.session_id == session_id)
                .order_by(TurnModel.turn_index.desc())
                .limit(limit)
                .all()
            )
            return self._to_domain_list(list(reversed(models)))

    def list_by_session_before(self, session_id: str, before_turn_id: str, limit: int) -> list[Turn]:
        with self.db.get_session() as db_session:
            cursor = (
                db_session.query(TurnModel)
                .filter_by(id=before_turn_id, session_id=session_id)
                .first()
            )
            if cursor is None:
                return []

            models = (
                db_session.query(TurnModel)
                .filter(
                    TurnModel.session_id == session_id,
                    TurnModel.turn_index < cursor.turn_index,
                )
                .order_by(TurnModel.turn_index.desc())
                .limit(limit)
                .all()
            )
            return self._to_domain_list(list(reversed(models)))

    def list_by_ids(self, turn_ids: list[str]) -> list[Turn]:
        if not turn_ids:
            return []
        with self.db.get_session() as db_session:
            models = (
                db_session.query(TurnModel)
                .filter(TurnModel.id.in_(turn_ids))
                .order_by(TurnModel.turn_index.asc())
                .all()
            )
            return self._to_domain_list(models)

    def delete_by_session_after_index(self, session_id: str, min_turn_index: int, *, db_session=None) -> list[str]:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete_by_session_after_index(session_id, min_turn_index, db_session=managed_session)

        turn_ids = (
            db_session.query(TurnModel.id)
            .filter(TurnModel.session_id == session_id, TurnModel.turn_index >= min_turn_index)
            .all()
        )
        turn_id_list = [tid[0] for tid in turn_ids]
        db_session.query(TurnModel).filter(
            TurnModel.session_id == session_id, TurnModel.turn_index >= min_turn_index
        ).delete(synchronize_session=False)
        db_session.flush()
        return turn_id_list

    def update(self, turn: Turn, *, db_session=None) -> Turn:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(turn, db_session=managed_session)

        model = db_session.query(TurnModel).filter_by(id=turn.id).first()
        if model is None:
            raise NotFoundValueError("轮次不存在")

        model.status = turn.status.value
        model.active_run_id = turn.active_run_id
        model.completed_at = turn.completed_at
        model.updated_at = turn.updated_at
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def next_turn_index(self, session_id: str, *, db_session=None) -> int:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.next_turn_index(session_id, db_session=managed_session)

        current = (
            db_session.query(TurnModel.turn_index)
            .filter_by(session_id=session_id)
            .order_by(TurnModel.turn_index.desc())
            .limit(1)
            .scalar()
        ) or 0
        return current + 1

    def list_terminal_before(
        self, statuses: list[str], before: datetime, *, db_session=None
    ) -> list[Turn]:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.list_terminal_before(statuses, before, db_session=managed_session)

        models = (
            db_session.query(TurnModel)
            .filter(
                TurnModel.status.in_(statuses),
                TurnModel.completed_at.isnot(None),
                TurnModel.completed_at < before,
            )
            .order_by(TurnModel.completed_at.asc(), TurnModel.turn_index.asc())
            .all()
        )
        return self._to_domain_list(models)
