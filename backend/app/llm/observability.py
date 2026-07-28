from contextlib import contextmanager
from contextvars import ContextVar, Token

from pydantic import BaseModel, ConfigDict

_llm_observability_context: ContextVar["LLMCallObservabilityContext | None"] = ContextVar(
    "llm_observability_context",
    default=None,
)


class LLMCallObservabilityContext(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    run_id: str | None = None
    project_name_snapshot: str | None = None
    session_title_snapshot: str | None = None
    call_kind: str | None = None
    loop_iteration: int | None = None

    def merged(
        self,
        override: "LLMCallObservabilityContext | None",
    ) -> "LLMCallObservabilityContext":
        if override is None:
            return self
        return self.model_copy(update=override.model_dump(exclude_none=True))


def get_llm_observability_context() -> LLMCallObservabilityContext | None:
    return _llm_observability_context.get()


@contextmanager
def llm_observability_scope(context: LLMCallObservabilityContext):
    token: Token = _llm_observability_context.set(context)
    try:
        yield
    finally:
        _llm_observability_context.reset(token)
