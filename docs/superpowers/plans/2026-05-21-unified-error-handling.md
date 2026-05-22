# 统一错误处理体系 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立前后端统一的错误处理体系，确保所有错误信息都能正确传递并展示给用户，消除静默吞掉异常的问题。

**Architecture:** 后端引入 `AppError` 错误基类 + FastAPI 全局 exception handler，统一 HTTP 和 WebSocket 的错误响应格式；WebSocket 最外层异常改为发送 `conversation:error` 而非静默断连；`run:cancelled` 事件携带原因数据；前端构建 Toast 通知组件替代 `window.alert()`，WebSocket 错误事件触发 Toast 展示，Run 失败/取消在 transcript 中渲染错误信息。

**Tech Stack:** Python / FastAPI / Pydantic (后端), TypeScript / React / Zustand / TailwindCSS / Framer Motion (前端)

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/app/errors.py` | `AppError` 基类 + 子类定义 |

### Backend — Modified Files
| File | Change |
|------|--------|
| `backend/app/main.py` | 注册全局 exception handler |
| `backend/app/api/routes/websocket.py` | 最外层 except 发送 error 后断连；run:cancelled 携带 data |
| `backend/app/services/conversation_runtime_adapter.py` | `_execution_cancelled_events` 接收 data，区分取消原因 |
| `backend/app/execution/rapid_loop.py` | `_emit` 回调失败时抛异常而非静默吞掉 |
| `backend/app/llm/retry.py` | `RetryExhaustedError` 继承 `AppError` |
| `backend/app/security/path_security.py` | `SecurityError` 继承 `AppError` |
| `backend/app/security/shell_security.py` | `ShellSecurityError` 继承 `AppError` |
| `backend/app/tools/registry.py` | `ToolNotFoundError` 继承 `AppError` |
| `backend/app/tools/diff_parser.py` | `CodexPatchParseError` 继承 `AppError` |
| `backend/app/api/routes/projects.py` | 移除手动 try/except HTTPException，让全局 handler 处理 |
| `backend/app/api/routes/sessions.py` | 同上 |
| `backend/app/api/routes/llm.py` | 同上 |

### Frontend — New Files
| File | Responsibility |
|------|---------------|
| `frontend/src/components/common/Toast.tsx` | Toast 通知组件 |
| `frontend/src/stores/toastStore.ts` | Toast 状态管理 (Zustand) |
| `frontend/src/hooks/useToast.ts` | Toast 便捷 hook |

### Frontend — Modified Files
| File | Change |
|------|--------|
| `frontend/src/services/dialogService.ts` | `notifyError` 改为 toast 调用，保留 confirm/prompt |
| `frontend/src/hooks/useConversationRuntime.ts` | `conversation:error` 触发 toast；`connection:error` 触发 toast；`run.failed`/`run.cancelled` 展示错误 |
| `frontend/src/components/workspace/WorkspaceTranscript.tsx` | 渲染 Run 失败/取消的错误提示 |
| `frontend/src/components/workspace/transcriptItems.ts` | 支持从 `payloadJson` 提取 run-level 错误 |
| `frontend/src/pages/AgentWorkspace.tsx` | 挂载 Toast 容器 |
| `frontend/src/features/llm/useSettingsPageController.ts` | 消除 `catch(() => undefined)`，加 toast |
| `frontend/src/features/llm/llmSettingsLoader.ts` | 加载失败时 toast 提示 |
| `frontend/src/hooks/useSessionData.ts` | LLM 设置加载失败加 toast |
| `frontend/src/components/layout/WorkspaceSidebar.tsx` | 项目加载失败加 toast |
| `frontend/src/pages/SkillsPage.tsx` | 技能加载失败加 toast |

---

## Task 1: 后端 — 创建 AppError 错误基类体系

**Files:**
- Create: `backend/app/errors.py`
- Test: `backend/tests/test_errors.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_errors.py
import pytest
from app.errors import (
    AppError,
    NotFoundError,
    ValidationError,
    LLMRetryExhaustedError,
    SecurityError,
    ToolNotFoundError,
    ExecutionError,
)


def test_app_error_fields():
    err = AppError(code="test_error", message="测试错误")
    assert err.code == "test_error"
    assert err.message == "测试错误"
    assert err.detail is None
    assert str(err) == "测试错误"


def test_app_error_with_detail():
    err = AppError(code="test_error", message="测试错误", detail={"key": "value"})
    assert err.detail == {"key": "value"}


def test_app_error_to_dict():
    err = AppError(code="test_error", message="测试错误", detail={"retry": 3})
    d = err.to_dict()
    assert d == {"code": "test_error", "message": "测试错误", "detail": {"retry": 3}}


def test_not_found_error():
    err = NotFoundError(resource="项目", resource_id="abc")
    assert err.code == "not_found"
    assert "项目" in err.message
    assert err.detail == {"resource": "项目", "resource_id": "abc"}


def test_validation_error():
    err = ValidationError(message="名称不能为空")
    assert err.code == "validation_error"
    assert err.message == "名称不能为空"


def test_llm_retry_exhausted_error():
    original = RuntimeError("API 连接超时")
    err = LLMRetryExhaustedError(last_exception=original, max_retries=5)
    assert err.code == "llm_retry_exhausted"
    assert err.max_retries == 5
    assert err.last_exception is original
    assert "5" in err.message
    assert "API 连接超时" in err.message
    assert err.detail == {"max_retries": 5, "error_type": "RuntimeError"}


def test_security_error():
    err = SecurityError(message="/etc/passwd 不在允许的目录中")
    assert err.code == "security_error"


def test_tool_not_found_error():
    err = ToolNotFoundError(tool_name="nonexistent_tool")
    assert err.code == "tool_not_found"
    assert "nonexistent_tool" in err.message


def test_execution_error():
    err = ExecutionError(message="执行异常")
    assert err.code == "execution_error"


def test_app_error_is_exception():
    with pytest.raises(AppError):
        raise AppError(code="test", message="test")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.errors'`

- [ ] **Step 3: 实现最小代码**

```python
# backend/app/errors.py
from __future__ import annotations


class AppError(Exception):
    """应用层统一错误基类。"""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        detail: dict | None = None,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)

    def to_dict(self) -> dict:
        result: dict = {"code": self.code, "message": self.message}
        if self.detail is not None:
            result["detail"] = self.detail
        return result


class NotFoundError(AppError):
    def __init__(self, *, resource: str, resource_id: str | None = None, message: str | None = None):
        msg = message or f"{resource}不存在"
        detail: dict = {"resource": resource}
        if resource_id is not None:
            detail["resource_id"] = resource_id
        super().__init__(code="not_found", message=msg, detail=detail)


class ValidationError(AppError):
    def __init__(self, *, message: str, detail: dict | None = None):
        super().__init__(code="validation_error", message=message, detail=detail)


class LLMRetryExhaustedError(AppError):
    def __init__(self, *, last_exception: Exception, max_retries: int):
        self.last_exception = last_exception
        self.max_retries = max_retries
        super().__init__(
            code="llm_retry_exhausted",
            message=f"LLM 重试次数已达上限（{max_retries} 次）: {last_exception}",
            detail={"max_retries": max_retries, "error_type": type(last_exception).__name__},
        )


class SecurityError(AppError):
    def __init__(self, *, message: str, detail: dict | None = None):
        super().__init__(code="security_error", message=message, detail=detail)


class ToolNotFoundError(AppError):
    def __init__(self, *, tool_name: str):
        super().__init__(
            code="tool_not_found",
            message=f"工具 {tool_name} 不存在",
            detail={"tool_name": tool_name},
        )


class ExecutionError(AppError):
    def __init__(self, *, message: str, detail: dict | None = None):
        super().__init__(code="execution_error", message=message, detail=detail)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/test_errors.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add backend/app/errors.py backend/tests/test_errors.py
git commit -m "feat: add AppError unified error hierarchy"
```

---

## Task 2: 后端 — 注册 FastAPI 全局 exception handler

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 添加全局 exception handler 到 main.py**

在 `backend/app/main.py` 中，`app = FastAPI(...)` 之后、`app.add_middleware(...)` 之前，添加：

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from app.errors import AppError

@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    status_code = 400
    if exc.code == "not_found":
        status_code = 404
    elif exc.code == "security_error":
        status_code = 403
    return JSONResponse(
        status_code=status_code,
        content=exc.to_dict(),
    )
```

同时添加 import：在文件顶部 import 区添加 `from app.errors import AppError` 和 `from fastapi import Request` 以及 `from fastapi.responses import JSONResponse`。

- [ ] **Step 2: 验证 main.py 可正常启动**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -c "from app.main import app; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add backend/app/main.py
git commit -m "feat: register global AppError exception handler in FastAPI"
```

---

## Task 3: 后端 — 迁移现有错误类继承 AppError

**Files:**
- Modify: `backend/app/llm/retry.py` — `RetryExhaustedError` 改为继承新 `LLMRetryExhaustedError`
- Modify: `backend/app/security/path_security.py` — `SecurityError` 改为继承新 `SecurityError`
- Modify: `backend/app/security/shell_security.py` — `ShellSecurityError` 改为继承新 `SecurityError`
- Modify: `backend/app/tools/registry.py` — `ToolNotFoundError` 改为继承新 `ToolNotFoundError`
- Modify: `backend/app/tools/diff_parser.py` — `CodexPatchParseError` 改为继承 `ValidationError`

- [ ] **Step 1: 修改 `backend/app/llm/retry.py`**

删除旧的 `RetryExhaustedError` 类（原 line 19-25），替换为从 `app.errors` 导入：

```python
from app.errors import LLMRetryExhaustedError as RetryExhaustedError
```

注意：用 `as RetryExhaustedError` 保持所有引用此类的代码无需修改。

`retry_async` 函数在 line 92-93 中 `raise RetryExhaustedError(...)` 的调用签名需要适配。旧签名是 `RetryExhaustedError(last_exception, max_retries=max_retries)`，新签名是 `LLMRetryExhaustedError(*, last_exception, max_retries)`。需将 line 93 改为：

```python
        raise RetryExhaustedError(last_exception=last_exc, max_retries=max_retries) from last_exc
```

- [ ] **Step 2: 修改 `backend/app/security/path_security.py`**

将原有的 `class SecurityError(Exception)` 改为继承 `app.errors.SecurityError`：

```python
from app.errors import SecurityError as AppSecurityError

class SecurityError(AppSecurityError):
    """文件路径安全错误，保持向后兼容。"""

    def __init__(self, message: str):
        super().__init__(message=message)
```

- [ ] **Step 3: 修改 `backend/app/security/shell_security.py`**

```python
from app.errors import SecurityError as AppSecurityError

class ShellSecurityError(AppSecurityError):
    """Shell 命令安全错误，保持向后兼容。"""

    def __init__(self, message: str):
        super().__init__(message=message)
```

- [ ] **Step 4: 修改 `backend/app/tools/registry.py`**

```python
from app.errors import ToolNotFoundError as AppToolNotFoundError

class ToolNotFoundError(AppToolNotFoundError):
    """工具未注册错误，保持向后兼容。"""

    def __init__(self, tool_name: str):
        super().__init__(tool_name=tool_name)
```

- [ ] **Step 5: 修改 `backend/app/tools/diff_parser.py`**

```python
from app.errors import ValidationError as AppValidationError

class CodexPatchParseError(AppValidationError):
    """Codex 补丁解析错误。"""

    def __init__(self, message: str):
        super().__init__(message=message)
```

- [ ] **Step 6: 运行后端全部测试确认无破坏**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/ -x -q`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add backend/app/llm/retry.py backend/app/security/path_security.py backend/app/security/shell_security.py backend/app/tools/registry.py backend/app/tools/diff_parser.py
git commit -m "refactor: migrate existing error classes to inherit from AppError"
```

---

## Task 4: 后端 — HTTP 路由改用 AppError 替代 ValueError + HTTPException

**Files:**
- Modify: `backend/app/api/routes/projects.py`
- Modify: `backend/app/api/routes/sessions.py`
- Modify: `backend/app/api/routes/llm.py`

将各路由中 `raise ValueError(...)` + `try/except` + `HTTPException` 的模式改为直接 `raise NotFoundError(...)` 或 `raise ValidationError(...)`，由全局 handler 自动处理。

- [ ] **Step 1: 修改 `backend/app/api/routes/projects.py`**

替换整个文件为：

```python
from fastapi import APIRouter

from app.errors import NotFoundError
from app.models.project import Project, ProjectCreate
from app.services.project_service import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/", response_model=Project)
async def create_project(project: ProjectCreate):
    return project_service.create_project(project)


@router.get("/", response_model=list[Project])
async def list_projects():
    return project_service.list_projects()


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str):
    project = project_service.get_project(project_id)
    if not project:
        raise NotFoundError(resource="项目", resource_id=project_id)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    if not project_service.delete_project(project_id):
        raise NotFoundError(resource="项目", resource_id=project_id)
    return {"message": "项目已删除"}


@router.get("/{project_id}/structure")
async def get_project_structure(project_id: str):
    structure = project_service.get_project_structure(project_id)
    if not structure:
        raise NotFoundError(resource="项目", resource_id=project_id, message="项目不存在或路径无效")
    return structure
```

- [ ] **Step 2: 修改 `backend/app/api/routes/sessions.py`**

替换整个文件为：

```python
from fastapi import APIRouter

from app.errors import NotFoundError, ValidationError
from app.models.conversation_snapshot import ConversationSnapshot
from app.models.session import Session
from app.services.conversation_service import conversation_service
from app.services.session_service import SessionCreate, SessionUpdate, session_service

router = APIRouter(prefix="/api", tags=["sessions"])


def _value_error_to_app_error(exc: ValueError) -> NotFoundError | ValidationError:
    msg = str(exc)
    if "不存在" in msg:
        return NotFoundError(resource="会话", message=msg)
    return ValidationError(message=msg)


@router.post("/projects/{project_id}/sessions", response_model=Session)
async def create_session(project_id: str, payload: SessionCreate):
    try:
        return session_service.create_session(project_id, payload)
    except ValueError as exc:
        raise _value_error_to_app_error(exc) from exc


@router.get("/projects/{project_id}/sessions", response_model=list[Session])
async def list_project_sessions(project_id: str):
    try:
        return session_service.list_project_sessions(project_id)
    except ValueError as exc:
        raise _value_error_to_app_error(exc) from exc


@router.get("/sessions/{session_id}", response_model=Session)
async def get_session(session_id: str):
    session = session_service.get_session(session_id)
    if not session:
        raise NotFoundError(resource="会话", resource_id=session_id)
    return session


@router.get("/sessions/{session_id}/conversation", response_model=ConversationSnapshot)
async def get_session_conversation(session_id: str):
    try:
        return conversation_service.get_snapshot(session_id)
    except ValueError as exc:
        raise _value_error_to_app_error(exc) from exc


@router.patch("/sessions/{session_id}", response_model=Session)
async def update_session(session_id: str, payload: SessionUpdate):
    try:
        return session_service.update_session(session_id, payload)
    except ValueError as exc:
        raise _value_error_to_app_error(exc) from exc


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        session_service.delete_session(session_id)
        return {"message": "会话已删除"}
    except ValueError as exc:
        raise _value_error_to_app_error(exc) from exc
```

- [ ] **Step 3: 修改 `backend/app/api/routes/llm.py`**

替换整个文件为：

```python
from fastapi import APIRouter

from app.errors import NotFoundError, ValidationError
from app.models.llm_config import (
    DefaultLLMSelection,
    ProviderConnectionTestRequest,
    ProviderConnectionTestResult,
    ProviderInstanceConfig,
)
from app.services.llm_provider_service import llm_provider_service

router = APIRouter(prefix="/api/llm", tags=["llm"])


def _value_error_to_app_error(exc: ValueError) -> NotFoundError | ValidationError:
    msg = str(exc)
    if "不存在" in msg:
        return NotFoundError(resource="供应商", message=msg)
    return ValidationError(message=msg)


@router.get("/providers", response_model=list[ProviderInstanceConfig])
async def list_providers():
    return llm_provider_service.list_providers()


@router.post("/providers", response_model=ProviderInstanceConfig)
async def create_provider(provider: ProviderInstanceConfig):
    try:
        return llm_provider_service.create_provider(provider)
    except ValueError as exc:
        raise _value_error_to_app_error(exc) from exc


@router.put("/providers/{provider_id}", response_model=ProviderInstanceConfig)
async def update_provider(provider_id: str, provider: ProviderInstanceConfig):
    try:
        return llm_provider_service.update_provider(provider_id, provider)
    except ValueError as exc:
        raise _value_error_to_app_error(exc) from exc


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    try:
        llm_provider_service.delete_provider(provider_id)
        return {"message": "供应商已删除"}
    except ValueError as exc:
        raise NotFoundError(resource="供应商", resource_id=provider_id, message=str(exc)) from exc


@router.post("/providers/test", response_model=ProviderConnectionTestResult)
async def test_provider_connection(request: ProviderConnectionTestRequest):
    try:
        return await llm_provider_service.test_provider_connection(
            request.provider,
            request.model_id,
        )
    except ValueError as exc:
        raise ValidationError(message=str(exc)) from exc
    except Exception as exc:
        raise ValidationError(message=f"连接测试失败: {exc}") from exc


@router.get("/default", response_model=DefaultLLMSelection)
async def get_default_selection():
    return llm_provider_service.get_default_selection()


@router.put("/default", response_model=DefaultLLMSelection)
async def set_default_selection(selection: DefaultLLMSelection):
    try:
        return llm_provider_service.set_default_selection(selection)
    except ValueError as exc:
        raise _value_error_to_app_error(exc) from exc
```

- [ ] **Step 4: 运行后端测试确认无破坏**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/ -x -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add backend/app/api/routes/projects.py backend/app/api/routes/sessions.py backend/app/api/routes/llm.py
git commit -m "refactor: HTTP routes raise AppError instead of ValueError+HTTPException"
```

---

## Task 5: 后端 — WebSocket 最外层异常发送 error 消息而非静默断连

**Files:**
- Modify: `backend/app/api/routes/websocket.py`

- [ ] **Step 1: 修改最外层 except 块**

将 `websocket.py` 的 line 208-210 从：

```python
    except Exception as exc:  # pragma: no cover
        logger.error("WebSocket 错误: %s", exc)
        ws_manager.disconnect(websocket, session_id)
```

改为：

```python
    except Exception as exc:  # pragma: no cover
        logger.error("WebSocket 错误: %s", exc)
        try:
            await _send_error(
                websocket,
                code="internal_error",
                message=f"内部错误: {exc}",
            )
        except Exception:
            pass
        ws_manager.disconnect(websocket, session_id)
```

这样客户端在断连前会收到一条 `conversation:error` 消息，包含错误信息。

- [ ] **Step 2: 运行测试确认无破坏**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/ -x -q`
Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add backend/app/api/routes/websocket.py
git commit -m "fix: send conversation:error before disconnecting on WebSocket exception"
```

---

## Task 6: 后端 — run:cancelled 事件携带取消原因数据

**Files:**
- Modify: `backend/app/services/conversation_runtime_adapter.py` — `_execution_cancelled_events` 接收 data 参数
- Modify: `backend/app/api/routes/websocket.py` — `run:cancelled` 处理传入 data（如适用）

这是**最关键的修复** — LLM 重试耗尽后的原始错误信息在这里丢失。

- [ ] **Step 1: 修改 `conversation_runtime_adapter.py` 的 `handle_event` 方法**

将 line 92-93 从：

```python
        if event_type == "run:cancelled":
            return self._append_events(self._execution_cancelled_events())
```

改为：

```python
        if event_type == "run:cancelled":
            return self._append_events(self._execution_cancelled_events(data))
```

- [ ] **Step 2: 修改 `_execution_cancelled_events` 方法签名和实现**

找到 `_execution_cancelled_events` 方法，将签名从 `def _execution_cancelled_events(self)` 改为 `def _execution_cancelled_events(self, data: dict)`，并更新内部逻辑以区分取消原因：

```python
    def _execution_cancelled_events(self, data: dict) -> list[ConversationEvent]:
        reason = data.get("reason")
        error_msg = data.get("error")

        if reason == "llm_retry_exhausted":
            error_code = "llm_retry_exhausted"
            error_message = f"LLM 重试次数已达上限: {error_msg}" if error_msg else "LLM 重试次数已达上限"
        elif reason == "user_cancelled":
            error_code = "run_cancelled"
            error_message = "本次执行已取消"
        else:
            error_code = "run_cancelled"
            error_message = data.get("result") or "本次执行已取消"

        events = self._close_open_messages_for_cancel(error_code, error_message)

        terminal_event = self._run_terminal_event(
            EventType.RUN_CANCELLED,
            payload_json={
                "finished_at": datetime.now().isoformat(),
                "error_code": error_code,
                "error_message": error_message,
            },
        )
        if terminal_event is not None:
            events.append(terminal_event)
            events.append(self._cancel_notice_event())
        return events
```

- [ ] **Step 3: 修改 `_close_open_messages_for_cancel` 方法签名**

将签名从 `def _close_open_messages_for_cancel(self)` 改为 `def _close_open_messages_for_cancel(self, error_code: str = "run_cancelled", error_message: str = "本次执行已取消")`：

```python
    def _close_open_messages_for_cancel(self, error_code: str = "run_cancelled", error_message: str = "本次执行已取消") -> list[ConversationEvent]:
        events = self._assistant_terminal_events(
            terminal_event_type=EventType.MESSAGE_FAILED,
            payload_json={
                "error_code": error_code,
                "error_message": error_message,
            },
        )
        open_ids: set[str] = {
            message.id
            for message in self.conversation_service.message_repo.list_by_turn(self.turn_id)
            if message.run_id == self.run_id
            and message.message_type in {MessageType.ASSISTANT_MESSAGE, MessageType.TOOL_TRACE}
            and message.stream_state in {StreamState.IDLE, StreamState.STREAMING}
        }

        if self.assistant_message_id:
            open_ids.discard(self.assistant_message_id)
        open_ids.update(self.tool_message_ids.values())

        for message_id in sorted(open_ids):
            if self._message_is_terminal(message_id):
                continue
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_PAYLOAD_UPDATED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={"payload_json": {"status": "cancelled"}},
                )
            )
            events.append(
                self._new_event(
                    event_type=EventType.MESSAGE_FAILED,
                    message_id=message_id,
                    run_id=self.run_id,
                    payload_json={
                        "error_code": error_code,
                        "error_message": error_message,
                    },
                )
            )

        return events
```

- [ ] **Step 4: 修改 `rapid_loop.py` 的 `RetryExhaustedError` 处理，传入 reason 和 error**

在 `rapid_loop.py` line 390-404 中，`run:cancelled` 的 emit 已经包含 `reason` 和 `error` 字段，无需修改。但需确认 `run:error` 的 emit 也传入足够信息。当前 line 406-413 已有：

```python
except Exception as e:
    loop_result.status = LoopStatus.FAILED
    loop_result.result = f"执行异常: {str(e)}"
    logger.error("执行异常: %s\n%s", e, traceback.format_exc())
    await self._emit("run:error", {"error": str(e)})
```

这里 `run:error` 会走 `_execution_error_events` 路径，已经有 `error_code` 和 `error_message`，无需修改。

- [ ] **Step 5: 修改 `rapid_loop.py` 的 `_emit` 方法，回调失败时抛异常而非静默**

将 line 77-83 从：

```python
    async def _emit(self, event_type: str, data: dict) -> None:
        """发送事件"""
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.error("事件回调失败: %s", e)
```

改为：

```python
    async def _emit(self, event_type: str, data: dict) -> None:
        """发送事件"""
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as e:
                logger.error("事件回调失败: %s", e)
                raise
```

这样当事件回调失败时（比如数据库写入失败），异常会向上传播，run 会被标记为 FAILED 而非继续假装成功。

- [ ] **Step 6: 运行后端测试**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/ -x -q`
Expected: 全部 PASS（部分依赖 `_emit` 静默吞异常的测试可能需要更新）

- [ ] **Step 7: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add backend/app/services/conversation_runtime_adapter.py backend/app/execution/rapid_loop.py
git commit -m "fix: propagate cancellation reason and error details through run:cancelled events"
```

---

## Task 7: 前端 — 创建 Toast 通知组件

**Files:**
- Create: `frontend/src/stores/toastStore.ts`
- Create: `frontend/src/components/common/Toast.tsx`
- Create: `frontend/src/hooks/useToast.ts`

- [ ] **Step 1: 创建 toastStore.ts**

```typescript
// frontend/src/stores/toastStore.ts
import { create } from 'zustand'

export type ToastLevel = 'error' | 'warning' | 'info'

export interface ToastItem {
  id: string
  level: ToastLevel
  message: string
  duration: number
}

interface ToastState {
  toasts: ToastItem[]
  addToast: (level: ToastLevel, message: string, duration?: number) => void
  removeToast: (id: string) => void
}

let nextId = 0

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (level, message, duration = 5000) => {
    const id = `toast-${nextId++}`
    set((state) => ({
      toasts: [...state.toasts, { id, level, message, duration }],
    }))
    if (duration > 0) {
      setTimeout(() => {
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        }))
      }, duration)
    }
  },
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }))
  },
}))
```

- [ ] **Step 2: 创建 Toast.tsx 组件**

```typescript
// frontend/src/components/common/Toast.tsx
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, Info, AlertTriangle, X } from 'lucide-react'
import { useToastStore, type ToastItem } from '@/stores/toastStore'

const levelConfig: Record<string, { icon: typeof AlertCircle; bg: string; border: string; text: string }> = {
  error: { icon: AlertCircle, bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-800' },
  warning: { icon: AlertTriangle, bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-800' },
  info: { icon: Info, bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-800' },
}

function ToastItem({ item }: { item: ToastItem }) {
  const removeToast = useToastStore((s) => s.removeToast)
  const config = levelConfig[item.level] ?? levelConfig.info
  const Icon = config.icon

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -12, scale: 0.96 }}
      transition={{ duration: 0.18 }}
      className={`flex items-start gap-2 rounded-lg border ${config.border} ${config.bg} px-4 py-3 shadow-lg ${config.text}`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="flex-1 text-sm leading-5">{item.message}</span>
      <button
        type="button"
        onClick={() => removeToast(item.id)}
        className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
      >
        <X className="h-4 w-4" />
      </button>
    </motion.div>
  )
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-4">
      <div className="pointer-events-auto flex w-full max-w-lg flex-col gap-2">
        <AnimatePresence mode="popLayout">
          {toasts.map((item) => (
            <ToastItem key={item.id} item={item} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 创建 useToast.ts hook**

```typescript
// frontend/src/hooks/useToast.ts
import { useToastStore, type ToastLevel } from '@/stores/toastStore'

export function useToast() {
  const addToast = useToastStore((s) => s.addToast)
  return {
    showError: (message: string) => addToast('error', message),
    showWarning: (message: string) => addToast('warning', message),
    showInfo: (message: string) => addToast('info', message),
  }
}

export function showToast(level: ToastLevel, message: string, duration?: number) {
  useToastStore.getState().addToast(level, message, duration)
}
```

- [ ] **Step 4: 验证 TypeScript 编译**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: 无新增错误

- [ ] **Step 5: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add frontend/src/stores/toastStore.ts frontend/src/components/common/Toast.tsx frontend/src/hooks/useToast.ts
git commit -m "feat: add Toast notification component and store"
```

---

## Task 8: 前端 — 挂载 Toast 容器 + 更新 dialogService

**Files:**
- Modify: `frontend/src/pages/AgentWorkspace.tsx` — 挂载 `<ToastContainer />`
- Modify: `frontend/src/services/dialogService.ts` — `notifyError` 改为 toast 调用

- [ ] **Step 1: 在 AgentWorkspace.tsx 中挂载 Toast 容器**

在 `AgentWorkspace.tsx` 的 import 区添加：

```typescript
import { ToastContainer } from '@/components/common/Toast'
```

在 `<div className="flex h-full flex-col bg-white">` 之前添加：

```tsx
      <ToastContainer />
```

即 return 语句变为：

```tsx
  return (
    <>
      <ToastContainer />
      <div className="flex h-full flex-col bg-white">
        ...
      </div>
    </>
  )
```

- [ ] **Step 2: 更新 dialogService.ts**

将 `nativeDialogService.notifyError` 改为使用 toast：

```typescript
// frontend/src/services/dialogService.ts
import { useToastStore } from '@/stores/toastStore'

export interface DialogService {
  notifyError: (message: string) => void
  confirmAction: (message: string) => boolean
  promptText: (message: string, defaultValue?: string) => string | null
}

export const nativeDialogService: DialogService = {
  notifyError: (message) => {
    useToastStore.getState().addToast('error', message)
  },
  confirmAction: (message) => window.confirm(message),
  promptText: (message, defaultValue) => window.prompt(message, defaultValue),
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: 无新增错误

- [ ] **Step 4: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add frontend/src/pages/AgentWorkspace.tsx frontend/src/services/dialogService.ts
git commit -m "feat: mount ToastContainer and update dialogService to use toast"
```

---

## Task 9: 前端 — WebSocket 错误事件触发 Toast + 连接失败 Toast

**Files:**
- Modify: `frontend/src/hooks/useConversationRuntime.ts`

- [ ] **Step 1: 修改 `conversation:error` 处理**

在 `useConversationRuntime.ts` 的 import 区添加：

```typescript
import { useToastStore } from '@/stores/toastStore'
```

将 line 176-179 从：

```typescript
    ws.on('conversation:error', (data) => {
      console.error('Conversation websocket error:', data)
      setIsCancelling(false)
    })
```

改为：

```typescript
    ws.on('conversation:error', (data) => {
      console.error('Conversation websocket error:', data)
      const message = typeof data.message === 'string' ? data.message : '对话发生错误'
      useToastStore.getState().addToast('error', message)
      setIsCancelling(false)
    })
```

- [ ] **Step 2: 修改连接失败处理**

将 line 306-309 从：

```typescript
    connectSession(currentSessionId).catch((error) => {
      console.error('Failed to initialize conversation runtime:', error)
      setConnectionStatus('disconnected')
    })
```

改为：

```typescript
    connectSession(currentSessionId).catch((error) => {
      console.error('Failed to initialize conversation runtime:', error)
      const message = error instanceof Error ? error.message : '连接失败'
      useToastStore.getState().addToast('error', `对话连接失败: ${message}`)
      setConnectionStatus('disconnected')
    })
```

- [ ] **Step 3: 验证 TypeScript 编译**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: 无新增错误

- [ ] **Step 4: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add frontend/src/hooks/useConversationRuntime.ts
git commit -m "feat: show toast on WebSocket errors and connection failures"
```

---

## Task 10: 前端 — Run 失败/取消在 Transcript 中渲染错误信息

**Files:**
- Modify: `frontend/src/components/workspace/WorkspaceTranscript.tsx`
- Modify: `frontend/src/features/conversation/conversationReducer.ts`

当前 `assistant_message` 在 `streamState === 'failed'` 或 `streamState === 'cancelled'` 时无任何特殊渲染。需要在 transcript 中显示错误原因。

- [ ] **Step 1: 在 WorkspaceTranscript.tsx 中为失败的 assistant_message 添加错误提示**

在 `assistant_message` 渲染分支（line 185-197）中，增加失败/取消状态判断：

将 line 185-197 从：

```tsx
            if (message.messageType === 'assistant_message') {
              return (
                <SlideIn key={message.id} direction="up">
                  <div className="mb-10">
                    <MarkdownRenderer
                      content={message.contentText || ''}
                      variant="plain"
                      isStreaming={message.streamState === 'streaming'}
                      className={transcriptClassName}
                    />
                  </div>
                </SlideIn>
              )
            }
```

改为：

```tsx
            if (message.messageType === 'assistant_message') {
              const isFailed = message.streamState === 'failed'
              const isCancelled = message.streamState === 'cancelled'
              const errorCode = message.payloadJson?.error_code as string | undefined
              const errorMessage = message.payloadJson?.error_message as string | undefined

              return (
                <SlideIn key={message.id} direction="up">
                  <div className="mb-10">
                    {message.contentText && (
                      <MarkdownRenderer
                        content={message.contentText}
                        variant="plain"
                        isStreaming={message.streamState === 'streaming'}
                        className={transcriptClassName}
                      />
                    )}
                    {(isFailed || isCancelled) && (errorMessage || errorCode) && (
                      <div className={`mt-3 rounded-lg border px-4 py-3 text-sm ${
                        isFailed
                          ? 'border-red-200 bg-red-50 text-red-800'
                          : 'border-amber-200 bg-amber-50 text-amber-800'
                      }`}>
                        <div className="flex items-center gap-2 font-medium">
                          {isFailed ? '执行失败' : '执行已取消'}
                        </div>
                        {errorMessage && (
                          <div className="mt-1 text-xs opacity-80">{errorMessage}</div>
                        )}
                      </div>
                    )}
                  </div>
                </SlideIn>
              )
            }
```

- [ ] **Step 2: 确保 conversationReducer 中 message.failed/cancelled 事件携带 error_code 和 error_message**

在 `conversationReducer.ts` 的 `applyConversationEvent` 中，`message.payload_updated` 事件已经能合并 `payloadJson`，而 `message.failed` 事件类型虽然当前只更新了 `lastEventSeq`，但实际后端通过 `MESSAGE_FAILED` 事件设置了 `error_code` 和 `error_message`。

需要确保 `message.failed` 事件也更新 `payloadJson`。在 `applyConversationEvent` 函数的 return 语句之前（line 213-216 之前），添加：

```typescript
  if (event.eventType === 'message.failed') {
    return {
      ...currentState,
      lastEventSeq: event.seq,
      messagesById: {
        ...currentState.messagesById,
        [event.messageId]: {
          ...currentMessage,
          streamState: 'failed',
          payloadJson: {
            ...currentMessage.payloadJson,
            ...event.payloadJson,
          },
          updatedAt: event.createdAt,
        },
      },
    }
  }

  if (event.eventType === 'message.cancelled') {
    return {
      ...currentState,
      lastEventSeq: event.seq,
      messagesById: {
        ...currentState.messagesById,
        [event.messageId]: {
          ...currentMessage,
          streamState: 'cancelled',
          payloadJson: {
            ...currentMessage.payloadJson,
            ...event.payloadJson,
          },
          updatedAt: event.createdAt,
        },
      },
    }
  }
```

- [ ] **Step 3: 验证 TypeScript 编译**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: 无新增错误

- [ ] **Step 4: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add frontend/src/components/workspace/WorkspaceTranscript.tsx frontend/src/features/conversation/conversationReducer.ts
git commit -m "feat: render run failure/cancellation errors in transcript"
```

---

## Task 11: 前端 — 消除所有静默吞掉错误的 catch 块

**Files:**
- Modify: `frontend/src/features/llm/useSettingsPageController.ts`
- Modify: `frontend/src/features/llm/llmSettingsLoader.ts`
- Modify: `frontend/src/hooks/useSessionData.ts`
- Modify: `frontend/src/components/layout/WorkspaceSidebar.tsx`
- Modify: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: 修复 `useSettingsPageController.ts`**

在 import 区添加：

```typescript
import { useToastStore } from '@/stores/toastStore'
```

将 `refreshSettings().catch(() => undefined)` 改为：

```typescript
refreshSettings().catch((error) => {
  console.error('Failed to refresh settings:', error)
  useToastStore.getState().addToast('error', '刷新设置失败')
})
```

- [ ] **Step 2: 修复 `llmSettingsLoader.ts`**

在 import 区添加：

```typescript
import { useToastStore } from '@/stores/toastStore'
```

在 catch 块中添加 toast 通知，将 line 137-143 的 catch 块改为：

```typescript
    } catch (error) {
      console.error('Failed to load LLM settings:', error)
      useToastStore.getState().addToast('error', '加载 LLM 设置失败，请检查配置')
      options.resetStoredSettings()
      setProviders([])
      setDefaultSelection(createEmptySelection())
      ...
    }
```

- [ ] **Step 3: 修复 `useSessionData.ts`**

在 import 区添加：

```typescript
import { useToastStore } from '@/stores/toastStore'
```

将 `ensureLLMSettingsLoaded().catch((error) => { console.error('Failed to load LLM settings:', error) })` 改为：

```typescript
ensureLLMSettingsLoaded().catch((error) => {
  console.error('Failed to load LLM settings:', error)
  useToastStore.getState().addToast('warning', '加载 LLM 设置失败')
})
```

- [ ] **Step 4: 修复 `WorkspaceSidebar.tsx`**

在 import 区添加：

```typescript
import { useToastStore } from '@/stores/toastStore'
```

将 `ensureProjectsLoaded().catch((error) => { console.error('Failed to load projects:', error) })` 改为：

```typescript
ensureProjectsLoaded().catch((error) => {
  console.error('Failed to load projects:', error)
  useToastStore.getState().addToast('error', '加载项目列表失败')
})
```

- [ ] **Step 5: 修复 `SkillsPage.tsx`**

在 import 区添加：

```typescript
import { useToastStore } from '@/stores/toastStore'
```

将 `catch (error) { console.error('Failed to load skills:', error) }` 改为：

```typescript
catch (error) {
  console.error('Failed to load skills:', error)
  useToastStore.getState().addToast('warning', '加载技能列表失败')
}
```

- [ ] **Step 6: 验证 TypeScript 编译**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: 无新增错误

- [ ] **Step 7: 运行前端测试**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npm run test`
Expected: 全部 PASS

- [ ] **Step 8: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add frontend/src/features/llm/useSettingsPageController.ts frontend/src/features/llm/llmSettingsLoader.ts frontend/src/hooks/useSessionData.ts frontend/src/components/layout/WorkspaceSidebar.tsx frontend/src/pages/SkillsPage.tsx
git commit -m "fix: add toast notifications for previously silent error catches"
```

---

## Task 12: 前端 — 更新 apiClient 解析 AppError 响应格式

**Files:**
- Modify: `frontend/src/services/apiClient.ts`
- Modify: `frontend/src/features/llm/providerActions.ts`

后端现在返回 `{"code": "...", "message": "...", "detail": {...}}` 格式而非 `{"detail": "..."}`，前端需要适配。

- [ ] **Step 1: 在 apiClient.ts 添加响应拦截器**

在 `apiClient` 创建之后添加拦截器，将新的错误格式映射为统一结构：

```typescript
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.data) {
      const data = error.response.data as Record<string, unknown>
      if (typeof data.message === 'string' && typeof data.code === 'string') {
        error.response.data = {
          ...data,
          detail: data.message,
        }
      }
    }
    return Promise.reject(error)
  }
)
```

这样后端新格式 `{code, message}` 会被自动映射为同时包含 `detail` 和 `message` 的格式，保证现有代码的 `error.response?.data?.detail` 继续工作。

- [ ] **Step 2: 更新 `providerActions.ts` 的 `getErrorMessage`**

将 `getErrorMessage` 更新为优先使用新的 `message` 字段：

```typescript
const getErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError<{ detail?: string; message?: string }>(error)) {
    return error.response?.data?.message || error.response?.data?.detail || fallback
  }
  return fallback
}
```

- [ ] **Step 3: 验证 TypeScript 编译**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: 无新增错误

- [ ] **Step 4: 运行前端测试**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npm run test`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS
git add frontend/src/services/apiClient.ts frontend/src/features/llm/providerActions.ts
git commit -m "feat: adapt frontend for AppError response format from backend"
```

---

## Task 13: 全链路验证

- [ ] **Step 1: 运行后端全部测试**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 2: 运行后端 lint**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/backend && python -m ruff check app/ tests/`
Expected: 无错误

- [ ] **Step 3: 运行前端全部测试**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npm run test`
Expected: 全部 PASS

- [ ] **Step 4: 运行前端 lint**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx eslint src/`
Expected: 无错误

- [ ] **Step 5: 验证 TypeScript 类型检查**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS/frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 6: 启动开发服务器进行手动验证**

Run: `cd /Users/munan/Documents/munan/my_project/ai/ReflexionOS && bash start-dev.sh`

手动验证场景：
1. 在设置页面故意输入错误的 API Key，点击"测试连接" → 应看到 toast 错误提示
2. 在聊天中发送消息，后端 LLM 重试耗尽 → transcript 中应显示红色错误框，包含具体错误原因
3. 取消正在执行的 run → transcript 中应显示琥珀色"执行已取消"提示
4. 断开后端服务，尝试操作 → 应看到 toast 提示"对话连接失败"
