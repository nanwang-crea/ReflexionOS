# 应用统一错误类型定义模块。
# 所有业务异常均继承自 AppError，携带 code/message/detail 三要素，
# 由 app/main.py 中的全局异常处理器统一捕获并映射为对应 HTTP 状态码返回给前端。

from __future__ import annotations


class AppError(Exception):
    """应用错误基类，所有业务异常的父类。
    携带错误码（code）、用户可读信息（message）、附加详情（detail），
    供全局异常处理器统一序列化为 JSON 响应。
    """
    code: str = "app_error"
    message: str = "应用错误"
    detail: dict | None = None

    def __init__(
        self, code: str | None = None, message: str | None = None, detail: dict | None = None
    ):
        """初始化异常实例。
        参数：code 错误码（缺省用类属性默认值）、message 错误信息（同上）、detail 附加详情字典。
        """
        self.code = code or self.__class__.code
        self.message = message or self.__class__.message
        self.detail = detail
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """将异常序列化为字典，用于构造 JSON 响应体。
        返回：包含 code、message，以及（若存在）detail 的字典。
        """
        d: dict = {"code": self.code, "message": self.message}
        if self.detail is not None:
            d["detail"] = self.detail
        return d

    def __str__(self) -> str:
        """返回 `[code] message` 格式的字符串表示，便于日志打印。"""
        return f"[{self.code}] {self.message}"


class NotFoundError(AppError):
    """资源不存在错误，对应 HTTP 404。"""
    code = "not_found"

    def __init__(self, resource: str, resource_id: str | None = None, message: str | None = None):
        """参数：resource 资源类型名（如"项目"）、resource_id 资源 ID（可选）、
        message 自定义错误信息（缺省时自动生成"{resource}不存在"）。
        """
        self.resource = resource
        self.resource_id = resource_id
        msg = message or f"{resource}不存在"
        detail = {"resource": resource}
        if resource_id is not None:
            detail["resource_id"] = resource_id
        super().__init__(message=msg, detail=detail)


class ValidationError(AppError):
    """参数/输入校验失败错误，对应 HTTP 400。"""
    code = "validation_error"

    def __init__(self, message: str, detail: dict | None = None):
        """参数：message 校验失败信息、detail 附加详情（可选）。"""
        super().__init__(message=message, detail=detail)


class LLMRetryExhaustedError(AppError):
    """LLM 调用重试次数耗尽错误。"""
    code = "llm_retry_exhausted"

    def __init__(self, last_exception: Exception, max_retries: int):
        """参数：last_exception 最后一次重试失败的原始异常、max_retries 最大重试次数。
        自动拼装包含次数和原始异常信息的错误消息。
        """
        self.last_exception = last_exception
        self.max_retries = max_retries
        msg = f"LLM 重试次数已达上限（{max_retries} 次）: {last_exception}"
        detail = {"max_retries": max_retries, "error_type": type(last_exception).__name__}
        super().__init__(message=msg, detail=detail)


class SecurityError(AppError):
    """安全相关错误（如越权访问、路径穿越等），对应 HTTP 403。"""
    code = "security_error"

    def __init__(self, message: str, detail: dict | None = None):
        """参数：message 安全错误信息、detail 附加详情（可选）。"""
        super().__init__(message=message, detail=detail)


class ToolNotFoundError(AppError):
    """Agent 工具未找到错误。"""
    code = "tool_not_found"

    def __init__(self, tool_name: str):
        """参数：tool_name 未找到的工具名称，用于生成错误信息和 detail。"""
        msg = f"工具 {tool_name} 不存在"
        detail = {"tool_name": tool_name}
        super().__init__(message=msg, detail=detail)


class ExecutionError(AppError):
    """工具/任务执行过程中的通用错误。"""
    code = "execution_error"

    def __init__(self, message: str, detail: dict | None = None):
        """参数：message 执行失败信息、detail 附加详情（可选）。"""
        super().__init__(message=message, detail=detail)


class NotFoundValueError(ValueError):
    """ValueError that should be mapped to a 404 NotFound response."""
    pass


def value_error_to_app_error(
    exc: ValueError, *, resource: str = "资源"
) -> NotFoundError | ValidationError:
    """将标准库 ValueError 转换为 AppError 子类，便于统一异常处理器识别。
    参数：exc 待转换的 ValueError 实例、resource 资源类型名（用于 NotFoundError 场景，默认"资源"）。
    工作流程：若 exc 是 NotFoundValueError，转换为 NotFoundError；否则转换为 ValidationError。
    返回：NotFoundError 或 ValidationError 实例。
    """
    if isinstance(exc, NotFoundValueError):
        return NotFoundError(resource=resource, message=str(exc))
    return ValidationError(message=str(exc))
