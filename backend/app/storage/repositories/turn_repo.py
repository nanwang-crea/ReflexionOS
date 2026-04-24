from app.models.conversation import Turn
from app.storage.models import TurnModel


class TurnRepository:
    def __init__(self, db):
        self.db = db

    def create(self, turn: Turn) -> Turn:
        with self.db.get_session() as db_session:
            model = TurnModel(**turn.model_dump())
            db_session.add(model)
            db_session.flush()
            db_session.refresh(model)
            return Turn.model_validate(model)

    def get(self, turn_id: str) -> Turn | None:
        with self.db.get_session() as db_session:
            model = db_session.query(TurnModel).filter_by(id=turn_id).first()
            return Turn.model_validate(model) if model else None

    def list_by_session(self, session_id: str) -> list[Turn]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(TurnModel)
                .filter_by(session_id=session_id)
                .order_by(TurnModel.turn_index.asc())
                .all()
            )
            return [Turn.model_validate(model) for model in models]

    def update(self, turn: Turn) -> Turn:
        with self.db.get_session() as db_session:
            model = db_session.query(TurnModel).filter_by(id=turn.id).first()
            if model is None:
                raise ValueError("轮次不存在")

            model.status = turn.status.value
            model.active_run_id = turn.active_run_id
            model.completed_at = turn.completed_at
            model.updated_at = turn.updated_at
            db_session.flush()
            db_session.refresh(model)
            return Turn.model_validate(model)

    def next_turn_index(self, session_id: str) -> int:
        with self.db.get_session() as db_session:
            current = (
                db_session.query(TurnModel.turn_index)
                .filter_by(session_id=session_id)
                .order_by(TurnModel.turn_index.desc())
                .limit(1)
                .scalar()
            ) or 0
            return current + 1
