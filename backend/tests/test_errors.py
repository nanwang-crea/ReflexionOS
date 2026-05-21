import pytest

from app.errors import (
    AppError,
    ExecutionError,
    LLMRetryExhaustedError,
    NotFoundError,
    SecurityError,
    ToolNotFoundError,
    ValidationError,
)


class TestAppError:
    def test_fields(self):
        err = AppError(code="test_code", message="test msg")
        assert err.code == "test_code"
        assert err.message == "test msg"
        assert err.detail is None

    def test_with_detail(self):
        err = AppError(code="c", message="m", detail={"key": "val"})
        assert err.detail == {"key": "val"}

    def test_to_dict_without_detail(self):
        err = AppError(code="c", message="m")
        assert err.to_dict() == {"code": "c", "message": "m"}

    def test_to_dict_with_detail(self):
        err = AppError(code="c", message="m", detail={"k": "v"})
        assert err.to_dict() == {"code": "c", "message": "m", "detail": {"k": "v"}}

    def test_str(self):
        err = AppError(code="c", message="m")
        assert str(err) == "[c] m"

    def test_is_exception(self):
        with pytest.raises(AppError):
            raise AppError(code="x", message="y")

    def test_is_exception_base(self):
        try:
            raise AppError(code="x", message="y")
        except Exception:
            pass
        else:
            pytest.fail("AppError should be catchable as Exception")

    def test_defaults(self):
        err = AppError()
        assert err.code == "app_error"
        assert err.message == "应用错误"
        assert err.detail is None


class TestNotFoundError:
    def test_basic(self):
        err = NotFoundError(resource="用户")
        assert err.code == "not_found"
        assert err.message == "用户不存在"
        assert err.detail == {"resource": "用户"}

    def test_with_resource_id(self):
        err = NotFoundError(resource="用户", resource_id="123")
        assert err.detail == {"resource": "用户", "resource_id": "123"}

    def test_custom_message(self):
        err = NotFoundError(resource="用户", message="找不到该用户")
        assert err.message == "找不到该用户"

    def test_all_params(self):
        err = NotFoundError(resource="文件", resource_id="f1", message="文件缺失")
        assert err.code == "not_found"
        assert err.message == "文件缺失"
        assert err.detail == {"resource": "文件", "resource_id": "f1"}


class TestValidationError:
    def test_basic(self):
        err = ValidationError(message="参数无效")
        assert err.code == "validation_error"
        assert err.message == "参数无效"
        assert err.detail is None

    def test_with_detail(self):
        err = ValidationError(message="参数无效", detail={"field": "age"})
        assert err.detail == {"field": "age"}


class TestLLMRetryExhaustedError:
    def test_basic(self):
        original = TimeoutError("connection timed out")
        err = LLMRetryExhaustedError(last_exception=original, max_retries=3)
        assert err.code == "llm_retry_exhausted"
        assert err.last_exception is original
        assert err.max_retries == 3
        assert "3" in err.message
        assert "connection timed out" in err.message
        assert err.detail == {"max_retries": 3, "error_type": "TimeoutError"}

    def test_message_format(self):
        original = ValueError("bad value")
        err = LLMRetryExhaustedError(last_exception=original, max_retries=5)
        assert err.message == "LLM 重试次数已达上限（5 次）: bad value"


class TestSecurityError:
    def test_basic(self):
        err = SecurityError(message="权限不足")
        assert err.code == "security_error"
        assert err.message == "权限不足"
        assert err.detail is None

    def test_with_detail(self):
        err = SecurityError(message="权限不足", detail={"user": "admin"})
        assert err.detail == {"user": "admin"}


class TestToolNotFoundError:
    def test_basic(self):
        err = ToolNotFoundError(tool_name="calculator")
        assert err.code == "tool_not_found"
        assert err.message == "工具 calculator 不存在"
        assert err.detail == {"tool_name": "calculator"}


class TestExecutionError:
    def test_basic(self):
        err = ExecutionError(message="执行失败")
        assert err.code == "execution_error"
        assert err.message == "执行失败"
        assert err.detail is None

    def test_with_detail(self):
        err = ExecutionError(message="执行失败", detail={"step": 2})
        assert err.detail == {"step": 2}
