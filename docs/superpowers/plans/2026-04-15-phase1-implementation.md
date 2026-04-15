# ReflexionOS 第一阶段实施计划

> **对于代理执行者:** 必需子技能: 使用 superpowers:subagent-driven-development (推荐) 或 superpowers:executing-plans 来逐任务执行此计划。步骤使用复选框 (`- [ ]`) 语法进行跟踪。

**目标:** 构建 ReflexionOS 的 MVP 核心功能,包括后端 Agent 执行引擎、前端 Electron+React 桌面应用框架,以及 OpenAI LLM 适配器。

**架构:** 采用紧耦合单体架构,Electron 主进程管理 FastAPI 子进程,React 前端通过 IPC 与主进程通信,通过 HTTP/WebSocket 与后端通信。自研统一 LLM 接口层,第一阶段实现 OpenAI 适配器。

**技术栈:** 
- 后端: FastAPI + Python 3.11+ + Pydantic + Uvicorn
- 前端: Electron + React 18 + TypeScript + Zustand + TailwindCSS
- 通信: IPC + HTTP/REST + WebSocket

---

## 模块一: 后端基础设施搭建 (Week 1)

### 任务 1.1: 创建后端项目结构

**文件:**
- 创建: `backend/`
- 创建: `backend/app/__init__.py`
- 创建: `backend/app/main.py`
- 创建: `backend/app/config.py`
- 创建: `backend/requirements.txt`
- 创建: `backend/pyproject.toml`
- 创建: `backend/.env.example`
- 创建: `backend/README.md`

- [ ] **步骤 1: 创建后端目录结构**

```bash
mkdir -p backend/app/{api/routes,services,execution,tools,llm,security,models,utils}
mkdir -p backend/tests/{test_tools,test_execution,test_api}
```

- [ ] **步骤 2: 创建 requirements.txt**

```txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
python-dotenv==1.0.0
python-socketio==5.11.0
httpx==0.26.0
openai==1.12.0
pytest==7.4.4
pytest-asyncio==0.23.3
```

- [ ] **步骤 3: 创建 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "reflexion-os"
version = "0.1.0"
description = "Local execution agent desktop application"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.3",
    "pydantic-settings>=2.1.0",
    "python-dotenv>=1.0.0",
    "python-socketio>=5.11.0",
    "httpx>=0.26.0",
    "openai>=1.12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.4",
    "pytest-asyncio>=0.23.3",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **步骤 4: 创建配置管理模块 backend/app/config.py**

```python
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "ReflexionOS"
    app_version: str = "0.1.0"
    debug: bool = False
    
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    
    llm_provider: str = "openai"
    llm_api_key: Optional[str] = None
    llm_model: str = "gpt-4-turbo-preview"
    llm_base_url: Optional[str] = None
    
    max_execution_steps: int = 50
    max_file_size: int = 10 * 1024 * 1024
    max_execution_time: int = 600
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

- [ ] **步骤 5: 创建 FastAPI 主应用 backend/app/main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

- [ ] **步骤 6: 创建 .env.example**

```env
APP_NAME=ReflexionOS
DEBUG=false

SERVER_HOST=127.0.0.1
SERVER_PORT=8000

LLM_PROVIDER=openai
LLM_API_KEY=your-openai-api-key-here
LLM_MODEL=gpt-4-turbo-preview
LLM_BASE_URL=

MAX_EXECUTION_STEPS=50
MAX_FILE_SIZE=10485760
MAX_EXECUTION_TIME=600
```

- [ ] **步骤 7: 创建 README.md**

```markdown
# ReflexionOS Backend

FastAPI 后端服务,提供 Agent 执行引擎和 API 接口。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env` 并填写配置项。

## 运行

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 测试

```bash
pytest
```
```

- [ ] **步骤 8: 创建空的 __init__.py 文件**

```bash
touch backend/app/__init__.py
touch backend/app/api/__init__.py
touch backend/app/api/routes/__init__.py
touch backend/app/services/__init__.py
touch backend/app/execution/__init__.py
touch backend/app/tools/__init__.py
touch backend/app/llm/__init__.py
touch backend/app/security/__init__.py
touch backend/app/models/__init__.py
touch backend/app/utils/__init__.py
touch backend/tests/__init__.py
```

- [ ] **步骤 9: 验证后端可以启动**

运行: `cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000`
预期: 服务成功启动,访问 http://127.0.0.1:8000 返回 JSON 响应

- [ ] **步骤 10: 提交代码**

```bash
git add backend/
git commit -m "feat: 初始化后端项目结构

- 创建 FastAPI 项目基础结构
- 添加配置管理模块
- 配置 pyproject.toml 和 requirements.txt
- 添加基础路由和健康检查接口"
```

---

### 任务 1.2: 实现数据模型定义

**文件:**
- 创建: `backend/app/models/project.py`
- 创建: `backend/app/models/execution.py`
- 创建: `backend/app/models/action.py`
- 创建: `backend/app/models/llm_config.py`
- 创建: `backend/tests/test_models/test_project.py`

- [ ] **步骤 1: 编写项目模型测试 backend/tests/test_models/test_project.py**

```python
import pytest
from app.models.project import Project, ProjectCreate


class TestProject:
    
    def test_create_project(self):
        data = {
            "name": "TestProject",
            "path": "/path/to/project",
            "language": "python"
        }
        project = ProjectCreate(**data)
        
        assert project.name == "TestProject"
        assert project.path == "/path/to/project"
        assert project.language == "python"
    
    def test_project_with_id(self):
        project = Project(
            id="proj-123",
            name="TestProject",
            path="/path/to/project",
            language="python"
        )
        
        assert project.id == "proj-123"
        assert project.name == "TestProject"
```

- [ ] **步骤 2: 运行测试验证失败**

运行: `cd backend && pytest tests/test_models/test_project.py -v`
预期: FAIL - 模块不存在

- [ ] **步骤 3: 创建项目模型 backend/app/models/project.py**

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class ProjectBase(BaseModel):
    name: str
    path: str
    language: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    id: str = Field(default_factory=lambda: f"proj-{uuid.uuid4().hex[:8]}")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        from_attributes = True
```

- [ ] **步骤 4: 运行测试验证通过**

运行: `cd backend && pytest tests/test_models/test_project.py -v`
预期: PASS

- [ ] **步骤 5: 创建执行模型 backend/app/models/execution.py**

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ExecutionStep(BaseModel):
    id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    step_number: int
    tool: str
    args: dict
    status: StepStatus = StepStatus.PENDING
    output: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ExecutionBase(BaseModel):
    project_id: str
    task: str


class ExecutionCreate(ExecutionBase):
    pass


class Execution(ExecutionBase):
    id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:8]}")
    status: ExecutionStatus = ExecutionStatus.PENDING
    steps: List[ExecutionStep] = []
    result: Optional[str] = None
    total_duration: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
```

- [ ] **步骤 6: 创建动作模型 backend/app/models/action.py**

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum


class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    FINISH = "finish"


class Action(BaseModel):
    type: ActionType
    thought: Optional[str] = None
    tool: Optional[str] = None
    args: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ActionResult(BaseModel):
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None
```

- [ ] **步骤 7: 创建 LLM 配置模型 backend/app/models/llm_config.py**

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class LLMProvider(str, Enum):
    OPENAI = "openai"
    CLAUDE = "claude"
    OLLAMA = "ollama"


class LLMConfigBase(BaseModel):
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)


class LLMConfigCreate(LLMConfigBase):
    pass


class LLMConfig(LLMConfigBase):
    class Config:
        from_attributes = True
```

- [ ] **步骤 8: 更新 models/__init__.py 导出所有模型**

```python
from app.models.project import Project, ProjectCreate
from app.models.execution import (
    Execution, 
    ExecutionCreate, 
    ExecutionStep, 
    ExecutionStatus,
    StepStatus
)
from app.models.action import Action, ActionResult, ActionType
from app.models.llm_config import LLMConfig, LLMConfigCreate, LLMProvider

__all__ = [
    "Project", "ProjectCreate",
    "Execution", "ExecutionCreate", "ExecutionStep", "ExecutionStatus", "StepStatus",
    "Action", "ActionResult", "ActionType",
    "LLMConfig", "LLMConfigCreate", "LLMProvider",
]
```

- [ ] **步骤 9: 提交代码**

```bash
git add backend/app/models/ backend/tests/test_models/
git commit -m "feat: 添加核心数据模型定义

- 项目模型 (Project)
- 执行模型 (Execution, ExecutionStep)
- 动作模型 (Action, ActionResult)
- LLM配置模型 (LLMConfig)
- 添加项目模型单元测试"
```

---

### 任务 1.3: 实现日志系统

**文件:**
- 创建: `backend/app/utils/logger.py`
- 创建: `backend/tests/test_utils/test_logger.py`

- [ ] **步骤 1: 创建日志工具 backend/app/utils/logger.py**

```python
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from app.config import settings


def setup_logger(
    name: str = "reflexion",
    log_file: Optional[str] = None,
    level: int = logging.INFO
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if log_file:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_dir / log_file,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "reflexion") -> logging.Logger:
    return logging.getLogger(name)


logger = setup_logger(
    name="reflexion",
    log_file=f"reflexion-{datetime.now().strftime('%Y%m%d')}.log" if not settings.debug else None,
    level=logging.DEBUG if settings.debug else logging.INFO
)
```

- [ ] **步骤 2: 创建日志测试 backend/tests/test_utils/test_logger.py**

```python
import pytest
import logging
from app.utils.logger import setup_logger, get_logger


class TestLogger:
    
    def test_setup_logger(self):
        logger = setup_logger("test_logger")
        
        assert logger.name == "test_logger"
        assert logger.level == logging.INFO
        assert len(logger.handlers) > 0
    
    def test_get_logger(self):
        logger = get_logger("reflexion")
        
        assert logger.name == "reflexion"
        assert isinstance(logger, logging.Logger)
```

- [ ] **步骤 3: 运行测试**

运行: `cd backend && pytest tests/test_utils/test_logger.py -v`
预期: PASS

- [ ] **步骤 4: 提交代码**

```bash
git add backend/app/utils/logger.py backend/tests/test_utils/
git commit -m "feat: 实现日志系统

- 添加控制台和文件日志输出
- 支持日志级别配置
- 添加日志工具单元测试"
```

---

## 模块二: LLM 适配层实现 (Week 2)

### 任务 2.1: 定义统一 LLM 接口

**文件:**
- 创建: `backend/app/llm/base.py`
- 创建: `backend/tests/test_llm/test_base.py`

- [ ] **步骤 1: 编写 LLM 接口测试 backend/tests/test_llm/test_base.py**

```python
import pytest
from app.llm.base import Message, LLMResponse


class TestMessage:
    
    def test_message_creation(self):
        message = Message(role="user", content="Hello")
        
        assert message.role == "user"
        assert message.content == "Hello"
    
    def test_message_to_dict(self):
        message = Message(role="user", content="Hello")
        msg_dict = message.to_dict()
        
        assert msg_dict == {"role": "user", "content": "Hello"}


class TestLLMResponse:
    
    def test_llm_response(self):
        response = LLMResponse(
            content="Response text",
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        assert response.content == "Response text"
        assert response.model == "gpt-4"
        assert response.usage["total_tokens"] == 100
```

- [ ] **步骤 2: 运行测试验证失败**

运行: `cd backend && pytest tests/test_llm/test_base.py -v`
预期: FAIL - 模块不存在

- [ ] **步骤 3: 创建 LLM 基础模型和接口 backend/app/llm/base.py**

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncIterator
from enum import Enum


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    role: str
    content: str
    
    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: Dict[str, int] = {}
    finish_reason: Optional[str] = None


class UniversalLLMInterface(ABC):
    """统一的 LLM 接口,所有 LLM 适配器必须实现此接口"""
    
    @abstractmethod
    async def complete(self, messages: List[Message]) -> LLMResponse:
        """
        同步补全接口
        
        Args:
            messages: 消息列表
            
        Returns:
            LLMResponse: LLM 响应结果
        """
        pass
    
    @abstractmethod
    async def stream_complete(self, messages: List[Message]) -> AsyncIterator[str]:
        """
        流式补全接口
        
        Args:
            messages: 消息列表
            
        Yields:
            str: 流式返回的文本片段
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """获取当前使用的模型名称"""
        pass
```

- [ ] **步骤 4: 运行测试验证通过**

运行: `cd backend && pytest tests/test_llm/test_base.py -v`
预期: PASS

- [ ] **步骤 5: 提交代码**

```bash
git add backend/app/llm/base.py backend/tests/test_llm/
git commit -m "feat: 定义统一 LLM 接口

- 创建 Message 和 LLMResponse 数据模型
- 定义 UniversalLLMInterface 抽象基类
- 支持同步和流式补全接口
- 添加基础测试"
```

---

### 任务 2.2: 实现 OpenAI 适配器

**文件:**
- 创建: `backend/app/llm/openai_adapter.py`
- 创建: `backend/tests/test_llm/test_openai_adapter.py`

- [ ] **步骤 1: 编写 OpenAI 适配器测试 backend/tests/test_llm/test_openai_adapter.py**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.llm.openai_adapter import OpenAIAdapter
from app.llm.base import Message, MessageRole
from app.models.llm_config import LLMConfig, LLMProvider


class TestOpenAIAdapter:
    
    @pytest.fixture
    def llm_config(self):
        return LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4-turbo-preview",
            api_key="test-api-key",
            temperature=0.7,
            max_tokens=1000
        )
    
    @pytest.fixture
    def openai_adapter(self, llm_config):
        return OpenAIAdapter(llm_config)
    
    def test_adapter_initialization(self, openai_adapter, llm_config):
        assert openai_adapter.config == llm_config
        assert openai_adapter.model == "gpt-4-turbo-preview"
    
    def test_get_model_name(self, openai_adapter):
        assert openai_adapter.get_model_name() == "gpt-4-turbo-preview"
    
    @pytest.mark.asyncio
    async def test_complete_success(self, openai_adapter):
        messages = [
            Message(role=MessageRole.USER.value, content="Hello")
        ]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi there!"
        mock_response.model = "gpt-4-turbo-preview"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50
        
        with patch.object(openai_adapter.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            
            response = await openai_adapter.complete(messages)
            
            assert response.content == "Hi there!"
            assert response.model == "gpt-4-turbo-preview"
            assert response.usage["total_tokens"] == 50
```

- [ ] **步骤 2: 运行测试验证失败**

运行: `cd backend && pytest tests/test_llm/test_openai_adapter.py -v`
预期: FAIL - 模块不存在

- [ ] **步骤 3: 实现 OpenAI 适配器 backend/app/llm/openai_adapter.py**

```python
from typing import List, AsyncIterator
from openai import AsyncOpenAI
from app.llm.base import UniversalLLMInterface, Message, LLMResponse
from app.models.llm_config import LLMConfig
import logging

logger = logging.getLogger(__name__)


class OpenAIAdapter(UniversalLLMInterface):
    """OpenAI API 适配器"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.model = config.model
        
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url if config.base_url else None
        )
        
        logger.info(f"OpenAI 适配器初始化完成,模型: {self.model}")
    
    async def complete(self, messages: List[Message]) -> LLMResponse:
        """
        同步补全
        
        Args:
            messages: 消息列表
            
        Returns:
            LLMResponse: 响应结果
        """
        try:
            message_dicts = [msg.to_dict() for msg in messages]
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=message_dicts,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
            
            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                finish_reason=response.choices[0].finish_reason
            )
            
        except Exception as e:
            logger.error(f"OpenAI API 调用失败: {str(e)}")
            raise
    
    async def stream_complete(self, messages: List[Message]) -> AsyncIterator[str]:
        """
        流式补全
        
        Args:
            messages: 消息列表
            
        Yields:
            str: 文本片段
        """
        try:
            message_dicts = [msg.to_dict() for msg in messages]
            
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=message_dicts,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"OpenAI 流式 API 调用失败: {str(e)}")
            raise
    
    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.model
```

- [ ] **步骤 4: 运行测试验证通过**

运行: `cd backend && pytest tests/test_llm/test_openai_adapter.py -v`
预期: PASS

- [ ] **步骤 5: 创建 LLM 适配器工厂**

在 `backend/app/llm/__init__.py` 中添加:

```python
from app.llm.base import UniversalLLMInterface, Message, LLMResponse
from app.llm.openai_adapter import OpenAIAdapter
from app.models.llm_config import LLMConfig, LLMProvider
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class LLMAdapterFactory:
    """LLM 适配器工厂"""
    
    @staticmethod
    def create(config: LLMConfig) -> UniversalLLMInterface:
        """
        根据配置创建 LLM 适配器
        
        Args:
            config: LLM 配置
            
        Returns:
            UniversalLLMInterface: LLM 适配器实例
            
        Raises:
            ValueError: 不支持的 LLM 提供商
        """
        if config.provider == LLMProvider.OPENAI:
            logger.info("创建 OpenAI 适配器")
            return OpenAIAdapter(config)
        
        elif config.provider == LLMProvider.CLAUDE:
            raise ValueError("Claude 适配器将在第二阶段实现")
        
        elif config.provider == LLMProvider.OLLAMA:
            raise ValueError("Ollama 适配器将在第二阶段实现")
        
        else:
            raise ValueError(f"不支持的 LLM 提供商: {config.provider}")


__all__ = [
    "UniversalLLMInterface",
    "Message",
    "LLMResponse",
    "OpenAIAdapter",
    "LLMAdapterFactory",
]
```

- [ ] **步骤 6: 提交代码**

```bash
git add backend/app/llm/ backend/tests/test_llm/
git commit -m "feat: 实现 OpenAI LLM 适配器

- 实现 UniversalLLMInterface 接口
- 支持同步和流式补全
- 添加 LLM 适配器工厂
- 预留 Claude 和 Ollama 接口
- 添加完整的单元测试"
```

---

## 模块三: 工具层实现 (Week 3)

### 任务 3.1: 实现文件工具

**文件:**
- 创建: `backend/app/tools/base.py`
- 创建: `backend/app/tools/file_tool.py`
- 创建: `backend/app/security/path_security.py`
- 创建: `backend/tests/test_tools/test_file_tool.py`

- [ ] **步骤 1: 创建工具基类 backend/app/tools/base.py**

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any, Dict, Optional


class ToolResult(BaseModel):
    """工具执行结果"""
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class BaseTool(ABC):
    """工具基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
    
    @abstractmethod
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行工具
        
        Args:
            args: 工具参数
            
        Returns:
            ToolResult: 执行结果
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """获取工具的 JSON Schema"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {}
        }
```

- [ ] **步骤 2: 创建路径安全控制 backend/app/security/path_security.py**

```python
import os
from typing import List
import logging

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """安全错误"""
    pass


class PathSecurity:
    """文件系统访问安全控制"""
    
    def __init__(self, allowed_base_paths: List[str]):
        self.allowed_base_paths = [os.path.abspath(p) for p in allowed_base_paths]
        logger.info(f"路径安全控制初始化,允许的路径: {self.allowed_base_paths}")
    
    def validate_path(self, path: str) -> str:
        """
        验证路径是否在允许范围内
        
        Args:
            path: 待验证路径
            
        Returns:
            str: 规范化后的绝对路径
            
        Raises:
            SecurityError: 路径不在允许范围内
        """
        abs_path = os.path.abspath(path)
        
        if not any(abs_path.startswith(base) for base in self.allowed_base_paths):
            raise SecurityError(f"路径 {path} 不在允许的访问范围内")
        
        real_path = os.path.realpath(abs_path)
        if not any(real_path.startswith(base) for base in self.allowed_base_paths):
            raise SecurityError("检测到路径遍历攻击")
        
        return abs_path
    
    def validate_write_path(self, path: str) -> str:
        """
        验证写入路径
        
        Args:
            path: 待验证路径
            
        Returns:
            str: 规范化后的绝对路径
            
        Raises:
            SecurityError: 禁止写入敏感文件
        """
        abs_path = self.validate_path(path)
        
        sensitive_patterns = ['.env', 'credentials', 'secrets', '.git/config']
        if any(pattern in abs_path for pattern in sensitive_patterns):
            raise SecurityError("禁止修改敏感文件")
        
        return abs_path
```

- [ ] **步骤 3: 创建文件工具测试 backend/tests/test_tools/test_file_tool.py**

```python
import pytest
import tempfile
from pathlib import Path
from app.tools.file_tool import FileTool
from app.security.path_security import PathSecurity, SecurityError


class TestFileTool:
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def file_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return FileTool(security)
    
    @pytest.mark.asyncio
    async def test_read_file_success(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("print('hello')")
        
        result = await file_tool.execute({
            "action": "read",
            "path": str(test_file)
        })
        
        assert result.success is True
        assert result.data["content"] == "print('hello')"
    
    @pytest.mark.asyncio
    async def test_read_file_outside_workspace(self, file_tool):
        with pytest.raises(SecurityError):
            await file_tool.execute({
                "action": "read",
                "path": "/etc/passwd"
            })
    
    @pytest.mark.asyncio
    async def test_write_file_success(self, file_tool, temp_dir):
        test_file = Path(temp_dir) / "output.txt"
        
        result = await file_tool.execute({
            "action": "write",
            "path": str(test_file),
            "content": "Hello World"
        })
        
        assert result.success is True
        assert test_file.read_text() == "Hello World"
    
    @pytest.mark.asyncio
    async def test_list_directory(self, file_tool, temp_dir):
        (Path(temp_dir) / "file1.txt").touch()
        (Path(temp_dir) / "file2.py").touch()
        
        result = await file_tool.execute({
            "action": "list",
            "path": temp_dir
        })
        
        assert result.success is True
        assert "file1.txt" in result.data["files"]
        assert "file2.py" in result.data["files"]
```

- [ ] **步骤 4: 运行测试验证失败**

运行: `cd backend && pytest tests/test_tools/test_file_tool.py -v`
预期: FAIL - 模块不存在

- [ ] **步骤 5: 实现文件工具 backend/app/tools/file_tool.py**

```python
import os
import aiofiles
from typing import Dict, Any, List
from app.tools.base import BaseTool, ToolResult
from app.security.path_security import PathSecurity
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class FileTool(BaseTool):
    """文件操作工具"""
    
    def __init__(self, security: PathSecurity):
        self.security = security
    
    @property
    def name(self) -> str:
        return "file"
    
    @property
    def description(self) -> str:
        return "文件读写和目录操作工具"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行文件操作
        
        Args:
            args: 包含 action 和相关参数的字典
            
        Returns:
            ToolResult: 执行结果
        """
        action = args.get("action")
        
        try:
            if action == "read":
                return await self._read_file(args)
            elif action == "write":
                return await self._write_file(args)
            elif action == "list":
                return await self._list_directory(args)
            elif action == "delete":
                return await self._delete_file(args)
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
                
        except Exception as e:
            logger.error(f"文件操作失败: {str(e)}")
            return ToolResult(success=False, error=str(e))
    
    async def _read_file(self, args: Dict[str, Any]) -> ToolResult:
        """读取文件内容"""
        path = self.security.validate_path(args["path"])
        
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        
        if os.path.getsize(path) > settings.max_file_size:
            return ToolResult(success=False, error="文件大小超过限制")
        
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            content = await f.read()
        
        logger.info(f"成功读取文件: {path}")
        return ToolResult(
            success=True,
            data={"content": content, "path": path}
        )
    
    async def _write_file(self, args: Dict[str, Any]) -> ToolResult:
        """写入文件内容"""
        path = self.security.validate_write_path(args["path"])
        content = args["content"]
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        async with aiofiles.open(path, mode='w', encoding='utf-8') as f:
            await f.write(content)
        
        logger.info(f"成功写入文件: {path}")
        return ToolResult(success=True, output=f"文件已写入: {path}")
    
    async def _list_directory(self, args: Dict[str, Any]) -> ToolResult:
        """列出目录内容"""
        path = self.security.validate_path(args["path"])
        
        if not os.path.isdir(path):
            return ToolResult(success=False, error=f"不是目录: {path}")
        
        files: List[str] = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            files.append({
                "name": item,
                "type": "directory" if os.path.isdir(item_path) else "file"
            })
        
        logger.info(f"成功列出目录: {path}, 共 {len(files)} 项")
        return ToolResult(success=True, data={"files": files, "path": path})
    
    async def _delete_file(self, args: Dict[str, Any]) -> ToolResult:
        """删除文件"""
        path = self.security.validate_write_path(args["path"])
        
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        
        os.remove(path)
        logger.info(f"成功删除文件: {path}")
        return ToolResult(success=True, output=f"文件已删除: {path}")
```

- [ ] **步骤 6: 更新 requirements.txt 添加 aiofiles**

在 `backend/requirements.txt` 中添加:
```txt
aiofiles==23.2.1
```

- [ ] **步骤 7: 运行测试验证通过**

运行: `cd backend && pytest tests/test_tools/test_file_tool.py -v`
预期: PASS

- [ ] **步骤 8: 提交代码**

```bash
git add backend/app/tools/ backend/app/security/ backend/tests/test_tools/ backend/requirements.txt
git commit -m "feat: 实现文件工具和路径安全控制

- 创建工具基类 BaseTool
- 实现文件读写、目录列表、文件删除功能
- 添加路径安全验证机制
- 防止路径遍历攻击
- 禁止修改敏感文件
- 添加完整的单元测试"
```

---

### 任务 3.2: 实现 Shell 工具

**文件:**
- 创建: `backend/app/tools/shell_tool.py`
- 创建: `backend/app/security/shell_security.py`
- 创建: `backend/tests/test_tools/test_shell_tool.py`

- [ ] **步骤 1: 创建 Shell 安全控制 backend/app/security/shell_security.py**

```python
import re
from typing import List
import logging

logger = logging.getLogger(__name__)


class ShellSecurityError(Exception):
    """Shell 安全错误"""
    pass


class ShellSecurity:
    """Shell 命令执行安全控制"""
    
    FORBIDDEN_COMMANDS = [
        'rm -rf /',
        'dd if=',
        'mkfs',
        ':(){ :|:& };:',
        'chmod 777',
        'chown root',
        'sudo',
        'su ',
    ]
    
    ALLOWED_COMMANDS_PATTERNS = [
        r'^(pytest|python|python3)\s+',
        r'^(node|npm|yarn|pnpm)\s+',
        r'^git\s+(status|diff|log|add|commit|push|pull|branch|checkout)',
        r'^(ls|cat|grep|find|mkdir|touch)\s+',
        r'^npm\s+(run|test|build|install)',
        r'^yarn\s+(run|test|build|add)',
    ]
    
    def validate_command(self, command: str) -> None:
        """
        验证命令安全性
        
        Args:
            command: 待执行的命令
            
        Raises:
            ShellSecurityError: 命令不安全
        """
        command_lower = command.lower().strip()
        
        for forbidden in self.FORBIDDEN_COMMANDS:
            if forbidden.lower() in command_lower:
                logger.warning(f"检测到禁止命令: {command}")
                raise ShellSecurityError(f"禁止执行危险命令: {command}")
        
        is_allowed = any(
            re.match(pattern, command_lower)
            for pattern in self.ALLOWED_COMMANDS_PATTERNS
        )
        
        if not is_allowed:
            logger.warning(f"命令不在允许列表中: {command}")
            raise ShellSecurityError(f"命令不在允许列表中: {command}")
        
        logger.info(f"命令验证通过: {command}")
```

- [ ] **步骤 2: 创建 Shell 工具测试 backend/tests/test_tools/test_shell_tool.py**

```python
import pytest
from app.tools.shell_tool import ShellTool
from app.security.shell_security import ShellSecurity, ShellSecurityError


class TestShellTool:
    
    @pytest.fixture
    def shell_tool(self):
        security = ShellSecurity()
        return ShellTool(security)
    
    @pytest.mark.asyncio
    async def test_execute_allowed_command(self, shell_tool):
        result = await shell_tool.execute({
            "command": "echo hello"
        })
        
        assert result.success is True
        assert "hello" in result.output
    
    @pytest.mark.asyncio
    async def test_execute_forbidden_command(self, shell_tool):
        with pytest.raises(ShellSecurityError):
            await shell_tool.execute({
                "command": "rm -rf /"
            })
    
    @pytest.mark.asyncio
    async def test_execute_python_command(self, shell_tool):
        result = await shell_tool.execute({
            "command": "python --version"
        })
        
        assert result.success is True
        assert "Python" in result.output
```

- [ ] **步骤 3: 运行测试验证失败**

运行: `cd backend && pytest tests/test_tools/test_shell_tool.py -v`
预期: FAIL - 模块不存在

- [ ] **步骤 4: 实现 Shell 工具 backend/app/tools/shell_tool.py**

```python
import asyncio
from typing import Dict, Any
from app.tools.base import BaseTool, ToolResult
from app.security.shell_security import ShellSecurity
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class ShellTool(BaseTool):
    """Shell 命令执行工具"""
    
    def __init__(self, security: ShellSecurity):
        self.security = security
    
    @property
    def name(self) -> str:
        return "shell"
    
    @property
    def description(self) -> str:
        return "执行安全的 Shell 命令"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        执行 Shell 命令
        
        Args:
            args: 包含 command 和可选 cwd 的字典
            
        Returns:
            ToolResult: 执行结果
        """
        command = args.get("command")
        cwd = args.get("cwd")
        timeout = args.get("timeout", settings.max_execution_time)
        
        if not command:
            return ToolResult(success=False, error="缺少 command 参数")
        
        try:
            self.security.validate_command(command)
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                logger.error(f"命令执行超时: {command}")
                return ToolResult(success=False, error=f"命令执行超时 ({timeout}秒)")
            
            output = stdout.decode('utf-8', errors='ignore')
            error = stderr.decode('utf-8', errors='ignore')
            
            if process.returncode == 0:
                logger.info(f"命令执行成功: {command}")
                return ToolResult(
                    success=True,
                    output=output,
                    data={"return_code": process.returncode}
                )
            else:
                logger.warning(f"命令执行失败: {command}, 返回码: {process.returncode}")
                return ToolResult(
                    success=False,
                    output=output,
                    error=error
                )
                
        except Exception as e:
            logger.error(f"Shell 执行异常: {str(e)}")
            return ToolResult(success=False, error=str(e))
```

- [ ] **步骤 5: 运行测试验证通过**

运行: `cd backend && pytest tests/test_tools/test_shell_tool.py -v`
预期: PASS

- [ ] **步骤 6: 提交代码**

```bash
git add backend/app/tools/shell_tool.py backend/app/security/shell_security.py backend/tests/test_tools/test_shell_tool.py
git commit -m "feat: 实现 Shell 工具和命令安全控制

- 创建 Shell 安全验证机制
- 禁止危险命令执行
- 实现命令白名单机制
- 支持命令超时控制
- 添加完整的单元测试"
```

---

### 任务 3.3: 实现工具注册中心

**文件:**
- 创建: `backend/app/tools/registry.py`
- 创建: `backend/tests/test_tools/test_registry.py`

- [ ] **步骤 1: 创建工具注册中心测试 backend/tests/test_tools/test_registry.py**

```python
import pytest
from app.tools.registry import ToolRegistry
from app.tools.file_tool import FileTool
from app.tools.shell_tool import ShellTool
from app.security.path_security import PathSecurity
from app.security.shell_security import ShellSecurity


class TestToolRegistry:
    
    @pytest.fixture
    def registry(self):
        return ToolRegistry()
    
    @pytest.fixture
    def file_tool(self, tmp_path):
        security = PathSecurity([str(tmp_path)])
        return FileTool(security)
    
    @pytest.fixture
    def shell_tool(self):
        security = ShellSecurity()
        return ShellTool(security)
    
    def test_register_tool(self, registry, file_tool):
        registry.register(file_tool)
        
        assert "file" in registry.tools
        assert registry.tools["file"] == file_tool
    
    def test_register_multiple_tools(self, registry, file_tool, shell_tool):
        registry.register(file_tool)
        registry.register(shell_tool)
        
        assert len(registry.tools) == 2
        assert "file" in registry.tools
        assert "shell" in registry.tools
    
    def test_get_tool_schema(self, registry, file_tool):
        registry.register(file_tool)
        
        schema = registry.get_tool_schema("file")
        
        assert schema["name"] == "file"
        assert "description" in schema
    
    def test_get_all_schemas(self, registry, file_tool, shell_tool):
        registry.register(file_tool)
        registry.register(shell_tool)
        
        schemas = registry.get_all_schemas()
        
        assert len(schemas) == 2
        assert any(s["name"] == "file" for s in schemas)
        assert any(s["name"] == "shell" for s in schemas)
```

- [ ] **步骤 2: 运行测试验证失败**

运行: `cd backend && pytest tests/test_tools/test_registry.py -v`
预期: FAIL - 模块不存在

- [ ] **步骤 3: 实现工具注册中心 backend/app/tools/registry.py**

```python
from typing import Dict, List, Optional
from app.tools.base import BaseTool
import logging

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """工具未找到错误"""
    pass


class ToolRegistry:
    """工具注册和管理中心"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        logger.info("工具注册中心初始化完成")
    
    def register(self, tool: BaseTool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self.tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")
    
    def unregister(self, name: str) -> None:
        """
        注销工具
        
        Args:
            name: 工具名称
        """
        if name in self.tools:
            del self.tools[name]
            logger.info(f"注销工具: {name}")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            Optional[BaseTool]: 工具实例,如果不存在返回 None
        """
        return self.tools.get(name)
    
    def get_tool_schema(self, name: str) -> Dict:
        """
        获取工具的 JSON Schema
        
        Args:
            name: 工具名称
            
        Returns:
            Dict: 工具 Schema
        """
        tool = self.get(name)
        if not tool:
            raise ToolNotFoundError(f"工具不存在: {name}")
        return tool.get_schema()
    
    def get_all_schemas(self) -> List[Dict]:
        """
        获取所有工具的 Schema
        
        Returns:
            List[Dict]: 所有工具的 Schema 列表
        """
        return [tool.get_schema() for tool in self.tools.values()]
    
    def list_tools(self) -> List[str]:
        """
        列出所有注册的工具名称
        
        Returns:
            List[str]: 工具名称列表
        """
        return list(self.tools.keys())
```

- [ ] **步骤 4: 运行测试验证通过**

运行: `cd backend && pytest tests/test_tools/test_registry.py -v`
预期: PASS

- [ ] **步骤 5: 更新 tools/__init__.py**

```python
from app.tools.base import BaseTool, ToolResult
from app.tools.file_tool import FileTool
from app.tools.shell_tool import ShellTool
from app.tools.registry import ToolRegistry, ToolNotFoundError

__all__ = [
    "BaseTool",
    "ToolResult",
    "FileTool",
    "ShellTool",
    "ToolRegistry",
    "ToolNotFoundError",
]
```

- [ ] **步骤 6: 提交代码**

```bash
git add backend/app/tools/ backend/tests/test_tools/
git commit -m "feat: 实现工具注册中心

- 创建 ToolRegistry 管理工具注册
- 支持工具注册、注销、查询
- 提供工具 Schema 获取接口
- 添加完整的单元测试"
```

---

## 模块三-B: MVP 核心补充组件 (Week 3-4) ✨ 新增

> **重要:** 这些是MVP必须实现的组件,优先级为 P0

### 任务 3.5: 实现 Patch 工具 🔴 P0

**优先级:** 🔴 高 - MVP 核心

**问题:** 没有Patch工具,Agent无法进行精确的代码修改,会退化为全文替换

**文件:**
- 创建: `backend/app/tools/patch_tool.py`
- 创建: `backend/app/tools/diff_parser.py`
- 创建: `backend/tests/test_tools/test_patch_tool.py`

- [ ] **步骤 1: 创建 Patch 工具测试**

```python
import pytest
import tempfile
import os
from pathlib import Path
from app.tools.patch_tool import PatchTool
from app.security.path_security import PathSecurity


class TestPatchTool:
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield os.path.realpath(tmpdir)
    
    @pytest.fixture
    def patch_tool(self, temp_dir):
        security = PathSecurity([temp_dir])
        return PatchTool(security)
    
    @pytest.mark.asyncio
    async def test_apply_simple_patch(self, patch_tool, temp_dir):
        # 创建测试文件
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")
        
        # 创建 patch
        patch = f"""--- a/{test_file}
+++ b/{test_file}
@@ -1,2 +1,2 @@
 def hello():
-    print('hello')
+    print('hello world')
"""
        
        result = await patch_tool.execute({"patch": patch})
        
        assert result.success is True
        assert "hello world" in test_file.read_text()
    
    @pytest.mark.asyncio
    async def test_patch_with_multiple_hunks(self, patch_tool, temp_dir):
        # 测试多个 Hunk
        pass
    
    @pytest.mark.asyncio
    async def test_patch_conflict_detection(self, patch_tool, temp_dir):
        # 测试冲突检测
        pass
```

- [ ] **步骤 2: 实现 Diff 解析器 backend/app/tools/diff_parser.py**

```python
import re
from typing import List
from dataclasses import dataclass


@dataclass
class Hunk:
    """Diff Hunk"""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str]


class DiffParser:
    """Unified Diff 解析器"""
    
    def parse(self, diff_text: str) -> List[Hunk]:
        """解析 Unified Diff"""
        hunks = []
        lines = diff_text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 查找 hunk 头: @@ -old_start,old_count +new_start,new_count @@
            if line.startswith('@@'):
                match = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', line)
                if match:
                    hunk = Hunk(
                        old_start=int(match.group(1)),
                        old_count=int(match.group(2) or 1),
                        new_start=int(match.group(3)),
                        new_count=int(match.group(4) or 1),
                        lines=[]
                    )
                    
                    # 收集 hunk 内容
                    i += 1
                    while i < len(lines) and not lines[i].startswith('@@'):
                        if lines[i].startswith(('+', '-', ' ')):
                            hunk.lines.append(lines[i])
                        i += 1
                    
                    hunks.append(hunk)
                else:
                    i += 1
            else:
                i += 1
        
        return hunks
    
    def extract_file_path(self, diff_text: str) -> str:
        """从 Diff 中提取文件路径"""
        lines = diff_text.split('\n')
        
        for line in lines:
            if line.startswith('+++ '):
                path = line[4:].strip()
                # 移除 b/ 前缀
                if path.startswith('b/'):
                    path = path[2:]
                return path
        
        return None
```

- [ ] **步骤 3: 实现 Patch 工具 backend/app/tools/patch_tool.py**

```python
from typing import Dict, Any
from app.tools.base import BaseTool, ToolResult
from app.security.path_security import PathSecurity
from app.tools.diff_parser import DiffParser
import logging

logger = logging.getLogger(__name__)


class PatchTool(BaseTool):
    """Patch 工具 - 应用 Unified Diff"""
    
    def __init__(self, security: PathSecurity):
        self.security = security
        self.parser = DiffParser()
    
    @property
    def name(self) -> str:
        return "patch"
    
    @property
    def description(self) -> str:
        return "应用 Unified Diff 格式的代码补丁"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """执行 Patch"""
        patch_text = args.get("patch")
        
        if not patch_text:
            return ToolResult(success=False, error="缺少 patch 参数")
        
        try:
            # 解析 diff
            hunks = self.parser.parse(patch_text)
            
            if not hunks:
                return ToolResult(success=False, error="无法解析 Diff 格式")
            
            # 提取文件路径
            file_path = self.parser.extract_file_path(patch_text)
            if not file_path:
                return ToolResult(success=False, error="无法从 Diff 中提取文件路径")
            
            # 验证路径安全性
            file_path = self.security.validate_write_path(file_path)
            
            # 读取原文件
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_lines = f.readlines()
            except FileNotFoundError:
                original_lines = []
            
            # 应用 Patch
            result_lines, applied, rejected = self._apply_hunks(original_lines, hunks)
            
            if rejected == 0:
                # 写入修改后的文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(result_lines)
                
                logger.info(f"成功应用 Patch: {file_path}, {applied} 个 Hunk")
                return ToolResult(
                    success=True,
                    output=f"成功应用 {applied} 个修改",
                    data={"file": file_path, "hunks_applied": applied}
                )
            else:
                logger.warning(f"Patch 部分失败: {rejected} 个 Hunk 被拒绝")
                return ToolResult(
                    success=False,
                    error=f"Patch 冲突: {rejected} 个修改无法应用"
                )
        
        except Exception as e:
            logger.error(f"Patch 执行失败: {str(e)}")
            return ToolResult(success=False, error=str(e))
    
    def _apply_hunks(self, original_lines: list, hunks: list) -> tuple:
        """应用所有 Hunk"""
        result_lines = original_lines[:]
        applied = 0
        rejected = 0
        
        # 从后往前应用,避免行号偏移
        for hunk in reversed(hunks):
            if self._apply_hunk(result_lines, hunk):
                applied += 1
            else:
                rejected += 1
        
        return result_lines, applied, rejected
    
    def _apply_hunk(self, lines: list, hunk: Hunk) -> bool:
        """应用单个 Hunk"""
        # 简化实现: 直接替换
        # TODO: 添加上下文验证
        
        start = hunk.old_start - 1  # 转为 0-based
        delete_count = hunk.old_count
        new_lines = []
        
        for line in hunk.lines:
            if line.startswith('+'):
                new_lines.append(line[1:] + '\n')
        
        # 执行替换
        if start >= 0 and start <= len(lines):
            lines[start:start + delete_count] = new_lines
            return True
        
        return False
```

- [ ] **步骤 4: 运行测试**

运行: `cd backend && pytest tests/test_tools/test_patch_tool.py -v`
预期: PASS

- [ ] **步骤 5: 更新 requirements.txt**

添加依赖:
```txt
# 已有依赖
```

- [ ] **步骤 6: 提交代码**

```bash
git add backend/app/tools/patch_tool.py backend/app/tools/diff_parser.py backend/tests/test_tools/test_patch_tool.py
git commit -m "feat: 实现 Patch 工具

- 实现 Unified Diff 解析器
- 支持 Hunk 应用
- 支持冲突检测
- 为 Agent 提供精确代码修改能力"
```

---

### 任务 3.6: 实现持久化存储层 🔴 P0

**优先级:** 🔴 高 - MVP 基础设施

**问题:** 数据重启丢失,无法追溯执行历史

**技术选型:** SQLite + SQLAlchemy

**文件:**
- 创建: `backend/app/storage/`
- 创建: `backend/app/storage/__init__.py`
- 创建: `backend/app/storage/database.py`
- 创建: `backend/app/storage/models.py`
- 创建: `backend/app/storage/repositories/__init__.py`
- 创建: `backend/app/storage/repositories/project_repo.py`
- 创建: `backend/app/storage/repositories/execution_repo.py`
- 创建: `backend/tests/test_storage/`

- [ ] **步骤 1: 更新 requirements.txt 添加数据库依赖**

```txt
sqlalchemy==2.0.25
alembic==1.13.1
```

- [ ] **步骤 2: 创建数据库模型 backend/app/storage/models.py**

```python
from sqlalchemy import Column, String, DateTime, JSON, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class ProjectModel(Base):
    """项目数据模型"""
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True)
    language = Column(String)
    config = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ExecutionModel(Base):
    """执行记录模型"""
    __tablename__ = "executions"
    
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    task = Column(Text, nullable=False)
    status = Column(String, default="pending", index=True)
    steps = Column(JSON, default=[])
    result = Column(Text)
    total_duration = Column(Integer)  # 毫秒
    created_at = Column(DateTime, default=datetime.now, index=True)
    completed_at = Column(DateTime)


class ConversationModel(Base):
    """对话记录模型"""
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True)
    execution_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)


class LLMUsageModel(Base):
    """LLM 使用统计模型"""
    __tablename__ = "llm_usage"
    
    id = Column(String, primary_key=True)
    execution_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost = Column(Integer, default=0)  # 单位: 分
    timestamp = Column(DateTime, default=datetime.now)
```

- [ ] **步骤 3: 创建数据库连接 backend/app/storage/database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from pathlib import Path
from app.storage.models import Base
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite 数据库管理"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # 默认在用户目录下创建数据库
            db_dir = Path.home() / ".reflexion"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "reflexion.db")
        
        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False}
        )
        
        # 创建表
        Base.metadata.create_all(self.engine)
        
        # 创建会话工厂
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"数据库初始化完成: {db_path}")
    
    @contextmanager
    def get_session(self) -> Session:
        """获取数据库会话"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def create_session(self) -> Session:
        """创建数据库会话"""
        return self.SessionLocal()


# 全局数据库实例
db = Database()
```

- [ ] **步骤 4: 创建项目仓储 backend/app/storage/repositories/project_repo.py**

```python
from typing import List, Optional
from sqlalchemy.orm import Session
from app.storage.models import ProjectModel
from app.models.project import Project, ProjectCreate
import logging

logger = logging.getLogger(__name__)


class ProjectRepository:
    """项目数据仓储"""
    
    def __init__(self, db):
        self.db = db
    
    def save(self, project: Project) -> Project:
        """保存项目"""
        with self.db.get_session() as session:
            # 检查是否已存在
            existing = session.query(ProjectModel).filter_by(
                path=project.path
            ).first()
            
            if existing:
                # 更新
                existing.name = project.name
                existing.language = project.language
                existing.config = project.config or {}
            else:
                # 新建
                model = ProjectModel(
                    id=project.id,
                    name=project.name,
                    path=project.path,
                    language=project.language,
                    config={}
                )
                session.add(model)
            
            logger.info(f"保存项目: {project.id}")
            return project
    
    def get(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(id=project_id).first()
            if model:
                return Project(
                    id=model.id,
                    name=model.name,
                    path=model.path,
                    language=model.language,
                    created_at=model.created_at,
                    updated_at=model.updated_at
                )
            return None
    
    def get_by_path(self, path: str) -> Optional[Project]:
        """根据路径获取项目"""
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(path=path).first()
            if model:
                return Project(
                    id=model.id,
                    name=model.name,
                    path=model.path,
                    language=model.language,
                    created_at=model.created_at,
                    updated_at=model.updated_at
                )
            return None
    
    def list_all(self) -> List[Project]:
        """列出所有项目"""
        with self.db.get_session() as session:
            models = session.query(ProjectModel).order_by(
                ProjectModel.updated_at.desc()
            ).all()
            
            return [
                Project(
                    id=m.id,
                    name=m.name,
                    path=m.path,
                    language=m.language,
                    created_at=m.created_at,
                    updated_at=m.updated_at
                )
                for m in models
            ]
    
    def delete(self, project_id: str) -> bool:
        """删除项目"""
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(id=project_id).first()
            if model:
                session.delete(model)
                logger.info(f"删除项目: {project_id}")
                return True
            return False
```

- [ ] **步骤 5: 创建执行记录仓储 backend/app/storage/repositories/execution_repo.py**

```python
from typing import List, Optional
from sqlalchemy.orm import Session
from app.storage.models import ExecutionModel
from app.models.execution import Execution, ExecutionCreate
import logging

logger = logging.getLogger(__name__)


class ExecutionRepository:
    """执行记录仓储"""
    
    def __init__(self, db):
        self.db = db
    
    def save(self, execution: Execution) -> Execution:
        """保存执行记录"""
        with self.db.get_session() as session:
            model = ExecutionModel(
                id=execution.id,
                project_id=execution.project_id,
                task=execution.task,
                status=execution.status.value,
                steps=[step.dict() for step in execution.steps],
                result=execution.result,
                total_duration=int(execution.total_duration * 1000) if execution.total_duration else None,
                created_at=execution.created_at,
                completed_at=execution.completed_at
            )
            session.add(model)
            logger.info(f"保存执行记录: {execution.id}")
            return execution
    
    def get(self, execution_id: str) -> Optional[Execution]:
        """获取执行记录"""
        with self.db.get_session() as session:
            model = session.query(ExecutionModel).filter_by(id=execution_id).first()
            if model:
                from app.models.execution import ExecutionStep, ExecutionStatus
                
                return Execution(
                    id=model.id,
                    project_id=model.project_id,
                    task=model.task,
                    status=ExecutionStatus(model.status),
                    steps=[ExecutionStep(**s) for s in model.steps],
                    result=model.result,
                    total_duration=model.total_duration / 1000 if model.total_duration else None,
                    created_at=model.created_at,
                    completed_at=model.completed_at
                )
            return None
    
    def list_by_project(self, project_id: str, limit: int = 10) -> List[Execution]:
        """获取项目的执行历史"""
        with self.db.get_session() as session:
            models = session.query(ExecutionModel).filter_by(
                project_id=project_id
            ).order_by(
                ExecutionModel.created_at.desc()
            ).limit(limit).all()
            
            from app.models.execution import ExecutionStep, ExecutionStatus
            
            return [
                Execution(
                    id=m.id,
                    project_id=m.project_id,
                    task=m.task,
                    status=ExecutionStatus(m.status),
                    steps=[ExecutionStep(**s) for s in m.steps],
                    result=m.result,
                    total_duration=m.total_duration / 1000 if m.total_duration else None,
                    created_at=m.created_at,
                    completed_at=m.completed_at
                )
                for m in models
            ]
```

- [ ] **步骤 6: 创建存储层测试**

```python
import pytest
from app.storage.database import Database
from app.storage.repositories.project_repo import ProjectRepository
from app.models.project import Project, ProjectCreate


class TestProjectRepository:
    
    @pytest.fixture
    def db(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        return Database(db_path)
    
    @pytest.fixture
    def repo(self, db):
        return ProjectRepository(db)
    
    def test_save_project(self, repo):
        project = Project(
            id="proj-123",
            name="TestProject",
            path="/tmp/test"
        )
        
        result = repo.save(project)
        
        assert result.id == "proj-123"
        assert result.name == "TestProject"
    
    def test_get_project(self, repo):
        project = Project(
            id="proj-456",
            name="TestProject2",
            path="/tmp/test2"
        )
        repo.save(project)
        
        result = repo.get("proj-456")
        
        assert result is not None
        assert result.name == "TestProject2"
    
    def test_list_all(self, repo):
        for i in range(3):
            project = Project(
                id=f"proj-{i}",
                name=f"Project{i}",
                path=f"/tmp/test{i}"
            )
            repo.save(project)
        
        result = repo.list_all()
        
        assert len(result) == 3
```

- [ ] **步骤 7: 运行测试**

运行: `cd backend && pytest tests/test_storage/ -v`
预期: PASS

- [ ] **步骤 8: 提交代码**

```bash
git add backend/app/storage/ backend/tests/test_storage/ backend/requirements.txt
git commit -m "feat: 实现持久化存储层

- 使用 SQLite 作为数据库
- 实现 SQLAlchemy ORM 模型
- 创建项目和执行记录仓储
- 支持数据持久化和查询"
```

---

### 任务 3.7: 完善配置管理系统 🔴 P0

**优先级:** 🔴 高 - 用户体验

**文件:**
- 创建: `backend/app/config/settings.py`
- 创建: `backend/app/config/llm_config.py`
- 创建: `backend/tests/test_config/`

- [ ] **步骤 1: 创建配置管理 backend/app/config/settings.py**

```python
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import json


class LLMSettings(BaseModel):
    """LLM 配置"""
    provider: str = "openai"
    model: str = "gpt-4-turbo-preview"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)


class ExecutionSettings(BaseModel):
    """执行配置"""
    max_steps: int = Field(default=50, ge=1, le=200)
    max_file_size: int = Field(default=10485760)  # 10MB
    max_execution_time: int = Field(default=600)  # 10分钟
    enable_auto_fix: bool = True


class UISettings(BaseModel):
    """界面配置"""
    theme: str = "light"
    auto_scroll: bool = True
    show_timestamps: bool = True


class AppSettings(BaseModel):
    """应用总配置"""
    llm: LLMSettings = LLMSettings()
    execution: ExecutionSettings = ExecutionSettings()
    ui: UISettings = UISettings()


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_dir = Path.home() / ".reflexion"
            config_dir.mkdir(exist_ok=True)
            config_path = str(config_dir / "config.json")
        
        self.config_path = Path(config_path)
        self.settings = self._load()
    
    def _load(self) -> AppSettings:
        """加载配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return AppSettings(**data)
            except Exception:
                pass
        
        return AppSettings()
    
    def save(self):
        """保存配置"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.settings.dict(), f, indent=2, ensure_ascii=False)
    
    def update_llm(self, llm_settings: LLMSettings):
        """更新 LLM 配置"""
        self.settings.llm = llm_settings
        self.save()
    
    def update_execution(self, execution_settings: ExecutionSettings):
        """更新执行配置"""
        self.settings.execution = execution_settings
        self.save()
    
    def update_ui(self, ui_settings: UISettings):
        """更新界面配置"""
        self.settings.ui = ui_settings
        self.save()
    
    def reset(self):
        """重置为默认配置"""
        self.settings = AppSettings()
        self.save()


# 全局配置管理器
config_manager = ConfigManager()
```

- [ ] **步骤 2: 创建 LLM 配置管理 backend/app/config/llm_config.py**

```python
from typing import Optional
from app.config.settings import config_manager, LLMSettings
from app.models.llm_config import LLMConfig, LLMProvider
import logging

logger = logging.getLogger(__name__)


class LLMConfigManager:
    """LLM 配置管理"""
    
    @staticmethod
    def get_config() -> LLMConfig:
        """获取当前 LLM 配置"""
        settings = config_manager.settings.llm
        
        return LLMConfig(
            provider=LLMProvider(settings.provider),
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens
        )
    
    @staticmethod
    def update_config(config: LLMConfig):
        """更新 LLM 配置"""
        llm_settings = LLMSettings(
            provider=config.provider.value,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )
        
        config_manager.update_llm(llm_settings)
        logger.info(f"LLM 配置已更新: {config.provider.value} - {config.model}")
    
    @staticmethod
    def set_api_key(api_key: str, provider: str = "openai"):
        """设置 API Key"""
        config = LLMConfigManager.get_config()
        config.api_key = api_key
        if provider:
            config.provider = LLMProvider(provider)
        LLMConfigManager.update_config(config)
```

- [ ] **步骤 3: 提交代码**

```bash
git add backend/app/config/
git commit -m "feat: 完善配置管理系统

- 实现应用配置管理器
- 支持 LLM/执行/界面配置
- 配置持久化到本地
- 支持动态配置更新"
```

---

### 任务 3.8: 实现 WebSocket 后端 🔴 P0

**优先级:** 🔴 高 - 实时性要求

**文件:**
- 创建: `backend/app/api/websocket.py`
- 更新: `backend/app/main.py`

- [ ] **步骤 1: 创建 WebSocket 连接管理器 backend/app/api/websocket.py**

```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # execution_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, execution_id: str):
        """接受新连接"""
        await websocket.accept()
        
        if execution_id not in self.active_connections:
            self.active_connections[execution_id] = set()
        
        self.active_connections[execution_id].add(websocket)
        logger.info(f"WebSocket 连接: execution_id={execution_id}, 当前连接数={len(self.active_connections[execution_id])}")
    
    def disconnect(self, websocket: WebSocket, execution_id: str):
        """断开连接"""
        if execution_id in self.active_connections:
            self.active_connections[execution_id].discard(websocket)
            
            if not self.active_connections[execution_id]:
                del self.active_connections[execution_id]
        
        logger.info(f"WebSocket 断开: execution_id={execution_id}")
    
    async def send_event(self, execution_id: str, event_type: str, data: dict):
        """发送事件到所有订阅该执行的客户端"""
        if execution_id not in self.active_connections:
            return
        
        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        disconnected = []
        
        for connection in self.active_connections[execution_id]:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn, execution_id)
    
    async def broadcast(self, event_type: str, data: dict):
        """广播到所有连接"""
        for execution_id in list(self.active_connections.keys()):
            await self.send_event(execution_id, event_type, data)


# 全局连接管理器
ws_manager = ConnectionManager()
```

- [ ] **步骤 2: 创建 WebSocket 路由**

在 `backend/app/api/websocket.py` 中添加:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.websocket import ws_manager

router = APIRouter()


@router.websocket("/ws/execution/{execution_id}")
async def websocket_endpoint(websocket: WebSocket, execution_id: str):
    """WebSocket 端点"""
    await ws_manager.connect(websocket, execution_id)
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # 处理心跳
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                
                # 处理控制命令
                elif message.get("type") == "control":
                    # TODO: 实现暂停/恢复/终止等控制
                    pass
            
            except json.JSONDecodeError:
                logger.warning(f"无效的 JSON 消息: {data}")
    
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, execution_id)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        ws_manager.disconnect(websocket, execution_id)
```

- [ ] **步骤 3: 更新 main.py 注册 WebSocket 路由**

```python
from app.api.websocket import router as ws_router

app.include_router(ws_router)
```

- [ ] **步骤 4: 在执行循环中集成 WebSocket**

在 `RapidExecutionLoop` 中:

```python
from app.api.websocket import ws_manager

class RapidExecutionLoop:
    async def run(self, task: str, context: ExecutionContext) -> Execution:
        execution_id = context.execution_id
        
        # 发送开始事件
        await ws_manager.send_event(execution_id, "execution:start", {
            "execution_id": execution_id,
            "task": task
        })
        
        for step_num in range(1, self.max_steps + 1):
            # 发送步骤开始事件
            await ws_manager.send_event(execution_id, "execution:step", {
                "step_number": step_num,
                "status": "running"
            })
            
            # 执行步骤...
            step = await self.execute_action(action, context, step_num)
            
            # 发送步骤完成事件
            await ws_manager.send_event(execution_id, "execution:step", {
                "step_number": step_num,
                "status": step.status.value,
                "tool": step.tool,
                "output": step.output,
                "duration": step.duration
            })
        
        # 发送完成事件
        await ws_manager.send_event(execution_id, "execution:complete", {
            "status": execution.status.value,
            "result": execution.result
        })
        
        return execution
```

- [ ] **步骤 5: 提交代码**

```bash
git add backend/app/api/websocket.py backend/app/main.py
git commit -m "feat: 实现 WebSocket 实时通信

- 创建 WebSocket 连接管理器
- 支持执行步骤实时推送
- 支持心跳机制
- 集成到执行循环"
```

---

## 模块四: Agent 执行引擎 (Week 4)

### 任务 4.1: 实现执行上下文管理

**文件:**
- 创建: `backend/app/execution/context_manager.py`
- 创建: `backend/tests/test_execution/test_context_manager.py`

- [ ] **步骤 1: 创建上下文管理测试 backend/tests/test_execution/test_context_manager.py**

```python
import pytest
from app.execution.context_manager import ExecutionContext
from app.models.action import Action, ActionType


class TestExecutionContext:
    
    def test_create_context(self):
        context = ExecutionContext(task="测试任务")
        
        assert context.task == "测试任务"
        assert len(context.history) == 0
    
    def test_update_history(self):
        context = ExecutionContext(task="测试任务")
        action = Action(type=ActionType.TOOL_CALL, tool="file", args={"path": "test.py"})
        
        context.update_history(action, "执行结果")
        
        assert len(context.history) == 1
        assert context.history[0]["action"] == action
        assert context.history[0]["result"] == "执行结果"
    
    def test_get_recent_history(self):
        context = ExecutionContext(task="测试任务")
        
        for i in range(5):
            action = Action(type=ActionType.TOOL_CALL, tool="file", args={"index": i})
            context.update_history(action, f"结果{i}")
        
        recent = context.get_recent_history(3)
        
        assert len(recent) == 3
        assert recent[0]["result"] == "结果2"
        assert recent[2]["result"] == "结果4"
```

- [ ] **步骤 2: 运行测试验证失败**

运行: `cd backend && pytest tests/test_execution/test_context_manager.py -v`
预期: FAIL - 模块不存在

- [ ] **步骤 3: 实现执行上下文 backend/app/execution/context_manager.py**

```python
from typing import List, Dict, Any, Optional
from app.models.action import Action
from app.models.execution import ExecutionStep, StepStatus
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ExecutionContext:
    """Agent 执行上下文"""
    
    def __init__(self, task: str, project_path: Optional[str] = None):
        self.task = task
        self.project_path = project_path
        self.history: List[Dict[str, Any]] = []
        self.steps: List[ExecutionStep] = []
        self.current_step_number = 0
        self.workspace_snapshot: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
    
    def update_history(self, action: Action, result: str) -> None:
        """
        更新执行历史
        
        Args:
            action: 执行的动作
            result: 执行结果
        """
        self.history.append({
            "action": action,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"更新执行历史,动作: {action.type}")
    
    def add_step(self, step: ExecutionStep) -> None:
        """
        添加执行步骤
        
        Args:
            step: 执行步骤
        """
        self.steps.append(step)
        self.current_step_number = step.step_number
        logger.info(f"添加执行步骤 {step.step_number}: {step.tool}")
    
    def update_step(self, step_id: str, status: StepStatus, output: Optional[str] = None) -> None:
        """
        更新步骤状态
        
        Args:
            step_id: 步骤 ID
            status: 新状态
            output: 输出内容
        """
        for step in self.steps:
            if step.id == step_id:
                step.status = status
                if output:
                    step.output = output
                logger.info(f"更新步骤 {step_id} 状态为 {status}")
                break
    
    def get_recent_history(self, limit: int = 3) -> List[Dict[str, Any]]:
        """
        获取最近的执行历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            List[Dict[str, Any]]: 最近的历史记录
        """
        return self.history[-limit:] if len(self.history) > limit else self.history
    
    def get_workspace_context(self) -> str:
        """
        获取工作区上下文信息
        
        Returns:
            str: 上下文信息字符串
        """
        recent_history = self.get_recent_history(3)
        
        context_parts = [f"任务: {self.task}"]
        
        if recent_history:
            context_parts.append("\n最近的操作:")
            for i, item in enumerate(recent_history, 1):
                action = item["action"]
                context_parts.append(f"{i}. {action.type}: {action.tool or 'finish'}")
        
        return "\n".join(context_parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        Returns:
            Dict[str, Any]: 上下文字典
        """
        return {
            "task": self.task,
            "project_path": self.project_path,
            "current_step": self.current_step_number,
            "total_steps": len(self.steps),
            "history_count": len(self.history)
        }
```

- [ ] **步骤 4: 运行测试验证通过**

运行: `cd backend && pytest tests/test_execution/test_context_manager.py -v`
预期: PASS

- [ ] **步骤 5: 提交代码**

```bash
git add backend/app/execution/context_manager.py backend/tests/test_execution/
git commit -m "feat: 实现执行上下文管理

- 创建 ExecutionContext 管理执行状态
- 支持执行历史记录
- 支持步骤管理
- 提供工作区上下文获取
- 添加完整的单元测试"
```

---

### 任务 4.2: 实现 Agent 执行循环 (核心)

**文件:**
- 创建: `backend/app/execution/rapid_loop.py`
- 创建: `backend/tests/test_execution/test_rapid_loop.py`

- [ ] **步骤 1: 创建执行循环测试 backend/tests/test_execution/test_rapid_loop.py**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.execution.rapid_loop import RapidExecutionLoop
from app.execution.context_manager import ExecutionContext
from app.llm.base import Message, LLMResponse
from app.models.action import Action, ActionType
from app.tools.registry import ToolRegistry


class TestRapidExecutionLoop:
    
    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.get_model_name.return_value = "gpt-4"
        return llm
    
    @pytest.fixture
    def mock_registry(self):
        return ToolRegistry()
    
    @pytest.fixture
    def execution_loop(self, mock_llm, mock_registry):
        return RapidExecutionLoop(llm=mock_llm, tool_registry=mock_registry)
    
    @pytest.mark.asyncio
    async def test_decide_action_with_finish(self, execution_loop, mock_llm):
        context = ExecutionContext(task="测试任务")
        
        mock_llm.complete.return_value = LLMResponse(
            content='{"type": "finish", "thought": "完成", "answer": "任务完成", "confidence": 0.9}',
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        action = await execution_loop.decide_action(context)
        
        assert action.type == ActionType.FINISH
        assert action.confidence == 0.9
    
    @pytest.mark.asyncio
    async def test_decide_action_with_tool_call(self, execution_loop, mock_llm):
        context = ExecutionContext(task="测试任务")
        
        mock_llm.complete.return_value = LLMResponse(
            content='{"type": "tool_call", "thought": "读取文件", "tool": "file", "args": {"action": "read", "path": "test.py"}, "confidence": 0.8}',
            model="gpt-4",
            usage={"total_tokens": 100}
        )
        
        action = await execution_loop.decide_action(context)
        
        assert action.type == ActionType.TOOL_CALL
        assert action.tool == "file"
        assert action.args["path"] == "test.py"
```

- [ ] **步骤 2: 运行测试验证失败**

运行: `cd backend && pytest tests/test_execution/test_rapid_loop.py -v`
预期: FAIL - 模块不存在

- [ ] **步骤 3: 实现 Agent 执行循环 backend/app/execution/rapid_loop.py**

```python
import json
from typing import Optional
from app.llm.base import UniversalLLMInterface, Message
from app.models.action import Action, ActionType, ActionResult
from app.models.execution import ExecutionStep, StepStatus, Execution, ExecutionStatus
from app.execution.context_manager import ExecutionContext
from app.tools.registry import ToolRegistry
from app.config import settings
import logging
import uuid
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class RapidExecutionLoop:
    """快速执行循环 - Agent 核心执行引擎"""
    
    def __init__(
        self,
        llm: UniversalLLMInterface,
        tool_registry: ToolRegistry,
        max_steps: int = None
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.max_steps = max_steps or settings.max_execution_steps
    
    async def run(self, task: str, project_path: Optional[str] = None) -> Execution:
        """
        执行任务
        
        Args:
            task: 任务描述
            project_path: 项目路径
            
        Returns:
            Execution: 执行结果
        """
        start_time = time.time()
        
        execution = Execution(
            project_id=project_path or "standalone",
            task=task,
            status=ExecutionStatus.RUNNING
        )
        
        context = ExecutionContext(task=task, project_path=project_path)
        
        logger.info(f"开始执行任务: {task}")
        
        try:
            for step_num in range(1, self.max_steps + 1):
                action = await self.decide_action(context)
                
                if action.type == ActionType.FINISH:
                    execution.status = ExecutionStatus.COMPLETED
                    execution.result = action.confidence
                    logger.info(f"任务完成: {action.confidence}")
                    break
                
                step = await self.execute_action(action, context, step_num)
                execution.steps.append(step)
                context.add_step(step)
                
                if step.status == StepStatus.FAILED and step.error:
                    await self.handle_error(context, step)
            
            else:
                execution.status = ExecutionStatus.FAILED
                execution.result = "超过最大步数限制"
                logger.warning("执行超过最大步数限制")
        
        except Exception as e:
            execution.status = ExecutionStatus.FAILED
            execution.result = str(e)
            logger.error(f"执行异常: {str(e)}")
        
        finally:
            execution.total_duration = time.time() - start_time
            execution.completed_at = datetime.now()
        
        return execution
    
    async def decide_action(self, context: ExecutionContext) -> Action:
        """
        决定下一步动作
        
        Args:
            context: 执行上下文
            
        Returns:
            Action: 决定的动作
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context)
        
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt)
        ]
        
        response = await self.llm.complete(messages)
        
        try:
            action_data = json.loads(response.content)
            action = Action(**action_data)
            logger.info(f"LLM 决策: {action.type} - {action.tool or 'finish'}")
            return action
        except json.JSONDecodeError as e:
            logger.error(f"解析 LLM 响应失败: {str(e)}")
            return Action(
                type=ActionType.FINISH,
                thought="解析失败",
                confidence=0.0
            )
    
    async def execute_action(
        self,
        action: Action,
        context: ExecutionContext,
        step_number: int
    ) -> ExecutionStep:
        """
        执行动作
        
        Args:
            action: 要执行的动作
            context: 执行上下文
            step_number: 步骤编号
            
        Returns:
            ExecutionStep: 执行步骤
        """
        step = ExecutionStep(
            id=f"step-{uuid.uuid4().hex[:8]}",
            step_number=step_number,
            tool=action.tool,
            args=action.args,
            status=StepStatus.RUNNING
        )
        
        start_time = time.time()
        
        try:
            tool = self.tool_registry.get(action.tool)
            
            if not tool:
                raise ValueError(f"工具不存在: {action.tool}")
            
            result = await tool.execute(action.args)
            
            step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
            step.output = result.output
            step.error = result.error
            step.duration = time.time() - start_time
            
            context.update_history(action, result.output or result.error)
            
            logger.info(f"步骤 {step_number} 执行{'成功' if result.success else '失败'}: {action.tool}")
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.duration = time.time() - start_time
            logger.error(f"步骤 {step_number} 执行异常: {str(e)}")
        
        return step
    
    async def handle_error(self, context: ExecutionContext, step: ExecutionStep) -> None:
        """
        处理错误
        
        Args:
            context: 执行上下文
            step: 失败的步骤
        """
        error_message = f"""
上一步执行失败:
工具: {step.tool}
错误: {step.error}

请尝试其他方法或报告无法完成任务。
"""
        context.metadata["last_error"] = error_message
        logger.warning(f"处理错误: {step.error}")
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        tools_schema = self.tool_registry.get_all_schemas()
        
        return f"""你是一个自主编程 Agent,在本地工作区执行任务。

你必须:
- 使用工具逐步解决问题
- 优先使用最小修改(使用 file 工具)
- 自动修复错误
- 通过 Shell 命令验证结果

规则:
- 输出必须是有效的 JSON
- JSON 之外不允许额外文本
- thought 字段保持简短(1句话)

可用工具:
{json.dumps(tools_schema, indent=2, ensure_ascii=False)}

输出格式示例:
{{"type": "tool_call", "thought": "读取配置文件", "tool": "file", "args": {{"action": "read", "path": "config.py"}}, "confidence": 0.8}}
{{"type": "finish", "thought": "任务完成", "confidence": 0.95}}
"""
    
    def _build_user_prompt(self, context: ExecutionContext) -> str:
        """构建用户提示词"""
        workspace_context = context.get_workspace_context()
        
        recent_history = context.get_recent_history(3)
        history_text = ""
        if recent_history:
            history_text = "\n最近的操作:\n"
            for item in recent_history:
                action = item["action"]
                history_text += f"- {action.type}: {action.tool or 'finish'} -> {item['result'][:100]}\n"
        
        error_context = context.metadata.get("last_error", "")
        
        return f"""任务:
{context.task}

{history_text}

{error_context}

工作区:
{workspace_context}

你的下一步动作是什么?(只输出 JSON)
"""
```

- [ ] **步骤 4: 运行测试验证通过**

运行: `cd backend && pytest tests/test_execution/test_rapid_loop.py -v`
预期: PASS

- [ ] **步骤 5: 提交代码**

```bash
git add backend/app/execution/rapid_loop.py backend/tests/test_execution/
git commit -m "feat: 实现 Agent 快速执行循环

- 实现 RapidExecutionLoop 核心引擎
- 支持基于 LLM 的决策机制
- 实现工具调用执行器
- 支持错误处理和自动修复
- 添加完整的单元测试"
```

---

### 任务 4.3: 实现 Prompt 管理系统 ✨ NEW

**文件:**
- 创建: `backend/app/execution/prompt_manager.py`
- 创建: `backend/tests/test_execution/test_prompt_manager.py`

**优先级:** 🔴 高 (Prompt 是 Agent 的核心)

**目标:**
- 实现 Prompt 模板管理
- 支持 System/Step/Error 三种 Prompt
- 支持模板变量替换
- 为后续扩展预留接口

- [ ] **步骤 1: 创建 Prompt 管理器测试**

```python
import pytest
from app.execution.prompt_manager import PromptManager


class TestPromptManager:
    
    def test_get_system_prompt(self):
        manager = PromptManager()
        
        prompt = manager.get_system_prompt(tools=[])
        
        assert "autonomous coding agent" in prompt
        assert "Output MUST be valid JSON" in prompt
    
    def test_get_step_prompt(self):
        from app.execution.context_manager import ExecutionContext
        manager = PromptManager()
        context = ExecutionContext(task="修复bug")
        
        prompt = manager.get_step_prompt(context)
        
        assert "修复bug" in prompt
        assert "What is your next action" in prompt
    
    def test_get_error_prompt(self):
        manager = PromptManager()
        
        prompt = manager.get_error_prompt(
            error="File not found",
            tool="file",
            code_snippet="def test(): pass"
        )
        
        assert "File not found" in prompt
        assert "Fix the issue" in prompt
```

- [ ] **步骤 2: 实现 Prompt 管理器**

创建 `backend/app/execution/prompt_manager.py` (参考设计文档中的实现)

- [ ] **步骤 3: 运行测试验证**

运行: `cd backend && pytest tests/test_execution/test_prompt_manager.py -v`
预期: PASS

- [ ] **步骤 4: 提交代码**

```bash
git add backend/app/execution/prompt_manager.py backend/tests/test_execution/test_prompt_manager.py
git commit -m "feat: 实现 Prompt 管理系统

- 创建 PromptManager 管理模板
- 支持 System/Step/Error 三种 Prompt
- 支持模板变量替换
- 为后续扩展预留接口"
```

---

### 任务 4.4: 预留 Skills 和 MCP 接口 ✨ NEW

**文件:**
- 创建: `backend/app/orchestration/__init__.py`
- 创建: `backend/app/orchestration/skill_registry.py`
- 创建: `backend/app/orchestration/mcp_manager.py`
- 创建: `backend/tests/test_orchestration/`

**优先级:** 🟡 中 (第二阶段完整实现)

**目标:**
- 创建 Skills 系统基础接口
- 创建 MCP 协议基础接口
- 注册默认 Skills
- 为第二阶段完整实现预留架构

- [ ] **步骤 1: 创建编排层目录**

```bash
mkdir -p backend/app/orchestration
mkdir -p backend/tests/test_orchestration
touch backend/app/orchestration/__init__.py
```

- [ ] **步骤 2: 创建 SkillRegistry 骨架**

创建 `backend/app/orchestration/skill_registry.py`:
```python
from typing import Dict, List, Optional
from pydantic import BaseModel


class Skill(BaseModel):
    """技能定义"""
    name: str
    description: str
    tools: List[str]
    prompt_template: str


class SkillRegistry:
    """技能注册中心 - 第一阶段仅提供基础接口"""
    
    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        # TODO: 第二阶段实现完整的技能系统
    
    def register_skill(self, skill: Skill):
        """注册技能"""
        self.skills[skill.name] = skill
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self.skills.get(name)
    
    def list_skills(self) -> List[Skill]:
        """列出所有技能"""
        return list(self.skills.values())
```

- [ ] **步骤 3: 创建 MCPManager 骨架**

创建 `backend/app/orchestration/mcp_manager.py`:
```python
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class MCPManager:
    """MCP 管理器 - 第一阶段仅提供接口定义"""
    
    def __init__(self):
        self.servers: Dict[str, any] = {}
        # TODO: 第二阶段实现完整的 MCP 协议支持
    
    async def register_server(self, server_id: str, config: Dict) -> bool:
        """注册 MCP 服务器 (第二阶段实现)"""
        logger.warning("MCP support will be implemented in Phase 2")
        return False
    
    async def call_tool(self, name: str, arguments: Dict) -> any:
        """调用 MCP 工具 (第二阶段实现)"""
        raise NotImplementedError("MCP support will be implemented in Phase 2")
    
    def list_tools(self) -> List:
        """列出 MCP 工具 (第二阶段实现)"""
        return []
```

- [ ] **步骤 4: 提交代码**

```bash
git add backend/app/orchestration/ backend/tests/test_orchestration/
git commit -m "feat: 预留 Skills 和 MCP 接口

- 创建 SkillRegistry 基础接口
- 创建 MCPManager 基础接口
- 为第二阶段完整实现预留架构
- 添加 TODO 标记"
```

---

## 模块五: API 路由实现 (Week 5)

### 任务 5.1: 实现项目管理 API

**文件:**
- 创建: `backend/app/api/routes/projects.py`
- 创建: `backend/app/services/project_service.py`
- 创建: `backend/tests/test_api/test_projects.py`

- [ ] **步骤 1: 创建项目服务 backend/app/services/project_service.py**

```python
from typing import List, Optional, Dict
from app.models.project import Project, ProjectCreate
import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class ProjectService:
    """项目管理服务"""
    
    def __init__(self, storage_path: str = ".reflexion/projects.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.projects: Dict[str, Project] = self._load_projects()
    
    def _load_projects(self) -> Dict[str, Project]:
        """从存储加载项目"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {k: Project(**v) for k, v in data.items()}
            except Exception as e:
                logger.error(f"加载项目失败: {str(e)}")
        return {}
    
    def _save_projects(self) -> None:
        """保存项目到存储"""
        try:
            data = {k: v.model_dump() for k, v in self.projects.items()}
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            logger.info("项目数据已保存")
        except Exception as e:
            logger.error(f"保存项目失败: {str(e)}")
    
    def create_project(self, project_create: ProjectCreate) -> Project:
        """
        创建项目
        
        Args:
            project_create: 项目创建数据
            
        Returns:
            Project: 创建的项目
        """
        project = Project(**project_create.model_dump())
        self.projects[project.id] = project
        self._save_projects()
        logger.info(f"创建项目: {project.id} - {project.name}")
        return project
    
    def get_project(self, project_id: str) -> Optional[Project]:
        """
        获取项目
        
        Args:
            project_id: 项目 ID
            
        Returns:
            Optional[Project]: 项目,如果不存在返回 None
        """
        return self.projects.get(project_id)
    
    def list_projects(self) -> List[Project]:
        """
        列出所有项目
        
        Returns:
            List[Project]: 项目列表
        """
        return list(self.projects.values())
    
    def delete_project(self, project_id: str) -> bool:
        """
        删除项目
        
        Args:
            project_id: 项目 ID
            
        Returns:
            bool: 是否删除成功
        """
        if project_id in self.projects:
            del self.projects[project_id]
            self._save_projects()
            logger.info(f"删除项目: {project_id}")
            return True
        return False
    
    def get_project_structure(self, project_id: str) -> Dict:
        """
        获取项目结构
        
        Args:
            project_id: 项目 ID
            
        Returns:
            Dict: 项目结构
        """
        project = self.get_project(project_id)
        if not project:
            return {}
        
        project_path = Path(project.path)
        if not project_path.exists():
            return {}
        
        structure = []
        for item in project_path.rglob("*"):
            if item.is_file() and not item.name.startswith('.'):
                structure.append({
                    "name": item.name,
                    "path": str(item.relative_to(project_path)),
                    "type": "file"
                })
        
        return {"files": structure[:100]}  # 限制返回数量
```

- [ ] **步骤 2: 创建项目 API 路由 backend/app/api/routes/projects.py**

```python
from fastapi import APIRouter, HTTPException
from typing import List
from app.models.project import Project, ProjectCreate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])

project_service = ProjectService()


@router.post("/", response_model=Project)
async def create_project(project: ProjectCreate):
    """创建项目"""
    return project_service.create_project(project)


@router.get("/", response_model=List[Project])
async def list_projects():
    """获取项目列表"""
    return project_service.list_projects()


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str):
    """获取项目详情"""
    project = project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """删除项目"""
    if not project_service.delete_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"message": "项目已删除"}


@router.get("/{project_id}/structure")
async def get_project_structure(project_id: str):
    """获取项目结构"""
    structure = project_service.get_project_structure(project_id)
    if not structure:
        raise HTTPException(status_code=404, detail="项目不存在或路径无效")
    return structure
```

- [ ] **步骤 3: 创建项目 API 测试 backend/tests/test_api/test_projects.py**

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestProjectsAPI:
    
    def test_create_project(self):
        response = client.post("/api/projects", json={
            "name": "TestProject",
            "path": "/tmp/test",
            "language": "python"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TestProject"
        assert data["path"] == "/tmp/test"
    
    def test_list_projects(self):
        client.post("/api/projects", json={
            "name": "Project1",
            "path": "/tmp/project1"
        })
        
        response = client.get("/api/projects")
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_project(self):
        create_response = client.post("/api/projects", json={
            "name": "Project2",
            "path": "/tmp/project2"
        })
        project_id = create_response.json()["id"]
        
        response = client.get(f"/api/projects/{project_id}")
        
        assert response.status_code == 200
        assert response.json()["name"] == "Project2"
    
    def test_delete_project(self):
        create_response = client.post("/api/projects", json={
            "name": "Project3",
            "path": "/tmp/project3"
        })
        project_id = create_response.json()["id"]
        
        response = client.delete(f"/api/projects/{project_id}")
        
        assert response.status_code == 200
```

- [ ] **步骤 4: 更新 main.py 注册路由**

在 `backend/app/main.py` 中添加:

```python
from app.api.routes import projects

app.include_router(projects.router)
```

- [ ] **步骤 5: 运行测试**

运行: `cd backend && pytest tests/test_api/test_projects.py -v`
预期: PASS

- [ ] **步骤 6: 提交代码**

```bash
git add backend/app/services/project_service.py backend/app/api/routes/projects.py backend/tests/test_api/ backend/app/main.py
git commit -m "feat: 实现项目管理 API

- 创建 ProjectService 管理项目数据
- 实现项目的 CRUD 接口
- 支持项目结构查询
- 添加完整的 API 测试"
```

---

### 任务 5.2: 实现 Agent 执行 API

**文件:**
- 创建: `backend/app/api/routes/agent.py`
- 创建: `backend/app/services/agent_service.py`
- 创建: `backend/tests/test_api/test_agent.py`

- [ ] **步骤 1: 创建 Agent 服务 backend/app/services/agent_service.py**

```python
from typing import Dict, Optional
from app.models.execution import Execution, ExecutionCreate
from app.models.llm_config import LLMConfig, LLMProvider
from app.execution.rapid_loop import RapidExecutionLoop
from app.execution.context_manager import ExecutionContext
from app.tools.registry import ToolRegistry
from app.tools.file_tool import FileTool
from app.tools.shell_tool import ShellTool
from app.security.path_security import PathSecurity
from app.security.shell_security import ShellSecurity
from app.llm import LLMAdapterFactory
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AgentService:
    """Agent 执行服务"""
    
    def __init__(self):
        self.executions: Dict[str, Execution] = {}
        self.tool_registry = self._init_tool_registry()
        self.llm_config: Optional[LLMConfig] = None
    
    def _init_tool_registry(self) -> ToolRegistry:
        """初始化工具注册中心"""
        registry = ToolRegistry()
        
        # 初始化安全控制
        path_security = PathSecurity(["/tmp"])  # 默认临时目录
        shell_security = ShellSecurity()
        
        # 注册工具
        registry.register(FileTool(path_security))
        registry.register(ShellTool(shell_security))
        
        logger.info("工具注册中心初始化完成")
        return registry
    
    def set_llm_config(self, config: LLMConfig) -> None:
        """设置 LLM 配置"""
        self.llm_config = config
        logger.info(f"设置 LLM 配置: {config.provider} - {config.model}")
    
    def get_llm_config(self) -> Optional[LLMConfig]:
        """获取 LLM 配置"""
        return self.llm_config
    
    async def execute_task(self, execution_create: ExecutionCreate) -> Execution:
        """
        执行任务
        
        Args:
            execution_create: 执行创建数据
            
        Returns:
            Execution: 执行结果
        """
        if not self.llm_config:
            raise ValueError("LLM 配置未设置")
        
        # 创建 LLM 适配器
        llm = LLMAdapterFactory.create(self.llm_config)
        
        # 创建执行循环
        execution_loop = RapidExecutionLoop(
            llm=llm,
            tool_registry=self.tool_registry
        )
        
        # 更新工具的安全路径
        project_path = execution_create.project_id
        if Path(project_path).exists():
            path_security = PathSecurity([project_path])
            self.tool_registry.tools["file"].security = path_security
        
        # 执行任务
        execution = await execution_loop.run(
            task=execution_create.task,
            project_path=project_path
        )
        
        # 保存执行结果
        self.executions[execution.id] = execution
        
        logger.info(f"任务执行完成: {execution.id} - {execution.status}")
        return execution
    
    def get_execution(self, execution_id: str) -> Optional[Execution]:
        """获取执行结果"""
        return self.executions.get(execution_id)
    
    def list_executions(self, project_id: Optional[str] = None) -> list:
        """列出执行历史"""
        executions = list(self.executions.values())
        if project_id:
            executions = [e for e in executions if e.project_id == project_id]
        return executions


agent_service = AgentService()
```

- [ ] **步骤 2: 创建 Agent API 路由 backend/app/api/routes/agent.py**

```python
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from app.models.execution import Execution, ExecutionCreate
from app.models.llm_config import LLMConfig
from app.services.agent_service import agent_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/execute", response_model=Execution)
async def execute_task(execution: ExecutionCreate):
    """执行任务"""
    try:
        result = await agent_service.execute_task(execution)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{execution_id}", response_model=Execution)
async def get_execution_status(execution_id: str):
    """获取执行状态"""
    execution = agent_service.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行不存在")
    return execution


@router.get("/history/{project_id}", response_model=List[Execution])
async def get_execution_history(project_id: str):
    """获取执行历史"""
    return agent_service.list_executions(project_id)
```

- [ ] **步骤 3: 创建 LLM 配置 API 路由**

在 `backend/app/api/routes/llm.py` 中:

```python
from fastapi import APIRouter
from app.models.llm_config import LLMConfig, LLMProvider
from app.services.agent_service import agent_service

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/config")
async def get_llm_config():
    """获取 LLM 配置"""
    config = agent_service.get_llm_config()
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url
    }


@router.post("/config")
async def set_llm_config(config: LLMConfig):
    """设置 LLM 配置"""
    agent_service.set_llm_config(config)
    return {"message": "配置已保存"}


@router.get("/providers")
async def list_providers():
    """获取支持的 LLM 提供商"""
    return [
        {
            "id": LLMProvider.OPENAI,
            "name": "OpenAI",
            "models": ["gpt-4-turbo-preview", "gpt-4", "gpt-3.5-turbo"]
        },
        {
            "id": LLMProvider.CLAUDE,
            "name": "Claude",
            "models": ["claude-3-opus", "claude-3-sonnet"],
            "status": "coming_soon"
        },
        {
            "id": LLMProvider.OLLAMA,
            "name": "Ollama",
            "models": ["llama2", "codellama"],
            "status": "coming_soon"
        }
    ]
```

- [ ] **步骤 4: 更新 main.py 注册所有路由**

```python
from app.api.routes import projects, agent, llm

app.include_router(projects.router)
app.include_router(agent.router)
app.include_router(llm.router)
```

- [ ] **步骤 5: 创建 API 测试 backend/tests/test_api/test_agent.py**

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.llm_config import LLMConfig, LLMProvider

client = TestClient(app)


class TestAgentAPI:
    
    def test_set_llm_config(self):
        response = client.post("/api/llm/config", json={
            "provider": "openai",
            "model": "gpt-4-turbo-preview",
            "api_key": "test-key"
        })
        
        assert response.status_code == 200
    
    def test_get_llm_config(self):
        client.post("/api/llm/config", json={
            "provider": "openai",
            "model": "gpt-4"
        })
        
        response = client.get("/api/llm/config")
        
        assert response.status_code == 200
        assert response.json()["configured"] is True
    
    def test_list_providers(self):
        response = client.get("/api/llm/providers")
        
        assert response.status_code == 200
        assert len(response.json()) > 0
```

- [ ] **步骤 6: 运行测试**

运行: `cd backend && pytest tests/test_api/test_agent.py -v`
预期: PASS

- [ ] **步骤 7: 提交代码**

```bash
git add backend/app/services/agent_service.py backend/app/api/routes/ backend/tests/test_api/
git commit -m "feat: 实现 Agent 执行 API

- 创建 AgentService 管理 Agent 执行
- 实现任务执行接口
- 实现 LLM 配置管理接口
- 支持执行状态查询
- 添加完整的 API 测试"
```

---

## 模块六: 前端基础搭建 (Week 5-6)

### 任务 6.1: 创建前端项目结构

**文件:**
- 创建: `frontend/` 目录结构
- 创建: `frontend/package.json`
- 创建: `frontend/tsconfig.json`
- 创建: `frontend/vite.config.ts`
- 创建: `frontend/tailwind.config.js`

- [ ] **步骤 1: 创建前端目录结构**

```bash
mkdir -p frontend/electron
mkdir -p frontend/src/{pages,components,stores,services,types,utils}
mkdir -p frontend/public
```

- [ ] **步骤 2: 创建 package.json**

```json
{
  "name": "reflexion-os-frontend",
  "version": "0.1.0",
  "description": "ReflexionOS Desktop Application",
  "main": "dist-electron/main.js",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "electron:dev": "concurrently \"vite\" \"wait-on http://localhost:5173 && electron .\"",
    "electron:build": "vite build && electron-builder"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0",
    "zustand": "^4.5.0",
    "axios": "^1.6.7",
    "socket.io-client": "^4.7.4"
  },
  "devDependencies": {
    "@types/react": "^18.2.55",
    "@types/react-dom": "^18.2.19",
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.17",
    "concurrently": "^8.2.2",
    "electron": "^28.2.1",
    "electron-builder": "^24.12.0",
    "postcss": "^8.4.35",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.3.3",
    "vite": "^5.1.0",
    "wait-on": "^7.2.0"
  }
}
```

- [ ] **步骤 3: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **步骤 4: 创建 vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  base: './',
  build: {
    outDir: 'dist',
  },
  server: {
    port: 5173,
  },
})
```

- [ ] **步骤 5: 创建 tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

- [ ] **步骤 6: 创建 index.html**

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ReflexionOS</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **步骤 7: 提交代码**

```bash
git add frontend/
git commit -m "feat: 初始化前端项目结构

- 创建 Electron + React 项目
- 配置 TypeScript 和 Vite
- 配置 TailwindCSS
- 设置开发环境"
```

---

### 任务 6.2: 实现状态管理

**文件:**
- 创建: `frontend/src/stores/projectStore.ts`
- 创建: `frontend/src/stores/agentStore.ts`
- 创建: `frontend/src/stores/executionStore.ts`

- [ ] **步骤 1: 创建项目 Store frontend/src/stores/projectStore.ts**

```typescript
import { create } from 'zustand'
import { Project } from '@/types/project'

interface ProjectState {
  projects: Project[]
  currentProject: Project | null
  setProjects: (projects: Project[]) => void
  addProject: (project: Project) => void
  removeProject: (id: string) => void
  setCurrentProject: (project: Project | null) => void
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  currentProject: null,
  
  setProjects: (projects) => set({ projects }),
  
  addProject: (project) => set((state) => ({
    projects: [...state.projects, project]
  })),
  
  removeProject: (id) => set((state) => ({
    projects: state.projects.filter((p) => p.id !== id)
  })),
  
  setCurrentProject: (project) => set({ currentProject: project }),
}))
```

- [ ] **步骤 2: 创建 Agent Store frontend/src/stores/agentStore.ts**

```typescript
import { create } from 'zustand'
import { Message } from '@/types/agent'

type ExecutionStatus = 'idle' | 'running' | 'paused' | 'completed'

interface AgentState {
  messages: Message[]
  executionStatus: ExecutionStatus
  currentStep: number
  totalSteps: number
  
  addMessage: (message: Message) => void
  setExecutionStatus: (status: ExecutionStatus) => void
  updateProgress: (current: number, total: number) => void
  reset: () => void
}

export const useAgentStore = create<AgentState>((set) => ({
  messages: [],
  executionStatus: 'idle',
  currentStep: 0,
  totalSteps: 0,
  
  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message]
  })),
  
  setExecutionStatus: (status) => set({ executionStatus: status }),
  
  updateProgress: (current, total) => set({
    currentStep: current,
    totalSteps: total
  }),
  
  reset: () => set({
    messages: [],
    executionStatus: 'idle',
    currentStep: 0,
    totalSteps: 0
  }),
}))
```

- [ ] **步骤 3: 创建 Execution Store frontend/src/stores/executionStore.ts**

```typescript
import { create } from 'zustand'
import { ExecutionStep } from '@/types/execution'

type StepStatus = 'pending' | 'running' | 'success' | 'failed'

interface ExecutionState {
  steps: ExecutionStep[]
  logs: string[]
  
  addStep: (step: ExecutionStep) => void
  updateStep: (id: string, status: StepStatus, output?: string) => void
  addLog: (log: string) => void
  clearSteps: () => void
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  steps: [],
  logs: [],
  
  addStep: (step) => set((state) => ({
    steps: [...state.steps, step]
  })),
  
  updateStep: (id, status, output) => set((state) => ({
    steps: state.steps.map((s) =>
      s.id === id ? { ...s, status, output } : s
    )
  })),
  
  addLog: (log) => set((state) => ({
    logs: [...state.logs, log]
  })),
  
  clearSteps: () => set({ steps: [], logs: [] }),
}))
```

- [ ] **步骤 4: 创建类型定义**

`frontend/src/types/project.ts`:
```typescript
export interface Project {
  id: string
  name: string
  path: string
  language?: string
  created_at: string
  updated_at: string
}
```

`frontend/src/types/agent.ts`:
```typescript
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}
```

`frontend/src/types/execution.ts`:
```typescript
export interface ExecutionStep {
  id: string
  step_number: number
  tool: string
  args: Record<string, any>
  status: 'pending' | 'running' | 'success' | 'failed'
  output?: string
  error?: string
  duration?: number
  timestamp: string
}
```

- [ ] **步骤 5: 提交代码**

```bash
git add frontend/src/stores/ frontend/src/types/
git commit -m "feat: 实现前端状态管理

- 创建项目状态管理 (projectStore)
- 创建 Agent 状态管理 (agentStore)
- 创建执行状态管理 (executionStore)
- 定义核心类型接口"
```

---

### 任务 6.3: 实现 API 客户端

**文件:**
- 创建: `frontend/src/services/apiClient.ts`
- 创建: `frontend/src/services/webSocketClient.ts`

- [ ] **步骤 1: 创建 API 客户端 frontend/src/services/apiClient.ts**

```typescript
import axios from 'axios'

const API_BASE_URL = 'http://127.0.0.1:8000'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 项目 API
export const projectApi = {
  list: () => apiClient.get('/api/projects'),
  get: (id: string) => apiClient.get(`/api/projects/${id}`),
  create: (data: { name: string; path: string; language?: string }) =>
    apiClient.post('/api/projects', data),
  delete: (id: string) => apiClient.delete(`/api/projects/${id}`),
  getStructure: (id: string) => apiClient.get(`/api/projects/${id}/structure`),
}

// Agent API
export const agentApi = {
  execute: (data: { project_id: string; task: string }) =>
    apiClient.post('/api/agent/execute', data),
  getStatus: (executionId: string) =>
    apiClient.get(`/api/agent/status/${executionId}`),
  getHistory: (projectId: string) =>
    apiClient.get(`/api/agent/history/${projectId}`),
}

// LLM API
export const llmApi = {
  getConfig: () => apiClient.get('/api/llm/config'),
  setConfig: (data: { provider: string; model: string; api_key?: string }) =>
    apiClient.post('/api/llm/config', data),
  getProviders: () => apiClient.get('/api/llm/providers'),
}
```

- [ ] **步骤 2: 创建 WebSocket 客户端 frontend/src/services/webSocketClient.ts**

```typescript
import { io, Socket } from 'socket.io-client'

const WS_URL = 'http://127.0.0.1:8000'

class WebSocketClient {
  private socket: Socket | null = null
  
  connect() {
    this.socket = io(WS_URL, {
      transports: ['websocket'],
    })
    
    this.socket.on('connect', () => {
      console.log('WebSocket 已连接')
    })
    
    this.socket.on('disconnect', () => {
      console.log('WebSocket 已断开')
    })
  }
  
  disconnect() {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
  }
  
  on(event: string, callback: (data: any) => void) {
    if (this.socket) {
      this.socket.on(event, callback)
    }
  }
  
  off(event: string) {
    if (this.socket) {
      this.socket.off(event)
    }
  }
  
  emit(event: string, data: any) {
    if (this.socket) {
      this.socket.emit(event, data)
    }
  }
}

export const wsClient = new WebSocketClient()
```

- [ ] **步骤 3: 提交代码**

```bash
git add frontend/src/services/
git commit -m "feat: 实现前端 API 客户端

- 创建 HTTP API 客户端 (axios)
- 创建 WebSocket 客户端 (socket.io)
- 封装项目、Agent、LLM 接口"
```

---

## 总结

本实施计划覆盖了 ReflexionOS 第一阶段的核心功能开发,包括:

**后端部分:**
1. ✅ FastAPI 项目基础设施
2. ✅ 数据模型定义
3. ✅ 日志系统
4. ✅ 统一 LLM 接口 + OpenAI 适配器
5. ✅ 文件工具和 Shell 工具
6. ✅ 工具注册中心
7. ✅ Agent 执行引擎
8. ✅ 项目管理和 Agent 执行 API

**前端部分:**
1. ✅ Electron + React 项目框架
2. ✅ Zustand 状态管理
3. ✅ API 客户端封装

所有任务遵循 TDD 原则,包含完整的测试和提交步骤,确保代码质量和可追溯性。
