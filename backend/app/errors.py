from __future__ import annotations


class AppError(Exception):
    code: str = "app_error"
    message: str = "应用错误"
    detail: dict | None = None

    def __init__(
        self, code: str | None = None, message: str | None = None, detail: dict | None = None
    ):
        self.code = code or self.__class__.code
        self.message = message or self.__class__.message
        self.detail = detail
        super().__init__(self.message)

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "message": self.message}
        if self.detail is not None:
            d["detail"] = self.detail
        return d

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class NotFoundError(AppError):
    code = "not_found"

    def __init__(self, resource: str, resource_id: str | None = None, message: str | None = None):
        self.resource = resource
        self.resource_id = resource_id
        msg = message or f"{resource}不存在"
        detail = {"resource": resource}
        if resource_id is not None:
            detail["resource_id"] = resource_id
        super().__init__(message=msg, detail=detail)


class ValidationError(AppError):
    code = "validation_error"

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message=message, detail=detail)


class LLMRetryExhaustedError(AppError):
    code = "llm_retry_exhausted"

    def __init__(self, last_exception: Exception, max_retries: int):
        self.last_exception = last_exception
        self.max_retries = max_retries
        msg = f"LLM 重试次数已达上限（{max_retries} 次）: {last_exception}"
        detail = {"max_retries": max_retries, "error_type": type(last_exception).__name__}
        super().__init__(message=msg, detail=detail)


class SecurityError(AppError):
    code = "security_error"

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message=message, detail=detail)


class ToolNotFoundError(AppError):
    code = "tool_not_found"

    def __init__(self, tool_name: str):
        msg = f"工具 {tool_name} 不存在"
        detail = {"tool_name": tool_name}
        super().__init__(message=msg, detail=detail)


class ExecutionError(AppError):
    code = "execution_error"

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message=message, detail=detail)


class NotFoundValueError(ValueError):
    """ValueError that should be mapped to a 404 NotFound response."""
    pass


def value_error_to_app_error(
    exc: ValueError, *, resource: str = "资源"
) -> NotFoundError | ValidationError:
    if isinstance(exc, NotFoundValueError):
        return NotFoundError(resource=resource, message=str(exc))
    return ValidationError(message=str(exc))
