from typing import Generic, TypeVar, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.storage.database import Database

DomainModel = TypeVar("DomainModel", bound=BaseModel)


class BaseRepository(Generic[DomainModel]):
    def __init__(self, db: "Database", domain_cls: type[DomainModel]):
        self.db = db
        self._domain_cls = domain_cls

    def _to_domain(self, model) -> DomainModel | None:
        if model is None:
            return None
        return self._domain_cls.model_validate(model)

    def _to_domain_list(self, models) -> list[DomainModel]:
        return [self._domain_cls.model_validate(m) for m in models]
