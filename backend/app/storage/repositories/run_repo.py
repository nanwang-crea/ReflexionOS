from app.models.conversation import Run
from app.storage.models import RunModel


class RunRepository:
    def __init__(self, db):
        self.db = db

    def create(self, run: Run) -> Run:
        with self.db.get_session() as db_session:
            model = RunModel(**run.model_dump())
            db_session.add(model)
            db_session.flush()
            db_session.refresh(model)
            return Run.model_validate(model)

    def get(self, run_id: str) -> Run | None:
        with self.db.get_session() as db_session:
            model = db_session.query(RunModel).filter_by(id=run_id).first()
            return Run.model_validate(model) if model else None

    def list_by_session(self, session_id: str) -> list[Run]:
        with self.db.get_session() as db_session:
            models = (
                db_session.query(RunModel)
                .filter_by(session_id=session_id)
                .order_by(RunModel.id.asc())
                .all()
            )
            return [Run.model_validate(model) for model in models]

    def update(self, run: Run) -> Run:
        with self.db.get_session() as db_session:
            model = db_session.query(RunModel).filter_by(id=run.id).first()
            if model is None:
                raise ValueError("运行不存在")

            model.status = run.status.value
            model.started_at = run.started_at
            model.finished_at = run.finished_at
            model.error_code = run.error_code
            model.error_message = run.error_message
            db_session.flush()
            db_session.refresh(model)
            return Run.model_validate(model)
