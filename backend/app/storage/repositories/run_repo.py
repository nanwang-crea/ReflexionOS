from app.errors import NotFoundValueError
from app.models.conversation import Run
from app.storage.models import RunModel

from .base_repo import BaseRepository


class RunRepository(BaseRepository[Run]):
    def __init__(self, db):
        super().__init__(db, Run)

    def create(self, run: Run, *, db_session=None) -> Run:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(run, db_session=managed_session)

        model = RunModel(**run.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def get(self, run_id: str, *, db_session=None) -> Run | None:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(run_id, db_session=managed_session)

        model = db_session.query(RunModel).filter_by(id=run_id).first()
        return self._to_domain(model)

    def list_by_session(self, session_id: str) -> list[Run]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(RunModel)
                .filter_by(session_id=session_id)
                .order_by(
                    RunModel.turn_id.asc(),
                    RunModel.attempt_index.asc(),
                    RunModel.id.asc(),
                )
                .all()
            )
            return self._to_domain_list(models)

    def list_by_turn_ids(self, turn_ids: list[str]) -> list[Run]:
        if not turn_ids:
            return []
        with self.db.get_session() as db_session:
            models = (
                db_session.query(RunModel)
                .filter(RunModel.turn_id.in_(turn_ids))
                .order_by(
                    RunModel.turn_id.asc(),
                    RunModel.attempt_index.asc(),
                    RunModel.id.asc(),
                )
                .all()
            )
            return self._to_domain_list(models)

    def update(self, run: Run, *, db_session=None) -> Run:
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(run, db_session=managed_session)

        model = db_session.query(RunModel).filter_by(id=run.id).first()
        if model is None:
            raise NotFoundValueError("运行不存在")

        model.status = run.status.value
        model.started_at = run.started_at
        model.finished_at = run.finished_at
        model.error_code = run.error_code
        model.error_message = run.error_message
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
        if not turn_ids:
            return 0

        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete_by_turn_ids(turn_ids, db_session=managed_session)

        deleted = (
            db_session.query(RunModel)
            .filter(RunModel.turn_id.in_(turn_ids))
            .delete(synchronize_session=False)
        )
        db_session.flush()
        return int(deleted or 0)
