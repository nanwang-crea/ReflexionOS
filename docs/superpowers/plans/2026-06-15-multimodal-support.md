# 多模态支持实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持用户在对话中上传图片，agent 可以分析图片内容

**Architecture:** 扩展 Message 和 LLMMessage 模型支持多模态内容，增加图片上传 API，改造 OpenAI adapter 支持 vision，添加模型能力检测和图片清理机制

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, OpenAI SDK, React, TypeScript

---

## 文件结构

### 后端新增文件
- `backend/app/llm/model_capabilities.py` - 模型视觉能力检测
- `backend/app/api/routes/upload.py` - 图片上传 API
- `backend/app/services/cleanup_service.py` - 图片清理服务
- `backend/tests/test_llm/test_model_capabilities.py` - 能力检测测试
- `backend/tests/test_api/test_upload.py` - 上传 API 测试

### 后端修改文件
- `backend/app/models/conversation.py` - Message 增加 attachments 字段
- `backend/app/llm/base.py` - LLMMessage 支持多模态 content
- `backend/app/llm/openai_adapter.py` - 支持多模态消息转换
- `backend/app/services/agent_service.py` - 启动时注册清理任务
- `backend/app/storage/models.py` - MessageModel 增加 attachments_json 列
- `backend/app/api/routes/__init__.py` - 注册 upload 路由

### 前端新增文件
- `frontend/src/features/conversation/useImageUpload.ts` - 图片上传 hook
- `frontend/src/features/conversation/ImagePreview.tsx` - 图片预览组件
- `frontend/src/features/conversation/ModelSwitchDialog.tsx` - 模型切换提示

### 前端修改文件
- `frontend/src/features/conversation/MessageComposer.tsx` - 支持图片粘贴
- `frontend/src/features/conversation/MessageBubble.tsx` - 显示图片附件

---

## Task 1: 模型视觉能力检测模块

**Files:**
- Create: `backend/app/llm/model_capabilities.py`
- Test: `backend/tests/test_llm/test_model_capabilities.py`

- [ ] **Step 1: 编写能力检测测试**

```python
# backend/tests/test_llm/test_model_capabilities.py
import pytest
from app.llm.model_capabilities import supports_vision


def test_supports_vision_exact_match():
    """测试精确匹配支持视觉的模型"""
    assert supports_vision("gpt-4o") is True
    assert supports_vision("gpt-4o-mini") is True
    assert supports_vision("claude-3-5-sonnet") is True
    assert supports_vision("gemini-1.5-pro") is True


def test_supports_vision_wildcard_match():
    """测试通配符匹配"""
    assert supports_vision("gpt-4o-2024-05-13") is True
    assert supports_vision("claude-3-opus-20240229") is True
    assert supports_vision("gemini-pro-vision") is True


def test_does_not_support_vision():
    """测试不支持视觉的模型"""
    assert supports_vision("gpt-3.5-turbo") is False
    assert supports_vision("gpt-4") is False
    assert supports_vision("claude-2") is False
    assert supports_vision("text-davinci-003") is False


def test_unknown_model():
    """测试未知模型默认不支持"""
    assert supports_vision("unknown-model") is False
    assert supports_vision("") is False
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend
pytest tests/test_llm/test_model_capabilities.py -v
```

Expected: FAIL - module not found

- [ ] **Step 3: 实现模型能力检测**

```python
# backend/app/llm/model_capabilities.py
"""模型能力检测模块"""

VISION_CAPABLE_MODELS = {
    # OpenAI
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4-vision-preview",
    
    # Anthropic Claude
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
    "claude-3-5-sonnet",
    "claude-fable-5",
    
    # Google Gemini
    "gemini-pro-vision",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    
    # 通配符模式
    "gpt-4o-*",
    "claude-3-*",
    "gemini-*-vision",
}


def supports_vision(model_name: str) -> bool:
    """检测模型是否支持视觉能力
    
    Args:
        model_name: 模型名称
        
    Returns:
        是否支持视觉
    """
    if not model_name:
        return False
    
    # 精确匹配
    if model_name in VISION_CAPABLE_MODELS:
        return True
    
    # 通配符匹配
    for pattern in VISION_CAPABLE_MODELS:
        if "*" in pattern:
            prefix = pattern.replace("*", "")
            if model_name.startswith(prefix):
                return True
    
    return False
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_llm/test_model_capabilities.py -v
```

Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/llm/model_capabilities.py backend/tests/test_llm/test_model_capabilities.py
git commit -m "feat: add model vision capability detection

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```


---

## Task 2: 扩展 LLMMessage 支持多模态

**Files:**
- Modify: `backend/app/llm/base.py:33-49`
- Test: `backend/tests/test_llm/test_base.py`

- [ ] **Step 1: 编写多模态 LLMMessage 测试**

Create `backend/tests/test_llm/test_base.py`:

```python
import pytest
from app.llm.base import LLMMessage, LLMContentPart


def test_llm_message_text_only():
    """测试纯文本消息"""
    msg = LLMMessage(role="user", content="Hello")
    assert msg.content == "Hello"
    assert msg.role == "user"


def test_llm_message_multimodal():
    """测试多模态消息"""
    msg = LLMMessage(
        role="user",
        content=[
            LLMContentPart(type="text", text="分析这张图片"),
            LLMContentPart(
                type="image_url",
                image_url={"url": "data:image/png;base64,abc123"}
            )
        ]
    )
    assert isinstance(msg.content, list)
    assert len(msg.content) == 2
    assert msg.content[0].type == "text"
    assert msg.content[1].type == "image_url"


def test_llm_content_part_text():
    """测试文本内容部分"""
    part = LLMContentPart(type="text", text="Hello")
    assert part.type == "text"
    assert part.text == "Hello"
    assert part.image_url is None


def test_llm_content_part_image():
    """测试图片内容部分"""
    part = LLMContentPart(
        type="image_url",
        image_url={"url": "data:image/png;base64,abc"}
    )
    assert part.type == "image_url"
    assert part.text is None
    assert part.image_url == {"url": "data:image/png;base64,abc"}
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_llm/test_base.py -v
```

Expected: FAIL - LLMContentPart not found

- [ ] **Step 3: 扩展 LLMMessage 模型**

```python
# backend/app/llm/base.py
# 在 LLMMessage 类之前添加 LLMContentPart

class LLMContentPart(BaseModel):
    """多模态内容部分"""
    type: str  # text, image_url
    text: str | None = None
    image_url: dict | None = None  # {"url": "data:image/png;base64,..."}


class LLMMessage(BaseModel):
    """统一的消息结构"""

    role: str
    content: str | list[LLMContentPart] | None = None  # 支持多模态
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"role": self.role}
        if self.content:
            if isinstance(self.content, str):
                result["content"] = self.content
            else:
                result["content"] = [part.model_dump(exclude_none=True) for part in self.content]
        if self.tool_calls:
            result["tool_calls"] = [tc.model_dump() for tc in self.tool_calls]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_llm/test_base.py -v
```

Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/llm/base.py backend/tests/test_llm/test_base.py
git commit -m "feat: extend LLMMessage to support multimodal content

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```


---

## Task 3: OpenAI Adapter 支持多模态转换

**Files:**
- Modify: `backend/app/llm/openai_adapter.py:258-285`
- Test: `backend/tests/test_llm/test_openai_adapter.py`

- [ ] **Step 1: 编写多模态转换测试**

Add to `backend/tests/test_llm/test_openai_adapter.py`:

```python
from app.llm.base import LLMMessage, LLMContentPart


def test_convert_multimodal_messages():
    """测试多模态消息转换"""
    from app.llm.openai_adapter import OpenAIAdapter
    from app.models.llm_config import ResolvedLLMConfig
    
    config = ResolvedLLMConfig(
        provider_id="openai",
        model="gpt-4o",
        api_key="test",
        base_url=None,
        temperature=0.7,
        max_tokens=4096,
        context_window=128000
    )
    adapter = OpenAIAdapter(config)
    
    messages = [
        LLMMessage(
            role="user",
            content=[
                LLMContentPart(type="text", text="分析这张图片"),
                LLMContentPart(
                    type="image_url",
                    image_url={"url": "data:image/png;base64,abc123"}
                )
            ]
        )
    ]
    
    converted = adapter._convert_messages(messages)
    
    assert len(converted) == 1
    assert converted[0]["role"] == "user"
    assert isinstance(converted[0]["content"], list)
    assert len(converted[0]["content"]) == 2
    assert converted[0]["content"][0]["type"] == "text"
    assert converted[0]["content"][0]["text"] == "分析这张图片"
    assert converted[0]["content"][1]["type"] == "image_url"
    assert converted[0]["content"][1]["image_url"]["url"] == "data:image/png;base64,abc123"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_llm/test_openai_adapter.py::test_convert_multimodal_messages -v
```

Expected: FAIL - multimodal content not converted

- [ ] **Step 3: 扩展 _convert_messages 方法**

```python
# backend/app/llm/openai_adapter.py
def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """将内部消息格式转换为 OpenAI 格式"""
    openai_messages = []

    for msg in messages:
        openai_msg: dict[str, Any] = {"role": msg.role}

        # 多模态内容
        if isinstance(msg.content, list):
            openai_msg["content"] = [
                self._convert_content_part(part) for part in msg.content
            ]
        elif msg.content is not None:
            openai_msg["content"] = msg.content
        elif msg.role == "tool":
            openai_msg["content"] = ""

        if msg.tool_calls:
            openai_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in msg.tool_calls
            ]

        if msg.tool_call_id:
            openai_msg["tool_call_id"] = msg.tool_call_id

        openai_messages.append(openai_msg)

    return openai_messages

def _convert_content_part(self, part) -> dict:
    """转换内容部分"""
    if part.type == "text":
        return {"type": "text", "text": part.text}
    elif part.type == "image_url":
        return {"type": "image_url", "image_url": part.image_url}
    else:
        raise ValueError(f"未知的内容类型: {part.type}")
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_llm/test_openai_adapter.py::test_convert_multimodal_messages -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/llm/openai_adapter.py backend/tests/test_llm/test_openai_adapter.py
git commit -m "feat: add multimodal message conversion to OpenAI adapter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```


---

## Task 4: 扩展 Message 模型支持附件

**Files:**
- Modify: `backend/app/models/conversation.py:95-110`
- Modify: `backend/app/storage/models.py:85-110`

- [ ] **Step 1: 扩展 Message Pydantic 模型**

```python
# backend/app/models/conversation.py
# 在 Message 类之前添加

class MessageAttachment(BaseModel):
    """消息附件"""
    id: str
    type: str  # image, file
    mime_type: str
    file_path: str
    file_size: int
    created_at: datetime = Field(default_factory=datetime.now)


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    turn_id: str
    run_id: str | None
    role: str
    content_text: str
    message_type: MessageType
    attachments: list[MessageAttachment] = Field(default_factory=list)  # 新增
    # ... 其他字段保持不变
```

- [ ] **Step 2: 扩展 MessageModel SQLAlchemy 模型**

```python
# backend/app/storage/models.py
# 在 MessageModel 类中添加字段

class MessageModel(Base):
    __tablename__ = "messages"

    # ... 现有字段
    attachments_json: Mapped[str | None] = mapped_column(Text, default=None)  # 新增：存储 JSON 字符串
```

- [ ] **Step 3: 创建数据库迁移脚本**

```python
# backend/alembic/versions/xxxx_add_message_attachments.py
"""add message attachments

Revision ID: xxxx
Revises: yyyy
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision = 'xxxx'
down_revision = 'yyyy'  # 替换为实际的前一个版本
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('messages', sa.Column('attachments_json', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('messages', 'attachments_json')
```

- [ ] **Step 4: 运行数据库迁移**

```bash
cd backend
alembic upgrade head
```

Expected: Migration applied successfully

- [ ] **Step 5: 提交**

```bash
git add backend/app/models/conversation.py backend/app/storage/models.py backend/alembic/versions/
git commit -m "feat: add attachments support to Message model

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```


---

## Task 5: 实现图片上传 API

**Files:**
- Create: `backend/app/api/routes/upload.py`
- Modify: `backend/app/api/routes/__init__.py`
- Test: `backend/tests/test_api/test_upload.py`

- [ ] **Step 1: 编写上传 API 测试**

```python
# backend/tests/test_api/test_upload.py
import pytest
from fastapi.testclient import TestClient
from io import BytesIO


def test_upload_image_success(client: TestClient, test_session_id: str):
    """测试成功上传图片"""
    # 创建一个简单的图片数据
    image_data = b"fake image content"
    files = {"file": ("test.png", BytesIO(image_data), "image/png")}
    
    response = client.post(
        f"/api/sessions/{test_session_id}/upload",
        files=files
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "attachment_id" in data
    assert "file_path" in data
    assert "file_size" in data
    assert data["file_size"] == len(image_data)


def test_upload_non_image_fails(client: TestClient, test_session_id: str):
    """测试上传非图片文件失败"""
    text_data = b"not an image"
    files = {"file": ("test.txt", BytesIO(text_data), "text/plain")}
    
    response = client.post(
        f"/api/sessions/{test_session_id}/upload",
        files=files
    )
    
    assert response.status_code == 400
    assert "只支持图片文件" in response.json()["detail"]


def test_upload_large_image_fails(client: TestClient, test_session_id: str):
    """测试上传超大图片失败"""
    large_data = b"x" * (11 * 1024 * 1024)  # 11MB
    files = {"file": ("large.png", BytesIO(large_data), "image/png")}
    
    response = client.post(
        f"/api/sessions/{test_session_id}/upload",
        files=files
    )
    
    assert response.status_code == 400
    assert "大小超过限制" in response.json()["detail"]
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_api/test_upload.py -v
```

Expected: FAIL - route not found

- [ ] **Step 3: 实现上传 API**

```python
# backend/app/api/routes/upload.py
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.storage.repositories.session_repo import SessionRepository
from app.storage.database import db

router = APIRouter()
session_repo = SessionRepository(db)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/sessions/{session_id}/upload")
async def upload_image(
    session_id: str,
    file: UploadFile = File(...),
) -> dict:
    """上传图片附件"""
    # 1. 验证 session 存在
    session = session_repo.get(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    
    # 2. 验证文件类型
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "只支持图片文件（PNG, JPG, WEBP）")
    
    # 3. 读取并验证文件大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"图片大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）")
    
    # 4. 保存文件
    upload_dir = Path("storage/uploads") / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    file_id = uuid.uuid4().hex[:8]
    file_ext = Path(file.filename).suffix if file.filename else ".png"
    file_path = upload_dir / f"{timestamp}_{file_id}{file_ext}"
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    # 5. 返回 attachment 信息
    return {
        "attachment_id": f"att_{file_id}",
        "file_path": str(file_path),
        "file_size": len(content),
        "mime_type": file.content_type
    }
```

- [ ] **Step 4: 注册路由**

```python
# backend/app/api/routes/__init__.py
# 添加导入和注册

from .upload import router as upload_router

# 在 app 中注册
app.include_router(upload_router, prefix="/api", tags=["upload"])
```

- [ ] **Step 5: 运行测试验证通过**

```bash
pytest tests/test_api/test_upload.py -v
```

Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/api/routes/upload.py backend/app/api/routes/__init__.py backend/tests/test_api/test_upload.py
git commit -m "feat: add image upload API

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```


---

## Task 6: 实现图片清理服务

**Files:**
- Create: `backend/app/services/cleanup_service.py`
- Modify: `backend/app/services/agent_service.py:320-328`
- Test: `backend/tests/test_services/test_cleanup_service.py`

- [ ] **Step 1: 编写清理服务测试**

```python
# backend/tests/test_services/test_cleanup_service.py
import pytest
from pathlib import Path
from datetime import datetime, timedelta
import time

from app.services.cleanup_service import CleanupService


@pytest.fixture
def temp_upload_dir(tmp_path):
    """创建临时上传目录"""
    upload_dir = tmp_path / "storage" / "uploads"
    upload_dir.mkdir(parents=True)
    return upload_dir


def test_cleanup_old_files(temp_upload_dir):
    """测试清理过期文件"""
    # 创建测试文件
    session_dir = temp_upload_dir / "test-session"
    session_dir.mkdir()
    
    # 旧文件（2天前）
    old_file = session_dir / "old.png"
    old_file.write_text("old")
    old_time = (datetime.now() - timedelta(days=2)).timestamp()
    Path(old_file).touch()
    import os
    os.utime(old_file, (old_time, old_time))
    
    # 新文件（现在）
    new_file = session_dir / "new.png"
    new_file.write_text("new")
    
    # 执行清理
    service = CleanupService(upload_root=str(temp_upload_dir))
    deleted = service.cleanup_old_uploads_sync(max_age_days=1)
    
    # 验证
    assert deleted == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_empty_directories(temp_upload_dir):
    """测试清理空目录"""
    empty_dir = temp_upload_dir / "empty-session"
    empty_dir.mkdir()
    
    service = CleanupService(upload_root=str(temp_upload_dir))
    service.cleanup_old_uploads_sync(max_age_days=1)
    
    assert not empty_dir.exists()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_services/test_cleanup_service.py -v
```

Expected: FAIL - module not found

- [ ] **Step 3: 实现清理服务**

```python
# backend/app/services/cleanup_service.py
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class CleanupService:
    """图片上传文件清理服务"""
    
    def __init__(self, upload_root: str = "storage/uploads"):
        self.upload_root = Path(upload_root)
    
    def cleanup_old_uploads_sync(self, max_age_days: int = 1) -> int:
        """同步清理超过指定天数的上传文件
        
        Args:
            max_age_days: 最大保留天数
            
        Returns:
            删除的文件数量
        """
        if not self.upload_root.exists():
            return 0
        
        cutoff = datetime.now() - timedelta(days=max_age_days)
        deleted_count = 0
        
        for session_dir in self.upload_root.iterdir():
            if not session_dir.is_dir():
                continue
            
            for file_path in session_dir.iterdir():
                if not file_path.is_file():
                    continue
                
                # 检查文件修改时间
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        logger.debug(f"删除过期文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"删除文件失败 {file_path}: {e}")
            
            # 删除空目录
            try:
                if not any(session_dir.iterdir()):
                    session_dir.rmdir()
                    logger.debug(f"删除空目录: {session_dir}")
            except Exception:
                pass
        
        if deleted_count > 0:
            logger.info(f"清理过期上传文件: {deleted_count} 个")
        
        return deleted_count
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_services/test_cleanup_service.py -v
```

Expected: ALL PASS

- [ ] **Step 5: 在 AgentService 中集成清理任务**

```python
# backend/app/services/agent_service.py
# 在 start_background_tasks 方法中添加

from app.services.cleanup_service import CleanupService

def start_background_tasks(
    self, cleanup_interval_seconds: int = _EVENT_CLEANUP_INTERVAL_SECONDS
) -> None:
    if self._cleanup_task is not None and not self._cleanup_task.done():
        return
    self._cleanup_task = asyncio.create_task(
        self._event_cleanup_loop(cleanup_interval_seconds),
        name="conversation-event-cleanup",
    )
    # 新增：启动图片清理任务
    self._upload_cleanup_task = asyncio.create_task(
        self._upload_cleanup_loop(),
        name="upload-cleanup",
    )

async def _upload_cleanup_loop(self):
    """图片清理循环"""
    cleanup_service = CleanupService()
    while True:
        try:
            await asyncio.to_thread(cleanup_service.cleanup_old_uploads_sync, max_age_days=1)
        except Exception:
            logger.exception("清理上传文件失败")
        await asyncio.sleep(3600)  # 每小时执行一次
```

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/cleanup_service.py backend/app/services/agent_service.py backend/tests/test_services/test_cleanup_service.py
git commit -m "feat: add upload file cleanup service

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```


---

## 验证和测试

- [ ] **集成测试：完整流程**

```bash
# 1. 启动后端
cd backend
python -m uvicorn app.main:app --reload

# 2. 测试上传图片
curl -X POST http://localhost:8000/api/sessions/{session_id}/upload \
  -F "file=@test_image.png"

# 3. 验证文件存在
ls storage/uploads/{session_id}/

# 4. 验证模型能力检测
python -c "from app.llm.model_capabilities import supports_vision; print(supports_vision('gpt-4o'))"

# 5. 运行所有测试
pytest tests/ -v --cov=app
```

- [ ] **手动测试清单**
  - [ ] 上传 PNG 图片
  - [ ] 上传 JPG 图片
  - [ ] 上传超大图片（应失败）
  - [ ] 上传非图片文件（应失败）
  - [ ] 等待 1 天后验证文件自动清理
  - [ ] 删除 session 后验证图片目录清理

---

## 实现计划自审

### 1. 规格覆盖检查
- ✅ 模型视觉能力检测 - Task 1
- ✅ LLMMessage 多模态支持 - Task 2
- ✅ OpenAI adapter 多模态转换 - Task 3
- ✅ Message 模型附件支持 - Task 4
- ✅ 图片上传 API - Task 5
- ✅ 图片清理服务 - Task 6
- ⏸️ 前端集成 - 待后续补充（非本次后端实现范围）
- ⏸️ 模型不支持时的错误处理 - 待集成到消息发送流程

### 2. Placeholder 扫描
- 无 TBD 或 TODO
- 所有代码块完整
- 所有测试用例具体

### 3. 类型一致性
- MessageAttachment: id, type, mime_type, file_path, file_size
- LLMContentPart: type, text, image_url
- 所有任务中使用的类型定义一致

### 4. 遗漏检查
所有后端核心功能已覆盖。前端部分和消息发送流程集成将在后续 Phase 补充。

---

## 注意事项

1. **数据库迁移**：Task 4 需要手动调整 revision ID
2. **路由注册**：Task 5 需要根据实际的 `__init__.py` 结构调整注册方式
3. **测试依赖**：某些测试需要 test fixtures (如 `test_session_id`, `client`)
4. **存储目录**：确保 `storage/uploads/` 目录有写权限
5. **清理任务**：首次启动后 1 小时才会执行清理

---

## 后续 Phase

### Phase 2: 前端集成
- 图片粘贴和上传 UI
- 图片预览组件
- 模型切换提示对话框
- 消息气泡中显示图片

### Phase 3: 消息发送集成
- 在消息创建时关联 attachments
- 构建 LLM 请求时转换附件为 LLMContentPart
- 模型不支持时的友好错误提示
- 图片 base64 编码和传输优化

---

## 参考资料

- OpenAI Vision API: https://platform.openai.com/docs/guides/vision
- FastAPI File Upload: https://fastapi.tiangolo.com/tutorial/request-files/
- SQLAlchemy JSON: https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.JSON
- Pydantic Models: https://docs.pydantic.dev/latest/

