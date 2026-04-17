# ReflexionOS 设计方案

> Status: Current primary design document.
> Use this file for product and architecture updates.
> Historical plans and reports under `docs/superpowers/plans/` and `docs/superpowers/status/` are reference only.

**版本**: v1.0  
**日期**: 2026-04-15  
**状态**: 已批准

---

## 一、项目概述

### 1.1 项目定位

ReflexionOS 是一个类似 Codex / Cursor 的本地执行型 Agent 桌面应用,具备:

- 自动读写代码
- 基于 diff 的精确修改(Patch)
- 自动运行命令(测试/构建)
- 错误驱动的自修复能力(Self-Debug Loop)
- 高速迭代执行(非图结构)

### 1.2 核心思想

> 从「规划驱动」转向「执行驱动」

```
小步执行 → 获取反馈 → 自动修复 → 收敛结果
```

### 1.3 设计目标

- 构建桌面端Agent应用,支持多项目并发管理
- 支持多种LLM提供商(OpenAI、Claude、Ollama等)
- 提供直观的执行时间线界面
- 支持代码审查和执行干预
- 预留外部应用接入能力(QQ、飞书等)

---

## 二、整体架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│              ReflexionOS Desktop Application             │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │     Electron Shell (主进程)                    │    │
│  │  ┌──────────────────────────────────────────┐  │    │
│  │  │  - FastAPI进程管理                       │  │    │
│  │  │  - IPC通信桥接                           │  │    │
│  │  │  - 项目配置持久化                        │  │    │
│  │  │  - 系统托盘集成                          │  │    │
│  │  └──────────────────────────────────────────┘  │    │
│  └────────────────────────────────────────────────┘    │
│                          │                              │
│                          │ IPC                          │
│                          ▼                              │
│  ┌────────────────────────────────────────────────┐    │
│  │     React Frontend (渲染进程)                 │    │
│  │  ┌──────────────────────────────────────────┐  │    │
│  │  │  - 项目管理界面                          │  │    │
│  │  │  - Agent对话界面                         │  │    │
│  │  │  - 执行监控面板                          │  │    │
│  │  │  - 代码审查视图                          │  │    │
│  │  └──────────────────────────────────────────┘  │    │
│  └────────────────────────────────────────────────┘    │
│                          │                              │
│                          │ HTTP/WebSocket               │
│                          ▼                              │
│  ┌────────────────────────────────────────────────┐    │
│  │     FastAPI Backend (子进程)                  │    │
│  │  ┌──────────────────────────────────────────┐  │    │
│  │  │  - Agent执行引擎                         │  │    │
│  │  │  - 自研LLM适配层                         │  │    │
│  │  │  - 工具注册中心                          │  │    │
│  │  │  - 文件系统操作                          │  │    │
│  │  └──────────────────────────────────────────┘  │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
                           ▲
                           │
                    ┌──────┴──────┐
                    │ API Gateway │  ← 预留扩展点(第二期)
                    │   (可选)    │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
        ┌───▼───┐      ┌───▼───┐      ┌───▼───┐
        │   QQ  │      │ 飞书  │      │ 其他  │
        │  Bot  │      │  Bot  │      │ App   │
        └───────┘      └───────┘      └───────┘
```

### 2.2 技术栈

**前端技术栈:**
- Electron: 桌面应用框架
- React 18: UI框架
- TypeScript: 类型安全
- Zustand: 状态管理
- TailwindCSS: 样式框架
- Monaco Editor: 代码编辑器
- Socket.io-client: WebSocket通信

**后端技术栈:**
- FastAPI: Web框架
- Python 3.11+: 运行时
- 自研LLM适配层: 统一多模型接口
- Pydantic: 数据验证
- Uvicorn: ASGI服务器
- python-socketio: WebSocket支持

**通信协议:**
- IPC: Electron主进程↔渲染进程
- HTTP/REST: 前端↔后端API
- WebSocket: 实时状态推送

### 2.3 扩展性设计

**Gateway扩展点(第二期):**
- 预留统一API Gateway接口
- 支持WebSocket和Webhook两种接入方式
- 统一鉴权和会话管理
- 第一期不做实现,仅预留架构扩展点

---

## 三、后端架构设计

### 3.1 分层架构

```
┌─────────────────────────────────────────────────────┐
│              API Layer (接口层)                     │
│  - RESTful API Endpoints                            │
│  - WebSocket Handlers                               │
│  - Request Validation                               │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│           Service Layer (服务层)                    │
│  - AgentService: Agent生命周期管理                  │
│  - ProjectService: 项目管理                         │
│  - ExecutionService: 执行流程控制                   │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│          Execution Layer (执行层)                   │
│  - RapidExecutionLoop: 快速执行循环                 │
│  - ActionExecutor: 工具调用执行器                   │
│  - ContextManager: 上下文管理                       │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│            Tool Layer (工具层)                      │
│  - FileTool: 文件读写                               │
│  - PatchTool: Diff编辑                              │
│  - ShellTool: 命令执行                              │
│  - SearchTool: 代码搜索                             │
│  - GitTool: Git操作                                 │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│           LLM Adapter Layer (LLM适配层)             │
│  - UniversalLLMInterface (统一接口)                 │
│  - OpenAIAdapter                                    │
│  - ClaudeAdapter (预留)                             │
│  - OllamaAdapter (预留)                             │
└─────────────────────────────────────────────────────┘
```

### 3.2 核心模块设计

#### 3.2.1 Agent执行引擎

```python
class RapidExecutionLoop:
    """
    核心执行循环
    - 接收任务
    - 构建提示词
    - 调用LLM决策
    - 执行工具
    - 处理反馈
    - 自动修复
    """
    
    async def run(self, task: str, context: ExecutionContext):
        for step in range(MAX_STEPS):
            action = await self.decide_action(context)
            
            if action.type == "finish":
                return action.answer
            
            result = await self.execute_action(action)
            context.update(action, result)
            
            if result.error:
                await self.handle_error(context, result)
```

#### 3.2.2 自研LLM适配层

```python
class UniversalLLMInterface(ABC):
    """统一LLM接口"""
    
    @abstractmethod
    async def complete(self, messages: List[Message]) -> str:
        """同步补全"""
        pass
    
    @abstractmethod
    async def stream_complete(self, messages: List[Message]) -> AsyncIterator[str]:
        """流式补全"""
        pass

class LLMAdapterFactory:
    """适配器工厂"""
    
    @staticmethod
    def create(config: LLMConfig) -> UniversalLLMInterface:
        if config.provider == "openai":
            return OpenAIAdapter(config)
        elif config.provider == "claude":
            return ClaudeAdapter(config)
        elif config.provider == "ollama":
            return OllamaAdapter(config)
```

#### 3.2.3 工具注册中心

```python
class ToolRegistry:
    """工具注册和管理"""
    
    def __init__(self):
        self.tools = {}
        
    def register(self, tool: Tool):
        self.tools[tool.name] = tool
        
    async def execute(self, name: str, args: dict) -> ToolResult:
        tool = self.tools.get(name)
        if not tool:
            raise ToolNotFoundError(name)
        return await tool.execute(args)
```

#### 3.2.4 Prompt 管理系统

```python
from typing import List, Dict, Any
from string import Template


class PromptTemplate:
    """Prompt 模板"""
    
    def __init__(self, name: str, template: str, variables: List[str]):
        self.name = name
        self.template = Template(template)
        self.variables = variables
    
    def render(self, **kwargs) -> str:
        """渲染模板"""
        return self.template.safe_substitute(**kwargs)


class PromptManager:
    """Prompt 管理器"""
    
    def __init__(self):
        self.templates: Dict[str, PromptTemplate] = {}
        self._load_default_templates()
    
    def _load_default_templates(self):
        """加载默认模板"""
        # System Prompt
        self.register_template(
            name="system",
            template="""You are an autonomous coding agent working in a local workspace.

You must:
- Solve tasks step by step using tools
- Prefer minimal edits (use apply_patch)
- Automatically fix errors
- Verify results via shell commands

Rules:
- Output MUST be valid JSON
- No explanation outside JSON
- Keep thought short

Available tools:
$tool_list""",
            variables=["tool_list"]
        )
        
        # Step Prompt
        self.register_template(
            name="step",
            template="""Task: $task

$history_context

$error_context

Workspace:
$workspace_context

What is your next action? (Output JSON only)""",
            variables=["task", "history_context", "error_context", "workspace_context"]
        )
        
        # Error Prompt
        self.register_template(
            name="error",
            template="""The previous action failed.

Tool: $tool
Error: $error

Relevant code:
$code_snippet

Fix the issue using available tools. Do not repeat the same action.""",
            variables=["tool", "error", "code_snippet"]
        )
    
    def register_template(self, name: str, template: str, variables: List[str]):
        """注册模板"""
        self.templates[name] = PromptTemplate(name, template, variables)
    
    def get_template(self, name: str) -> PromptTemplate:
        """获取模板"""
        if name not in self.templates:
            raise ValueError(f"Template not found: {name}")
        return self.templates[name]
    
    def get_system_prompt(self, tools: List[Any]) -> str:
        """获取系统提示"""
        tool_schemas = [tool.get_schema() for tool in tools]
        import json
        tool_list = json.dumps(tool_schemas, indent=2, ensure_ascii=False)
        
        return self.get_template("system").render(tool_list=tool_list)
    
    def get_step_prompt(self, context: 'ExecutionContext') -> str:
        """获取步骤提示"""
        history_context = self._build_history_context(context)
        error_context = context.metadata.get("last_error", "")
        workspace_context = context.get_workspace_context()
        
        return self.get_template("step").render(
            task=context.task,
            history_context=history_context,
            error_context=error_context,
            workspace_context=workspace_context
        )
    
    def get_error_prompt(self, error: str, tool: str, code_snippet: str = "") -> str:
        """获取错误提示"""
        return self.get_template("error").render(
            tool=tool,
            error=error,
            code_snippet=code_snippet
        )
    
    def _build_history_context(self, context: 'ExecutionContext') -> str:
        """构建历史上下文"""
        recent = context.get_recent_history(3)
        if not recent:
            return ""
        
        lines = ["Recent actions:"]
        for i, item in enumerate(recent, 1):
            action = item["action"]
            lines.append(f"{i}. {action.type}: {action.tool or 'finish'}")
            if item.get("result"):
                lines.append(f"   Result: {item['result'][:100]}")
        
        return "\n".join(lines)
```

#### 3.2.5 Skills 系统

```python
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class Skill(BaseModel):
    """技能定义"""
    name: str
    description: str
    tools: List[str]
    prompt_template: str
    examples: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}


class SkillRegistry:
    """技能注册中心"""
    
    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self._load_default_skills()
    
    def _load_default_skills(self):
        """加载默认技能"""
        # Bug 修复技能
        self.register_skill(Skill(
            name="fix_bug",
            description="修复代码中的 bug",
            tools=["file", "shell"],
            prompt_template="""Fix the bug in the code.

Steps:
1. Read the relevant file
2. Identify the bug
3. Apply the fix using minimal changes
4. Run tests to verify the fix

Bug description: $bug_description""",
            examples=[
                {
                    "input": "Fix login validation bug",
                    "output": "Successfully fixed the validation logic"
                }
            ]
        ))
        
        # 代码重构技能
        self.register_skill(Skill(
            name="refactor",
            description="重构代码以提高质量",
            tools=["file", "shell"],
            prompt_template="""Refactor the code to improve quality.

Focus on:
- Code readability
- Performance optimization
- Removing code duplication
- Following best practices

Refactoring goal: $goal""",
            examples=[
                {
                    "input": "Refactor database queries",
                    "output": "Optimized query performance by 50%"
                }
            ]
        ))
        
        # 测试生成技能
        self.register_skill(Skill(
            name="generate_tests",
            description="为代码生成测试用例",
            tools=["file", "shell"],
            prompt_template="""Generate comprehensive tests for the code.

Test types to include:
- Unit tests
- Edge cases
- Error handling tests

Target: $target""",
            examples=[
                {
                    "input": "Generate tests for UserService",
                    "output": "Created 15 test cases with 95% coverage"
                }
            ]
        ))
    
    def register_skill(self, skill: Skill):
        """注册技能"""
        self.skills[skill.name] = skill
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self.skills.get(name)
    
    def list_skills(self) -> List[Skill]:
        """列出所有技能"""
        return list(self.skills.values())
    
    def get_skill_prompt(self, name: str, **kwargs) -> str:
        """获取技能提示"""
        skill = self.get_skill(name)
        if not skill:
            raise ValueError(f"Skill not found: {name}")
        
        from string import Template
        template = Template(skill.prompt_template)
        return template.safe_substitute(**kwargs)
```

#### 3.2.6 MCP (Model Context Protocol) 支持

```python
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
import asyncio
import json


class MCPTool(BaseModel):
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_id: str


class MCPServer(ABC):
    """MCP 服务器接口"""
    
    @abstractmethod
    async def connect(self) -> bool:
        """连接到 MCP 服务器"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass
    
    @abstractmethod
    async def list_tools(self) -> List[MCPTool]:
        """列出可用工具"""
        pass
    
    @abstractmethod
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """调用工具"""
        pass


class StdioMCPServer(MCPServer):
    """基于 stdio 的 MCP 服务器实现"""
    
    def __init__(self, server_id: str, command: str, args: List[str] = None):
        self.server_id = server_id
        self.command = command
        self.args = args or []
        self.process: Optional[asyncio.subprocess.Process] = None
        self.tools: List[MCPTool] = []
    
    async def connect(self) -> bool:
        """启动 MCP 服务器进程"""
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 发送初始化请求
            await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {}
            })
            
            # 获取工具列表
            self.tools = await self.list_tools()
            
            return True
        except Exception as e:
            print(f"Failed to connect to MCP server: {e}")
            return False
    
    async def disconnect(self):
        """停止服务器进程"""
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None
    
    async def list_tools(self) -> List[MCPTool]:
        """获取工具列表"""
        response = await self._send_request("tools/list", {})
        
        tools = []
        for tool_data in response.get("tools", []):
            tools.append(MCPTool(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {}),
                server_id=self.server_id
            ))
        
        return tools
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """调用工具"""
        response = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        
        return response.get("content", [])
    
    async def _send_request(self, method: str, params: Dict[str, Any]) -> Dict:
        """发送 JSON-RPC 请求"""
        if not self.process:
            raise RuntimeError("MCP server not connected")
        
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        
        # 发送请求
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        await self.process.stdin.drain()
        
        # 读取响应
        response_line = await self.process.stdout.readline()
        response = json.loads(response_line.decode())
        
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        
        return response.get("result", {})


class MCPManager:
    """MCP 管理器"""
    
    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self.tools: Dict[str, MCPTool] = {}
    
    async def register_server(self, server: MCPServer) -> bool:
        """注册 MCP 服务器"""
        if await server.connect():
            self.servers[server.server_id] = server
            
            # 注册工具
            for tool in await server.list_tools():
                self.tools[tool.name] = tool
            
            return True
        return False
    
    async def unregister_server(self, server_id: str):
        """注销服务器"""
        if server_id in self.servers:
            server = self.servers[server_id]
            await server.disconnect()
            
            # 移除工具
            self.tools = {
                k: v for k, v in self.tools.items() 
                if v.server_id != server_id
            }
            
            del self.servers[server_id]
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """调用 MCP 工具"""
        if name not in self.tools:
            raise ValueError(f"MCP tool not found: {name}")
        
        tool = self.tools[name]
        server = self.servers[tool.server_id]
        
        return await server.call_tool(name, arguments)
    
    def list_tools(self) -> List[MCPTool]:
        """列出所有 MCP 工具"""
        return list(self.tools.values())
```

#### 3.2.7 更新后的分层架构

```
┌─────────────────────────────────────────────────────┐
│              API Layer (接口层)                     │
│  - RESTful API Endpoints                            │
│  - WebSocket Handlers                               │
│  - Request Validation                               │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│           Service Layer (服务层)                    │
│  - AgentService: Agent生命周期管理                  │
│  - ProjectService: 项目管理                         │
│  - ExecutionService: 执行流程控制                   │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│          Execution Layer (执行层)                   │
│  - RapidExecutionLoop: 快速执行循环                 │
│  - ActionExecutor: 工具调用执行器                   │
│  - ContextManager: 上下文管理                       │
│  - PromptManager: Prompt管理 ✨ NEW                 │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│          Orchestration Layer (编排层) ✨ NEW        │
│  - SkillRegistry: 技能注册与管理                    │
│  - MCPManager: MCP协议支持                          │
│  - WorkflowEngine: 工作流引擎 (第二阶段)            │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│            Tool Layer (工具层)                      │
│  - FileTool: 文件读写                               │
│  - PatchTool: Diff编辑                              │
│  - ShellTool: 命令执行                              │
│  - SearchTool: 代码搜索                             │
│  - GitTool: Git操作                                 │
│  - MCPTools: MCP外部工具 ✨ NEW                     │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│           LLM Adapter Layer (LLM适配层)             │
│  - UniversalLLMInterface (统一接口)                 │
│  - OpenAIAdapter                                    │
│  - ClaudeAdapter (预留)                             │
│  - OllamaAdapter (预留)                             │
└─────────────────────────────────────────────────────┘
```

---

## 3.3 核心支撑系统

### 3.3.1 持久化存储层 🔴 P0 (MVP必须)

**优先级:** 🔴 高 - MVP 必须实现

**问题:**
- 执行历史无法持久化
- 项目配置重启后丢失
- 无法追溯问题和优化

**架构设计:**

```python
from sqlalchemy import create_engine, Column, String, DateTime, JSON, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()


class ProjectModel(Base):
    """项目数据模型"""
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    language = Column(String)
    config = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ExecutionModel(Base):
    """执行记录模型"""
    __tablename__ = "executions"
    
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False)
    task = Column(String, nullable=False)
    status = Column(String, default="pending")
    steps = Column(JSON, default=[])
    result = Column(String)
    total_duration = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime)


class ConversationModel(Base):
    """对话记录模型"""
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True)
    execution_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)


class Database:
    """数据库管理"""
    
    def __init__(self, db_path: str = "reflexion.db"):
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        return self.Session()


class ProjectRepository:
    """项目仓储"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def save(self, project: Project) -> Project:
        with self.db.get_session() as session:
            model = ProjectModel(**project.dict())
            session.add(model)
            session.commit()
            return project
    
    def get(self, project_id: str) -> Optional[Project]:
        with self.db.get_session() as session:
            model = session.query(ProjectModel).filter_by(id=project_id).first()
            return Project.from_orm(model) if model else None
    
    def list_all(self) -> List[Project]:
        with self.db.get_session() as session:
            models = session.query(ProjectModel).all()
            return [Project.from_orm(m) for m in models]


class ExecutionRepository:
    """执行记录仓储"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def save(self, execution: Execution) -> Execution:
        with self.db.get_session() as session:
            model = ExecutionModel(**execution.dict())
            session.add(model)
            session.commit()
            return execution
    
    def get_by_project(self, project_id: str, limit: int = 10) -> List[Execution]:
        with self.db.get_session() as session:
            models = session.query(ExecutionModel)\
                .filter_by(project_id=project_id)\
                .order_by(ExecutionModel.created_at.desc())\
                .limit(limit)\
                .all()
            return [Execution.from_orm(m) for m in models]
```

**目录结构:**
```
backend/app/storage/
├── __init__.py
├── database.py           # 数据库连接
├── models.py             # ORM 模型
├── repositories/
│   ├── __init__.py
│   ├── project_repo.py
│   ├── execution_repo.py
│   └── conversation_repo.py
└── migrations/           # Alembic 迁移
    └── versions/
```

**技术选型:**
- SQLite (轻量级,桌面应用首选)
- SQLAlchemy (ORM 框架)
- Alembic (数据库迁移)

---

### 3.3.2 配置管理系统 🔴 P0 (MVP必须)

**优先级:** 🔴 高 - MVP 必须实现

**问题:**
- LLM 配置无法动态修改
- 用户偏好无法持久化
- 缺少配置验证机制

**架构设计:**

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from pathlib import Path
import json


class LLMConfig(BaseModel):
    """LLM 配置"""
    provider: str = "openai"
    model: str = "gpt-4-turbo-preview"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)


class ExecutionConfig(BaseModel):
    """执行配置"""
    max_steps: int = Field(default=50, ge=1, le=200)
    max_file_size: int = Field(default=10485760)  # 10MB
    max_execution_time: int = Field(default=600)  # 10分钟
    enable_auto_fix: bool = True
    enable_streaming: bool = True


class UIConfig(BaseModel):
    """界面配置"""
    theme: str = "light"
    font_size: int = 14
    auto_scroll: bool = True
    show_timestamps: bool = True


class AppConfig(BaseModel):
    """应用总配置"""
    llm: LLMConfig = LLMConfig()
    execution: ExecutionConfig = ExecutionConfig()
    ui: UIConfig = UIConfig()
    
    class Config:
        json_encoders = {
            Path: str
        }


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> AppConfig:
        """加载配置"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return AppConfig(**data)
        return AppConfig()
    
    def save_config(self):
        """保存配置"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config.dict(), f, indent=2, ensure_ascii=False)
    
    def update_llm_config(self, llm_config: LLMConfig):
        """更新 LLM 配置"""
        self.config.llm = llm_config
        self.save_config()
    
    def update_execution_config(self, execution_config: ExecutionConfig):
        """更新执行配置"""
        self.config.execution = execution_config
        self.save_config()
    
    def update_ui_config(self, ui_config: UIConfig):
        """更新界面配置"""
        self.config.ui = ui_config
        self.save_config()
    
    def reset_to_default(self):
        """重置为默认配置"""
        self.config = AppConfig()
        self.save_config()
```

**配置文件示例 (config.json):**
```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4-turbo-preview",
    "api_key": "sk-...",
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "execution": {
    "max_steps": 50,
    "max_file_size": 10485760,
    "max_execution_time": 600,
    "enable_auto_fix": true,
    "enable_streaming": true
  },
  "ui": {
    "theme": "light",
    "font_size": 14,
    "auto_scroll": true,
    "show_timestamps": true
  }
}
```

---

### 3.3.3 Patch 工具 🔴 P0 (MVP必须)

**优先级:** 🔴 高 - 核心功能

**问题:**
- 无法进行精确的代码修改
- 会退化为全文替换
- 容易出错

**架构设计:**

```python
import difflib
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class Hunk:
    """Diff Hunk"""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str]


@dataclass
class PatchResult:
    """Patch 结果"""
    success: bool
    message: str
    applied_hunks: int = 0
    rejected_hunks: int = 0


class DiffParser:
    """Unified Diff 解析器"""
    
    def parse(self, diff_text: str) -> List[Hunk]:
        """解析 Unified Diff"""
        hunks = []
        lines = diff_text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 查找 hunk 头
            if line.startswith('@@'):
                # 解析 @@ -old_start,old_count +new_start,new_count @@
                import re
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
                        if lines[i].startswith('+') or lines[i].startswith('-') or lines[i].startswith(' '):
                            hunk.lines.append(lines[i])
                        i += 1
                    
                    hunks.append(hunk)
            else:
                i += 1
        
        return hunks


class PatchTool(BaseTool):
    """Patch 工具"""
    
    def __init__(self, security: PathSecurity):
        self.security = security
        self.parser = DiffParser()
    
    @property
    def name(self) -> str:
        return "patch"
    
    @property
    def description(self) -> str:
        return "应用 Unified Diff 格式的补丁"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """执行 Patch"""
        patch_text = args.get("patch")
        
        if not patch_text:
            return ToolResult(success=False, error="缺少 patch 参数")
        
        try:
            # 解析 diff
            hunks = self.parser.parse(patch_text)
            
            if not hunks:
                return ToolResult(success=False, error="无法解析 Diff")
            
            # 获取文件路径
            file_path = self._extract_file_path(patch_text)
            if not file_path:
                return ToolResult(success=False, error="无法提取文件路径")
            
            # 验证路径
            file_path = self.security.validate_write_path(file_path)
            
            # 读取原文件
            with open(file_path, 'r', encoding='utf-8') as f:
                original_lines = f.readlines()
            
            # 应用 Patch
            result = self._apply_hunks(original_lines, hunks)
            
            if result.success:
                # 写入修改后的文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(result.lines)
                
                return ToolResult(
                    success=True,
                    output=f"成功应用 {result.applied_hunks} 个 Hunk",
                    data={"file": file_path}
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"应用失败: {result.message}"
                )
        
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    def _extract_file_path(self, diff_text: str) -> Optional[str]:
        """从 Diff 中提取文件路径"""
        lines = diff_text.split('\n')
        
        for line in lines:
            if line.startswith('+++ '):
                # +++ b/path/to/file
                path = line[4:].strip()
                if path.startswith('b/'):
                    path = path[2:]
                return path
        
        return None
    
    def _apply_hunks(self, original_lines: List[str], hunks: List[Hunk]) -> PatchResult:
        """应用 Hunk"""
        applied = 0
        rejected = 0
        result_lines = original_lines[:]
        
        # 从后往前应用,避免行号偏移
        for hunk in reversed(hunks):
            # 验证上下文
            start = hunk.old_start - 1  # 转为 0-based
            context_match = True
            
            # TODO: 实现完整的上下文验证和 Patch 应用
            
            if context_match:
                # 应用修改
                # TODO: 实现具体的应用逻辑
                applied += 1
            else:
                rejected += 1
        
        return PatchResult(
            success=rejected == 0,
            message=f"已应用 {applied} 个,拒绝 {rejected} 个",
            applied_hunks=applied,
            rejected_hunks=rejected
        )
```

---

### 3.3.4 WebSocket 实时通信 🔴 P0 (MVP必须)

**优先级:** 🔴 高 - 实时性要求

**后端实现:**

```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, execution_id: str):
        """接受连接"""
        await websocket.accept()
        if execution_id not in self.active_connections:
            self.active_connections[execution_id] = set()
        self.active_connections[execution_id].add(websocket)
        logger.info(f"WebSocket connected: {execution_id}")
    
    def disconnect(self, websocket: WebSocket, execution_id: str):
        """断开连接"""
        if execution_id in self.active_connections:
            self.active_connections[execution_id].discard(websocket)
            if not self.active_connections[execution_id]:
                del self.active_connections[execution_id]
        logger.info(f"WebSocket disconnected: {execution_id}")
    
    async def send_event(self, execution_id: str, event_type: str, data: dict):
        """发送事件"""
        if execution_id in self.active_connections:
            message = json.dumps({
                "type": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat()
            })
            
            for connection in self.active_connections[execution_id]:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Failed to send message: {e}")


manager = ConnectionManager()


@router.websocket("/ws/{execution_id}")
async def websocket_endpoint(websocket: WebSocket, execution_id: str):
    """WebSocket 端点"""
    await manager.connect(websocket, execution_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            # 处理客户端消息
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, execution_id)


# 在执行循环中使用
class RapidExecutionLoop:
    async def run(self, task: str, context: ExecutionContext) -> Execution:
        execution_id = context.execution_id
        
        # 发送开始事件
        await manager.send_event(execution_id, "execution:start", {
            "task": task
        })
        
        for step in range(self.max_steps):
            # 发送步骤事件
            await manager.send_event(execution_id, "execution:step", {
                "step_number": step,
                "status": "running"
            })
            
            # 执行步骤...
            
            # 发送完成事件
            await manager.send_event(execution_id, "execution:complete", {
                "result": result
            })
```

---

### 3.3.5 错误处理和恢复机制 🟡 P1 (第二阶段)

**优先级:** 🟡 中 - 第二阶段完善

**架构设计:**

```python
from enum import Enum
from typing import Optional, Callable
from dataclasses import dataclass


class ErrorCategory(Enum):
    """错误分类"""
    LLM_ERROR = "llm_error"
    TOOL_ERROR = "tool_error"
    SYSTEM_ERROR = "system_error"
    NETWORK_ERROR = "network_error"
    SECURITY_ERROR = "security_error"


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"          # 可忽略
    MEDIUM = "medium"    # 需要处理
    HIGH = "high"        # 阻塞执行
    CRITICAL = "critical" # 系统级错误


@dataclass
class AgentError:
    """Agent 错误"""
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    recoverable: bool
    retry_count: int = 0
    max_retries: int = 3


class ErrorHandler:
    """错误处理器"""
    
    def __init__(self):
        self.strategies = {
            ErrorCategory.LLM_ERROR: self._handle_llm_error,
            ErrorCategory.TOOL_ERROR: self._handle_tool_error,
            ErrorCategory.NETWORK_ERROR: self._handle_network_error,
        }
    
    async def handle(self, error: AgentError, context: ExecutionContext) -> RecoveryAction:
        """处理错误"""
        strategy = self.strategies.get(error.category, self._default_handler)
        return await strategy(error, context)
    
    async def _handle_llm_error(self, error: AgentError, context: ExecutionContext) -> RecoveryAction:
        """处理 LLM 错误"""
        if "rate_limit" in error.message.lower():
            return RecoveryAction(
                strategy="wait_and_retry",
                wait_time=60,
                message="遇到速率限制,等待后重试"
            )
        
        if "timeout" in error.message.lower():
            return RecoveryAction(
                strategy="retry",
                max_retries=3,
                message="请求超时,重试"
            )
        
        if "content_filter" in error.message.lower():
            return RecoveryAction(
                strategy="abort",
                message="内容被过滤,终止执行"
            )
        
        return RecoveryAction(strategy="ask_user", message="LLM 错误,需要用户干预")
    
    async def _handle_tool_error(self, error: AgentError, context: ExecutionContext) -> RecoveryAction:
        """处理工具错误"""
        # 工具错误的恢复策略
        pass
    
    async def _handle_network_error(self, error: AgentError, context: ExecutionContext) -> RecoveryAction:
        """处理网络错误"""
        return RecoveryAction(
            strategy="retry_with_backoff",
            max_retries=3,
            backoff_factor=2,
            message="网络错误,使用退避重试"
        )


@dataclass
class RecoveryAction:
    """恢复动作"""
    strategy: str
    message: str
    wait_time: Optional[int] = None
    max_retries: Optional[int] = None
    backoff_factor: Optional[float] = None
```

---

### 3.3.6 搜索和代码理解工具 🟡 P1 (第二阶段)

**优先级:** 🟡 中 - 提升能力

**架构设计:**

```python
import os
import re
from typing import List, Dict, Any
from pathlib import Path


class SearchResult:
    """搜索结果"""
    file_path: str
    line_number: int
    line_content: str
    context: List[str]


class SearchTool(BaseTool):
    """代码搜索工具"""
    
    @property
    def name(self) -> str:
        return "search"
    
    @property
    def description(self) -> str:
        return "在代码库中搜索文本"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """执行搜索"""
        query = args.get("query")
        path = args.get("path", ".")
        file_pattern = args.get("pattern", "*")
        
        results = []
        
        for root, dirs, files in os.walk(path):
            for file in files:
                if not file.endswith(('.py', '.js', '.ts', '.java', '.go')):
                    continue
                
                file_path = os.path.join(root, file)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    for i, line in enumerate(lines, 1):
                        if query.lower() in line.lower():
                            results.append(SearchResult(
                                file_path=file_path,
                                line_number=i,
                                line_content=line.strip(),
                                context=lines[max(0, i-3):i+2]
                            ))
                
                except Exception:
                    continue
        
        return ToolResult(
            success=True,
            data={"results": results, "count": len(results)}
        )


class ASTTool(BaseTool):
    """AST 分析工具 (第二阶段实现)"""
    
    @property
    def name(self) -> str:
        return "ast"
    
    @property
    def description(self) -> str:
        return "分析代码结构"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """AST 分析"""
        # TODO: 第二阶段实现
        pass
```

---

### 3.3.7 Git 工具集成 🟡 P1 (第二阶段)

**优先级:** 🟡 中 - 开发体验

**架构设计:**

```python
import subprocess
from typing import List, Optional


class GitTool(BaseTool):
    """Git 操作工具"""
    
    @property
    def name(self) -> str:
        return "git"
    
    @property
    def description(self) -> str:
        return "执行 Git 操作"
    
    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        """执行 Git 命令"""
        action = args.get("action")
        
        git_actions = {
            "status": self._git_status,
            "diff": self._git_diff,
            "log": self._git_log,
            "add": self._git_add,
            "commit": self._git_commit,
            "push": self._git_push,
            "pull": self._git_pull,
        }
        
        if action not in git_actions:
            return ToolResult(success=False, error=f"未知的 Git 操作: {action}")
        
        return await git_actions[action](args)
    
    async def _git_status(self, args: Dict[str, Any]) -> ToolResult:
        """查看状态"""
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=args.get("cwd", ".")
        )
        
        return ToolResult(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None
        )
    
    async def _git_commit(self, args: Dict[str, Any]) -> ToolResult:
        """提交更改"""
        message = args.get("message", "Auto commit by Agent")
        
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            cwd=args.get("cwd", ".")
        )
        
        return ToolResult(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None
        )
```

---

### 3.3.8 向量记忆/知识库 🟢 P2 (第三阶段)

**优先级:** 🟢 低 - 高级功能

**架构设计:**

```python
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings


class VectorStore:
    """向量存储"""
    
    def __init__(self, persist_directory: str = ".chroma"):
        self.client = chromadb.Client(Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_directory
        ))
        self.collection = self.client.get_or_create_collection("reflexion_memory")
    
    def add_document(self, text: str, metadata: Dict[str, Any] = None):
        """添加文档"""
        import uuid
        self.collection.add(
            documents=[text],
            metadatas=[metadata or {}],
            ids=[str(uuid.uuid4())]
        )
    
    def search(self, query: str, n_results: int = 5) -> List[Dict]:
        """搜索相似文档"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        return [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(results["documents"][0], results["metadatas"][0])
        ]


class KnowledgeBase:
    """知识库"""
    
    def __init__(self):
        self.vector_store = VectorStore()
    
    def add_execution_experience(self, execution: Execution):
        """添加执行经验"""
        # 将成功的执行转换为可检索的知识
        if execution.status == "completed":
            knowledge = f"Task: {execution.task}\nSolution: {execution.result}"
            self.vector_store.add_document(knowledge, {
                "type": "execution",
                "project_id": execution.project_id,
                "timestamp": execution.created_at.isoformat()
            })
    
    def retrieve_relevant_knowledge(self, task: str) -> List[str]:
        """检索相关知识"""
        results = self.vector_store.search(task)
        return [r["text"] for r in results]


class RetrievalSystem:
    """检索系统"""
    
    def __init__(self, knowledge_base: KnowledgeBase):
        self.kb = knowledge_base
    
    def augment_prompt(self, task: str, base_prompt: str) -> str:
        """增强 Prompt"""
        relevant_knowledge = self.kb.retrieve_relevant_knowledge(task)
        
        if relevant_knowledge:
            knowledge_text = "\n\n".join(relevant_knowledge)
            return f"{base_prompt}\n\nRelevant past experience:\n{knowledge_text}"
        
        return base_prompt
```

---

### 3.3.9 插件系统 🟢 P2 (第三阶段)

**优先级:** 🟢 低 - 扩展功能

**架构设计:**

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List


class Plugin(ABC):
    """插件基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """插件版本"""
        pass
    
    @abstractmethod
    def initialize(self, context: Dict[str, Any]):
        """初始化插件"""
        pass
    
    @abstractmethod
    def shutdown(self):
        """关闭插件"""
        pass


class PluginManager:
    """插件管理器"""
    
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
    
    def load_plugin(self, plugin_path: str):
        """加载插件"""
        # TODO: 实现插件加载
        pass
    
    def unload_plugin(self, plugin_name: str):
        """卸载插件"""
        if plugin_name in self.plugins:
            self.plugins[plugin_name].shutdown()
            del self.plugins[plugin_name]
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """获取插件"""
        return self.plugins.get(name)
    
    def list_plugins(self) -> List[str]:
        """列出所有插件"""
        return list(self.plugins.keys())
```

---

## 四、前端架构设计

### 4.1 整体结构

```
┌─────────────────────────────────────────────────────┐
│              Electron Application                    │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌───────────────────────────────────────────────┐  │
│  │         Main Process (主进程)                 │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │  - FastAPI进程启动/停止                 │  │  │
│  │  │  - IPC消息转发                          │  │  │
│  │  │  - 系统托盘                             │  │  │
│  │  │  - 文件对话框                           │  │  │
│  │  │  - 应用配置持久化                       │  │  │
│  │  └─────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────┘  │
│                         │                           │
│                         │ IPC                       │
│                         ▼                           │
│  ┌───────────────────────────────────────────────┐  │
│  │       Renderer Process (渲染进程)             │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │         React Application               │  │  │
│  │  │  ┌───────────────────────────────────┐  │  │  │
│  │  │  │    Pages                          │  │  │  │
│  │  │  │  - HomePage                      │  │  │  │
│  │  │  │  - AgentWorkspace                │  │  │  │
│  │  │  │  - SettingsPage                  │  │  │  │
│  │  │  └───────────────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────────────────┐  │  │  │
│  │  │  │    Components                     │  │  │  │
│  │  │  │  - ProjectManager                │  │  │  │
│  │  │  │  - ExecutionTimeline             │  │  │  │
│  │  │  │  - CodeReviewer                  │  │  │  │
│  │  │  │  - MonacoEditor                  │  │  │  │
│  │  │  └───────────────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────────────────┐  │  │  │
│  │  │  │    State Management (Zustand)     │  │  │  │
│  │  │  │  - projectStore                  │  │  │  │
│  │  │  │  - agentStore                    │  │  │  │
│  │  │  │  - executionStore                │  │  │  │
│  │  │  └───────────────────────────────────┘  │  │  │
│  │  │  ┌───────────────────────────────────┐  │  │  │
│  │  │  │    Services                       │  │  │  │
│  │  │  │  - APIClient                     │  │  │  │
│  │  │  │  - WebSocketClient               │  │  │  │
│  │  │  │  - IPCBridge                     │  │  │  │
│  │  │  └───────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### 4.2 核心页面设计

#### 4.2.1 HomePage (首页)

```
┌────────────────────────────────────────┐
│  项目列表                              │
│  ┌────────────────────────────────┐   │
│  │ [+] 新建项目                   │   │
│  └────────────────────────────────┘   │
│  ┌────────────────────────────────┐   │
│  │ 项目A  Python  最近修改: 1小时前│   │
│  │ [打开] [删除]                  │   │
│  └────────────────────────────────┘   │
│  ┌────────────────────────────────┐   │
│  │ 项目B  React   最近修改: 2天前  │   │
│  │ [打开] [删除]                  │   │
│  └────────────────────────────────┘   │
└────────────────────────────────────────┘
```

#### 4.2.2 AgentWorkspace (工作区页面 - 合并版)

**布局结构:**

```
┌─────────────────────────────────────────────────────────┐
│  项目: MyProject              [设置] [代码审查] [切换项目]│
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │        执行时间线 + 对话区域                    │    │
│  │  ┌───────────────────────────────────────────┐  │    │
│  │  │ User: 修复login函数的bug                  │  │    │
│  │  └───────────────────────────────────────────┘  │    │
│  │  ┌───────────────────────────────────────────┐  │    │
│  │  │ 🤖 Agent: 正在分析项目结构...             │  │    │
│  │  └───────────────────────────────────────────┘  │    │
│  │  ┌───────────────────────────────────────────┐  │    │
│  │  │ ▶ Step 1: read_file              ✅ 0.2s  │  │    │
│  │  │   📄 src/auth/login.py                    │  │    │
│  │  └───────────────────────────────────────────┘  │    │
│  │  ┌───────────────────────────────────────────┐  │    │
│  │  │ ▶ Step 2: apply_patch            ✅ 0.1s  │  │    │
│  │  │   📝 修改内容 (点击查看diff)              │  │    │
│  │  │   ┌─────────────────────────────────────┐ │  │    │
│  │  │   │ - def login(user):                 │ │  │    │
│  │  │   │ + def login(user, password):       │ │  │    │
│  │  │   └─────────────────────────────────────┘ │  │    │
│  │  └───────────────────────────────────────────┘  │    │
│  │  ┌───────────────────────────────────────────┐  │    │
│  │  │ ▶ Step 3: run_shell              🔄      │  │    │
│  │  │   💻 pytest tests/auth_test.py           │  │    │
│  │  │   ┌─────────────────────────────────────┐ │  │    │
│  │  │   │ Running tests...                   │ │  │    │
│  │  │   │ 2 passed, 0 failed                 │ │  │    │
│  │  │   └─────────────────────────────────────┘ │  │    │
│  │  └───────────────────────────────────────────┘  │    │
│  │  ┌───────────────────────────────────────────┐  │    │
│  │  │ ⏸️ Step 4: pending                       │  │    │
│  │  └───────────────────────────────────────────┘  │    │
│  │                                                   │    │
│  │  进度: 3/10 步骤   状态: 执行中  [暂停] [终止]   │    │
│  │                                                   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ [输入框...]                          [发送]     │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**交互特性:**

- **时间线展开/折叠**: 每个步骤可展开查看详细信息或折叠
- **实时滚动**: 新步骤自动滚动到视图中心
- **步骤状态标识**: ✅成功 🔄执行中 ❌失败 ⏸️待执行
- **内联Diff预览**: 代码修改直接在时间线中展示
- **日志流**: Shell输出实时流式显示
- **快速操作**: 暂停/继续/终止按钮固定在底部

#### 4.2.3 CodeReviewer (代码审查视图 - 独立弹窗)

```
┌────────────────────────────────────────┐
│  代码修改审查                    [×]   │
├────────────────────────────────────────┤
│  文件: src/auth/login.py               │
│  ┌────────────────────────────────┐   │
│  │ - def login(user):             │   │
│  │ + def login(user, password):   │   │
│  │ -   return True                │   │
│  │ +   if validate(user,password):│   │
│  │ +       return True            │   │
│  │ +   return False               │   │
│  └────────────────────────────────┘   │
│  [接受修改] [拒绝] [手动编辑]          │
└────────────────────────────────────────┘
```

### 4.3 状态管理设计

```typescript
// projectStore.ts
interface ProjectStore {
  projects: Project[]
  currentProject: Project | null
  addProject: (path: string) => Promise<void>
  removeProject: (id: string) => void
  loadProject: (id: string) => void
}

// agentStore.ts
interface AgentStore {
  messages: Message[]
  executionStatus: 'idle' | 'running' | 'paused' | 'completed'
  currentStep: number
  totalSteps: number
  sendMessage: (content: string) => Promise<void>
  pauseExecution: () => void
  resumeExecution: () => void
  stopExecution: () => void
}

// executionStore.ts
interface ExecutionStore {
  steps: ExecutionStep[]
  logs: string[]
  addStep: (step: ExecutionStep) => void
  updateStep: (id: string, status: StepStatus) => void
  addLog: (log: string) => void
}
```

---

## 五、数据流与通信设计

### 5.1 整体通信架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户交互流程                          │
└─────────────────────────────────────────────────────────┘

用户输入任务
    │
    ▼
┌─────────────┐  IPC   ┌──────────────┐
│ React前端   │───────▶│ Electron主进程│
│ (渲染进程)  │        │              │
└─────────────┘        └──────────────┘
    │                         │
    │ HTTP POST               │ 启动/管理
    │ /api/agent/execute      │
    ▼                         ▼
┌─────────────────────────────────────┐
│         FastAPI Backend             │
│  ┌───────────────────────────────┐  │
│  │  AgentService.execute()       │  │
│  │    │                          │  │
│  │    ▼                          │  │
│  │  RapidExecutionLoop.run()     │  │
│  │    │                          │  │
│  │    ├─▶ LLM决策                │  │
│  │    ├─▶ Tool执行               │  │
│  │    └─▶ 状态更新               │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
    │
    │ WebSocket推送
    │ (实时状态更新)
    ▼
┌─────────────┐
│ React前端   │
│ 更新UI      │
└─────────────┘
```

### 5.2 通信协议设计

#### 5.2.1 HTTP API Endpoints

```python
# 项目管理
POST   /api/projects                    # 添加项目
GET    /api/projects                    # 获取项目列表
DELETE /api/projects/{id}               # 删除项目
GET    /api/projects/{id}/structure     # 获取项目结构

# Agent执行
POST   /api/agent/execute               # 执行任务
POST   /api/agent/pause                 # 暂停执行
POST   /api/agent/resume                # 恢复执行
POST   /api/agent/stop                  # 终止执行
GET    /api/agent/history/{project_id}  # 获取执行历史

# 代码审查
GET    /api/changes/{execution_id}      # 获取代码变更
POST   /api/changes/{id}/accept         # 接受修改
POST   /api/changes/{id}/reject         # 拒绝修改

# LLM配置
GET    /api/llm/config                  # 获取LLM配置
POST   /api/llm/config                  # 更新LLM配置
GET    /api/llm/providers               # 获取支持的LLM提供商
```

#### 5.2.2 WebSocket事件

```typescript
// 服务端 → 客户端事件
interface ServerEvents {
  'execution:start': {
    executionId: string
    task: string
    timestamp: number
  }
  
  'execution:step': {
    stepId: string
    stepNumber: number
    totalSteps: number
    tool: string
    args: object
    status: 'running' | 'success' | 'failed'
    output?: string
    duration?: number
  }
  
  'execution:log': {
    stepId: string
    log: string
    timestamp: number
  }
  
  'execution:complete': {
    executionId: string
    result: string
    steps: ExecutionStep[]
    totalDuration: number
  }
  
  'execution:error': {
    executionId: string
    error: string
    step: ExecutionStep
  }
}

// 客户端 → 服务端事件
interface ClientEvents {
  'execution:pause': { executionId: string }
  'execution:resume': { executionId: string }
  'execution:stop': { executionId: string }
}
```

### 5.3 IPC通信(Electron主进程 ↔ 渲染进程)

```typescript
// 主进程暴露给渲染进程的API
interface ElectronAPI {
  // 项目管理
  selectDirectory: () => Promise<string>
  
  // 文件操作
  readFile: (path: string) => Promise<string>
  writeFile: (path: string, content: string) => Promise<void>
  
  // 应用配置
  getConfig: () => Promise<AppConfig>
  setConfig: (config: Partial<AppConfig>) => Promise<void>
  
  // 系统信息
  getAppPath: () => Promise<string>
  
  // 进程管理
  startBackend: () => Promise<void>
  stopBackend: () => Promise<void>
}

// 渲染进程调用方式
const result = await window.electronAPI.selectDirectory()
```

---

## 六、安全与错误处理设计

### 6.1 安全机制

#### 6.1.1 路径安全控制

```python
class PathSecurity:
    """文件系统访问安全控制"""
    
    def __init__(self, allowed_base_paths: List[str]):
        self.allowed_base_paths = [os.path.abspath(p) for p in allowed_base_paths]
    
    def validate_path(self, path: str) -> str:
        """验证路径是否在允许范围内"""
        abs_path = os.path.abspath(path)
        
        if not any(abs_path.startswith(base) for base in self.allowed_base_paths):
            raise SecurityError(f"路径 {path} 不在允许的访问范围内")
        
        # 防止路径遍历攻击
        real_path = os.path.realpath(abs_path)
        if not any(real_path.startswith(base) for base in self.allowed_base_paths):
            raise SecurityError("检测到路径遍历攻击")
        
        return abs_path
    
    def validate_write_path(self, path: str) -> str:
        """验证写入路径"""
        abs_path = self.validate_path(path)
        
        # 禁止写入敏感文件
        sensitive_patterns = ['.env', 'credentials', 'secrets', '.git/config']
        if any(pattern in abs_path for pattern in sensitive_patterns):
            raise SecurityError("禁止修改敏感文件")
        
        return abs_path
```

#### 6.1.2 Shell命令安全

```python
class ShellSecurity:
    """Shell命令执行安全控制"""
    
    FORBIDDEN_COMMANDS = [
        'rm -rf /',
        'dd if=',
        'mkfs',
        ':(){ :|:& };:',
        'chmod 777',
        'chown root',
    ]
    
    ALLOWED_COMMANDS_PATTERNS = [
        r'^(pytest|python|node|npm|yarn|git|ls|cat|grep|find)\s+',
        r'^npm (run|test|build)',
        r'^git (status|diff|log|add|commit|push|pull)',
    ]
    
    def validate_command(self, command: str) -> None:
        """验证命令安全性"""
        # 检查禁用命令
        for forbidden in self.FORBIDDEN_COMMANDS:
            if forbidden in command:
                raise SecurityError(f"禁止执行危险命令: {command}")
        
        # 检查是否在允许列表中
        import re
        if not any(re.match(pattern, command) for pattern in self.ALLOWED_COMMANDS_PATTERNS):
            raise SecurityError(f"命令不在允许列表中: {command}")
```

#### 6.1.3 资源限制

```python
class ResourceLimiter:
    """资源使用限制"""
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_EXECUTION_TIME = 600  # 10分钟
    MAX_STEPS = 50  # 最大执行步数
    MAX_SHELL_TIMEOUT = 60  # Shell命令超时
    
    def check_file_size(self, path: str) -> None:
        """检查文件大小"""
        size = os.path.getsize(path)
        if size > self.MAX_FILE_SIZE:
            raise ResourceLimitError(f"文件过大: {size} bytes")
    
    def check_execution_time(self, start_time: float) -> None:
        """检查执行时间"""
        elapsed = time.time() - start_time
        if elapsed > self.MAX_EXECUTION_TIME:
            raise ResourceLimitError(f"执行超时: {elapsed}秒")
```

### 6.2 错误处理机制

#### 6.2.1 错误分类

```python
class ErrorType(Enum):
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    SYNTAX_ERROR = "syntax_error"
    LLM_ERROR = "llm_error"
    TOOL_ERROR = "tool_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    SECURITY_ERROR = "security_error"
    RESOURCE_LIMIT = "resource_limit"

class AgentError(Exception):
    """Agent错误基类"""
    
    def __init__(self, error_type: ErrorType, message: str, recoverable: bool = True):
        self.error_type = error_type
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)
```

#### 6.2.2 错误恢复策略

```python
class ErrorRecovery:
    """错误恢复策略"""
    
    async def handle_error(self, error: AgentError, context: ExecutionContext) -> RecoveryAction:
        """根据错误类型选择恢复策略"""
        
        if error.error_type == ErrorType.FILE_NOT_FOUND:
            return RecoveryAction(
                strategy="search_and_retry",
                message="文件未找到,尝试搜索相似文件",
                auto_retry=True
            )
        
        elif error.error_type == ErrorType.SYNTAX_ERROR:
            return RecoveryAction(
                strategy="fix_and_retry",
                message="检测到语法错误,尝试自动修复",
                auto_retry=True
            )
        
        elif error.error_type == ErrorType.LLM_ERROR:
            return RecoveryAction(
                strategy="retry_with_backoff",
                message="LLM调用失败,等待后重试",
                auto_retry=True,
                max_retries=3
            )
        
        elif error.error_type == ErrorType.SECURITY_ERROR:
            return RecoveryAction(
                strategy="abort",
                message="安全违规,终止执行",
                auto_retry=False
            )
        
        else:
            return RecoveryAction(
                strategy="ask_user",
                message="遇到未知错误,需要用户干预",
                auto_retry=False
            )
```

#### 6.2.3 前端错误展示

```typescript
// 错误状态组件
const ErrorDisplay: React.FC<{error: AgentError}> = ({error}) => {
  return (
    <div className="error-container">
      <div className="error-header">
        <span className="error-icon">⚠️</span>
        <span className="error-type">{error.type}</span>
      </div>
      <div className="error-message">{error.message}</div>
      {error.recoverable && (
        <div className="error-actions">
          <button onClick={onRetry}>重试</button>
          <button onClick={onSkip}>跳过</button>
          <button onClick={onAbort}>终止</button>
        </div>
      )}
    </div>
  )
}
```

### 6.3 日志与审计

```python
class AuditLogger:
    """审计日志记录器"""
    
    def log_action(self, action: Action, result: ActionResult):
        """记录Agent行为"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action.type,
            "tool": action.tool,
            "args": self._sanitize_args(action.args),
            "result_status": result.status,
            "duration": result.duration,
            "error": result.error if result.error else None
        }
        
        # 写入审计日志
        self.logger.info(json.dumps(log_entry))
    
    def _sanitize_args(self, args: dict) -> dict:
        """清理敏感参数"""
        sensitive_keys = ['password', 'token', 'api_key', 'secret']
        return {
            k: '***REDACTED***' if k in sensitive_keys else v
            for k, v in args.items()
        }
```

---

## 七、项目结构设计

### 7.1 整体目录结构

```
ReflexionOS/
├── backend/                    # FastAPI后端
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI应用入口
│   │   ├── api/               # API层
│   │   │   ├── __init__.py
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── projects.py
│   │   │   │   ├── agent.py
│   │   │   │   ├── changes.py
│   │   │   │   └── llm.py
│   │   │   └── websocket.py   # WebSocket实时通信 🔴 P0
│   │   ├── services/          # 服务层
│   │   │   ├── __init__.py
│   │   │   ├── agent_service.py
│   │   │   ├── project_service.py
│   │   │   └── execution_service.py
│   │   ├── execution/         # 执行层
│   │   │   ├── __init__.py
│   │   │   ├── rapid_loop.py
│   │   │   ├── action_executor.py
│   │   │   ├── context_manager.py
│   │   │   └── prompt_manager.py  # Prompt管理 ✨ NEW
│   │   ├── orchestration/     # 编排层 ✨ NEW
│   │   │   ├── __init__.py
│   │   │   ├── skill_registry.py   # Skills系统
│   │   │   └── mcp_manager.py      # MCP协议支持
│   │   ├── tools/             # 工具层
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── file_tool.py
│   │   │   ├── patch_tool.py      # Patch工具 🔴 P0
│   │   │   ├── shell_tool.py
│   │   │   ├── search_tool.py     # 搜索工具 🟡 P1
│   │   │   └── git_tool.py        # Git工具 🟡 P1
│   │   ├── llm/               # LLM适配层
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── openai_adapter.py
│   │   │   ├── claude_adapter.py
│   │   │   └── ollama_adapter.py
│   │   ├── storage/           # 持久化存储层 ✨ NEW 🔴 P0
│   │   │   ├── __init__.py
│   │   │   ├── database.py        # 数据库连接
│   │   │   ├── models.py          # ORM模型
│   │   │   └── repositories/
│   │   │       ├── __init__.py
│   │   │       ├── project_repo.py
│   │   │       ├── execution_repo.py
│   │   │       └── conversation_repo.py
│   │   ├── config/            # 配置管理 ✨ NEW 🔴 P0
│   │   │   ├── __init__.py
│   │   │   ├── settings.py        # 应用配置
│   │   │   ├── llm_config.py      # LLM配置
│   │   │   ├── user_preferences.py # 用户偏好
│   │   │   └── validators.py      # 配置验证
│   │   ├── core/              # 核心功能 ✨ NEW
│   │   │   ├── __init__.py
│   │   │   ├── error_handler.py   # 错误处理 🟡 P1
│   │   │   ├── retry_strategy.py  # 重试策略
│   │   │   └── recovery.py        # 恢复机制
│   │   ├── security/          # 安全层
│   │   │   ├── __init__.py
│   │   │   ├── path_security.py
│   │   │   ├── shell_security.py
│   │   │   └── resource_limiter.py
│   │   ├── models/            # 数据模型
│   │   │   ├── __init__.py
│   │   │   ├── project.py
│   │   │   ├── execution.py
│   │   │   ├── action.py
│   │   │   └── llm_config.py
│   │   └── utils/             # 工具函数
│   │       ├── __init__.py
│   │       ├── logger.py
│   │       └── helpers.py
│   ├── tests/                 # 测试
│   │   ├── __init__.py
│   │   ├── test_tools/
│   │   ├── test_execution/
│   │   ├── test_storage/
│   │   ├── test_orchestration/
│   │   └── test_api/
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── README.md
│
├── frontend/                  # Electron+React前端
│   ├── electron/              # Electron主进程
│   │   ├── main.ts
│   │   ├── preload.ts
│   │   └── backend-manager.ts
│   ├── src/                   # React应用
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── HomePage.tsx
│   │   │   ├── AgentWorkspace.tsx
│   │   │   └── SettingsPage.tsx
│   │   ├── components/
│   │   │   ├── ProjectManager/
│   │   │   ├── ExecutionTimeline/
│   │   │   ├── CodeReviewer/
│   │   │   ├── ConfigPanel/      # 配置面板 ✨ NEW
│   │   │   └── MonacoEditor/
│   │   ├── stores/            # Zustand状态管理
│   │   │   ├── projectStore.ts
│   │   │   ├── agentStore.ts
│   │   │   ├── executionStore.ts
│   │   │   └── configStore.ts    # 配置状态 ✨ NEW
│   │   ├── services/          # API服务
│   │   │   ├── apiClient.ts
│   │   │   ├── webSocketClient.ts
│   │   │   └── ipcBridge.ts
│   │   ├── types/             # TypeScript类型定义
│   │   │   ├── project.ts
│   │   │   ├── agent.ts
│   │   │   ├── execution.ts
│   │   │   └── config.ts         # 配置类型 ✨ NEW
│   │   └── utils/
│   │       └── helpers.ts
│   ├── public/
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
│
├── docs/                      # 文档
│   ├── design/
│   ├── api/
│   └── user-guide/
│
├── scripts/                   # 构建脚本
│   ├── build.sh
│   └── dev.sh
│
├── .gitignore
├── LICENSE
└── README.md
```

### 7.2 核心文件职责说明

#### Backend核心文件:

- `main.py`: FastAPI应用初始化,路由注册,中间件配置
- `config.py`: 环境变量,配置项管理
- `rapid_loop.py`: Agent执行循环核心逻辑
- `action_executor.py`: 工具调用执行器
- `base.py`: LLM统一接口定义
- `path_security.py`: 文件系统访问安全控制

#### Frontend核心文件:

- `main.ts`: Electron主进程,进程管理,IPC桥接
- `AgentWorkspace.tsx`: 主工作区页面(合并版)
- `ExecutionTimeline.tsx`: 执行时间线组件
- `agentStore.ts`: Agent状态管理
- `apiClient.ts`: HTTP API客户端
- `webSocketClient.ts`: WebSocket实时通信

---

## 八、测试策略设计

### 8.1 测试分层

```
┌─────────────────────────────────────────┐
│          E2E Tests (端到端测试)          │
│  - 完整用户流程测试                      │
│  - Electron + FastAPI集成测试           │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│       Integration Tests (集成测试)       │
│  - API集成测试                           │
│  - 工具执行集成测试                      │
│  - WebSocket通信测试                    │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│          Unit Tests (单元测试)           │
│  - 工具层单元测试                        │
│  - 执行循环单元测试                      │
│  - 安全控制单元测试                      │
│  - 前端组件单元测试                      │
└─────────────────────────────────────────┘
```

### 8.2 后端测试

#### 8.2.1 单元测试

```python
# tests/test_tools/test_file_tool.py
import pytest
from app.tools.file_tool import FileTool
from app.security.path_security import PathSecurity

class TestFileTool:
    
    @pytest.fixture
    def file_tool(self, tmp_path):
        security = PathSecurity([str(tmp_path)])
        return FileTool(security)
    
    async def test_read_file_success(self, file_tool, tmp_path):
        # 准备测试文件
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        
        # 执行读取
        result = await file_tool.execute({
            "action": "read",
            "path": str(test_file)
        })
        
        # 验证结果
        assert result.success is True
        assert result.content == "print('hello')"
    
    async def test_read_file_outside_workspace(self, file_tool):
        # 尝试读取工作区外的文件
        with pytest.raises(SecurityError):
            await file_tool.execute({
                "action": "read",
                "path": "/etc/passwd"
            })
    
    async def test_read_large_file(self, file_tool, tmp_path):
        # 测试大文件拒绝
        large_file = tmp_path / "large.txt"
        large_file.write_bytes(b"x" * (20 * 1024 * 1024))  # 20MB
        
        with pytest.raises(ResourceLimitError):
            await file_tool.execute({
                "action": "read",
                "path": str(large_file)
            })
```

```python
# tests/test_execution/test_rapid_loop.py
import pytest
from app.execution.rapid_loop import RapidExecutionLoop
from app.llm.base import MockLLMAdapter

class TestRapidExecutionLoop:
    
    @pytest.fixture
    def execution_loop(self):
        llm = MockLLMAdapter()
        return RapidExecutionLoop(llm)
    
    async def test_simple_task_completion(self, execution_loop):
        """测试简单任务完成"""
        task = "创建一个hello.txt文件"
        context = ExecutionContext(task=task)
        
        result = await execution_loop.run(task, context)
        
        assert result.status == "completed"
        assert "hello.txt" in result.answer
    
    async def test_max_steps_limit(self, execution_loop):
        """测试最大步数限制"""
        task = "无限循环任务"
        context = ExecutionContext(task=task)
        
        # Mock LLM返回永不完成的action
        execution_loop.llm.set_response({
            "type": "tool_call",
            "tool": "read_file",
            "args": {"path": "test.py"}
        })
        
        result = await execution_loop.run(task, context)
        
        assert result.status == "failed"
        assert "超过最大步数" in result.error
```

#### 8.2.2 集成测试

```python
# tests/test_api/test_agent_integration.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestAgentIntegration:
    
    async def test_execute_task_e2e(self, tmp_path):
        """端到端任务执行测试"""
        # 创建测试项目
        project_path = str(tmp_path)
        
        # 添加项目
        response = client.post("/api/projects", json={
            "path": project_path,
            "name": "TestProject"
        })
        project_id = response.json()["id"]
        
        # 执行任务
        response = client.post("/api/agent/execute", json={
            "project_id": project_id,
            "task": "创建一个README.md文件"
        })
        execution_id = response.json()["execution_id"]
        
        # 等待执行完成
        import time
        for _ in range(10):
            response = client.get(f"/api/agent/status/{execution_id}")
            status = response.json()["status"]
            if status in ["completed", "failed"]:
                break
            time.sleep(1)
        
        # 验证结果
        assert status == "completed"
        assert (tmp_path / "README.md").exists()
```

### 8.3 前端测试

#### 8.3.1 组件测试

```typescript
// src/components/ExecutionTimeline/__tests__/ExecutionTimeline.test.tsx
import { render, screen } from '@testing-library/react'
import { ExecutionTimeline } from '../ExecutionTimeline'

describe('ExecutionTimeline', () => {
  it('should render execution steps', () => {
    const steps = [
      { id: '1', tool: 'read_file', status: 'success', duration: 0.2 },
      { id: '2', tool: 'apply_patch', status: 'running' },
    ]
    
    render(<ExecutionTimeline steps={steps} />)
    
    expect(screen.getByText('read_file')).toBeInTheDocument()
    expect(screen.getByText('apply_patch')).toBeInTheDocument()
    expect(screen.getByText('✅')).toBeInTheDocument()
    expect(screen.getByText('🔄')).toBeInTheDocument()
  })
  
  it('should expand step details on click', async () => {
    const steps = [
      { id: '1', tool: 'read_file', status: 'success', output: 'file content' }
    ]
    
    render(<ExecutionTimeline steps={steps} />)
    
    const step = screen.getByText('read_file')
    fireEvent.click(step)
    
    await waitFor(() => {
      expect(screen.getByText('file content')).toBeInTheDocument()
    })
  })
})
```

#### 8.3.2 Store测试

```typescript
// src/stores/__tests__/agentStore.test.ts
import { renderHook, act } from '@testing-library/react'
import { useAgentStore } from '../agentStore'

describe('agentStore', () => {
  it('should send message and update state', async () => {
    const { result } = renderHook(() => useAgentStore())
    
    await act(async () => {
      await result.current.sendMessage('修复bug')
    })
    
    expect(result.current.messages).toHaveLength(1)
    expect(result.current.messages[0].role).toBe('user')
    expect(result.current.executionStatus).toBe('running')
  })
  
  it('should pause execution', () => {
    const { result } = renderHook(() => useAgentStore())
    
    act(() => {
      result.current.pauseExecution()
    })
    
    expect(result.current.executionStatus).toBe('paused')
  })
})
```

### 8.4 E2E测试

```typescript
// e2e/agent-workflow.spec.ts
import { test, expect } from '@playwright/test'

test('complete agent workflow', async ({ page }) => {
  // 启动应用
  await page.goto('http://localhost:3000')
  
  // 添加项目
  await page.click('[data-testid="new-project-btn"]')
  await page.setInputFiles('[data-testid="directory-input"]', '/path/to/test/project')
  await page.click('[data-testid="confirm-btn"]')
  
  // 打开项目
  await page.click('[data-testid="project-card"]')
  
  // 发送任务
  await page.fill('[data-testid="task-input"]', '创建hello.py文件')
  await page.click('[data-testid="send-btn"]')
  
  // 等待执行完成
  await page.waitForSelector('[data-testid="execution-complete"]', {
    timeout: 30000
  })
  
  // 验证结果
  const result = await page.textContent('[data-testid="result-message"]')
  expect(result).toContain('完成')
})
```

---

## 九、开发路线图

### 9.1 第一阶段:MVP核心功能 (4-6周)

#### Week 1-2: 后端基础设施
- [ ] FastAPI项目初始化
- [ ] 基础API路由搭建
- [ ] 数据模型定义
- [ ] 配置管理系统
- [ ] 日志系统

#### Week 2-3: 核心执行引擎
- [ ] RapidExecutionLoop实现
- [ ] Action协议定义
- [ ] ContextManager实现
- [ ] 自研LLM适配层
  - [ ] **统一接口定义(UniversalLLMInterface)**
  - [ ] **OpenAI适配器(完整实现)**
  - [ ] Claude适配器(预留接口)
  - [ ] Ollama适配器(预留接口)
  - [ ] 流式输出支持
  - [ ] 多模型切换机制

#### Week 3-4: 核心工具层
- [ ] FileTool实现
- [ ] PatchTool实现
- [ ] ShellTool实现
- [ ] ToolRegistry实现

#### Week 4-5: Electron应用框架
- [ ] Electron项目初始化
- [ ] React应用框架
- [ ] IPC通信桥接
- [ ] FastAPI进程管理

#### Week 5-6: 核心UI组件
- [ ] HomePage实现
- [ ] AgentWorkspace页面
- [ ] ExecutionTimeline组件
- [ ] LLM配置界面(OpenAI API Key配置、模型选择)
- [ ] 基础状态管理

#### Week 6: 集成测试
- [ ] 端到端测试
- [ ] OpenAI适配器测试
- [ ] Bug修复
- [ ] 性能优化

### 9.2 第二阶段:功能完善 (3-4周)

#### Week 7-8: 高级功能
- [ ] CodeReviewer代码审查
- [ ] GitTool集成
- [ ] SearchTool实现
- [ ] 错误恢复机制完善

#### Week 8-9: Prompt与体验优化
- [ ] Prompt模板优化
- [ ] 多语言项目支持优化
- [ ] 执行历史管理
- [ ] 项目配置持久化

#### Week 9-10: LLM扩展与体验优化
- [ ] **Claude适配器实现**
- [ ] **Ollama适配器实现**
- [ ] 性能优化
- [ ] UI/UX改进
- [ ] 快捷键支持
- [ ] 主题定制

### 9.3 第三阶段:扩展能力 (2-3周)

#### Week 11-12: 插件系统
- [ ] 插件架构设计
- [ ] 插件加载机制
- [ ] 示例插件开发

#### Week 12-13: Gateway预留
- [ ] API Gateway接口设计
- [ ] Webhook支持
- [ ] 鉴权系统

### 9.4 关键里程碑

```
M1 (Week 6): MVP可用
├─ 基础Agent执行能力
├─ 单项目支持
├─ 核心工具可用
├─ 多LLM支持
├─ 流式输出
├─ LLM配置界面
└─ 基础UI交互

M2 (Week 10): 功能完善
├─ 代码审查功能
├─ 错误恢复机制
├─ Prompt优化
├─ 用户体验优化
└─ 执行历史管理

M3 (Week 13): 扩展就绪
├─ 插件系统
├─ Gateway预留
└─ 文档完善
```

### 9.5 技术风险与应对

| 风险 | 影响 | 应对策略 |
|------|------|----------|
| FastAPI进程管理复杂 | 高 | 使用成熟的进程管理库,参考VSCode的方案 |
| LLM响应不稳定 | 中 | 实现重试机制和降级策略 |
| Diff解析失败 | 中 | 多种Diff格式兼容,fallback到全文替换 |
| Electron性能问题 | 中 | 懒加载、虚拟滚动、Worker线程 |
| 跨平台兼容性 | 低 | 优先保证macOS/Windows,Linux后续支持 |

---

## 十、总结

ReflexionOS 采用紧耦合单体架构,基于 Electron + React + FastAPI 技术栈,实现了类似 Codex 的本地执行型 Agent 桌面应用。核心设计要点:

1. **执行驱动**: 小步执行、反馈驱动、自动修复的执行循环
2. **统一接口**: 自研LLM适配层,支持多模型切换和流式输出
3. **直观交互**: 时间线式的执行监控界面,代码修改内联预览
4. **安全可靠**: 完善的路径安全、命令安全和资源限制机制
5. **扩展预留**: Gateway和插件系统架构预留,支持未来扩展

项目按照3个阶段推进,MVP阶段重点实现核心执行能力和OpenAI适配,后续逐步完善功能和扩展能力。

---

## 十一、架构完整性检查与实施优先级

### 11.1 组件优先级矩阵

| 组件 | 优先级 | MVP必要性 | 实施阶段 | 预计工时 |
|------|--------|----------|---------|---------|
| **执行引擎** | 🔴 P0 | ✅ 必须 | 第一阶段 | 4h |
| **LLM适配层** | 🔴 P0 | ✅ 必须 | 第一阶段 | 3h |
| **文件/Shell工具** | 🔴 P0 | ✅ 必须 | 第一阶段 | 4h |
| **工具注册中心** | 🔴 P0 | ✅ 必须 | 第一阶段 | 2h |
| **Prompt管理** | 🔴 P0 | ✅ 必须 | 第一阶段 | 2h |
| **Patch工具** | 🔴 P0 | ✅ 必须 | 第一阶段 | 3h |
| **持久化存储** | 🔴 P0 | ✅ 必须 | 第一阶段 | 4h |
| **配置管理完善** | 🔴 P0 | ✅ 必须 | 第一阶段 | 2h |
| **WebSocket后端** | 🔴 P0 | ✅ 必须 | 第一阶段 | 3h |
| **前端UI框架** | 🔴 P0 | ✅ 必须 | 第一阶段 | 6h |
| **搜索工具** | 🟡 P1 | ⏸️ 可选 | 第二阶段 | 3h |
| **Git工具** | 🟡 P1 | ⏸️ 可选 | 第二阶段 | 2h |
| **错误处理完善** | 🟡 P1 | ⏸️ 可选 | 第二阶段 | 3h |
| **Skills系统** | 🟡 P1 | ⏸️ 可选 | 第二阶段 | 4h |
| **MCP协议支持** | 🟡 P1 | ⏸️ 可选 | 第二阶段 | 6h |
| **向量记忆** | 🟢 P2 | ❌ 不需要 | 第三阶段 | 8h |
| **插件系统** | 🟢 P2 | ❌ 不需要 | 第三阶段 | 6h |
| **多Agent协作** | 🟢 P2 | ❌ 不需要 | 第三阶段 | 10h |
| **工作流引擎** | 🟢 P3 | ❌ 不需要 | 第四阶段 | 12h |

### 11.2 MVP 最小功能集

**第一阶段必须完成 (预计 2-3 周):**

```
核心执行能力:
✅ RapidExecutionLoop - Agent执行循环
✅ LLM适配层 - OpenAI支持
✅ Prompt管理 - 基础模板
✅ 工具层 - File/Shell/Patch
✅ 上下文管理 - ExecutionContext

基础设施:
✅ 持久化存储 - SQLite + SQLAlchemy
✅ 配置管理 - 动态配置 + 验证
✅ WebSocket - 实时状态推送
✅ 安全控制 - 路径和命令安全

用户界面:
✅ 项目管理 - 创建/删除/切换
✅ Agent工作区 - 时间线式交互
✅ 配置面板 - LLM配置界面
✅ 执行监控 - 实时步骤展示
```

### 11.3 实施计划概览

> 详细实施计划见: `docs/superpowers/plans/2026-04-15-phase1-implementation.md`

#### 第一阶段实施模块 (Week 1-6)

**模块一: 后端基础设施搭建 (Week 1)**
- 任务 1.1: 创建后端项目结构
- 任务 1.2: 实现数据模型定义
- 任务 1.3: 实现日志系统

**模块二: LLM 适配层实现 (Week 2)**
- 任务 2.1: 定义统一 LLM 接口
- 任务 2.2: 实现 OpenAI 适配器

**模块三: 工具层实现 (Week 3)**
- 任务 3.1: 实现文件工具
- 任务 3.2: 实现 Shell 工具
- 任务 3.3: 实现工具注册中心
- 任务 3.5: 实现 Patch 工具 🔴 P0
- 任务 3.6: 实现持久化存储层 🔴 P0
- 任务 3.7: 完善配置管理系统 🔴 P0
- 任务 3.8: 实现 WebSocket 后端 🔴 P0

**模块四: Agent 执行引擎 (Week 4)**
- 任务 4.1: 实现执行上下文管理
- 任务 4.2: 实现 Agent 执行循环 (核心)
- 任务 4.3: 实现 Prompt 管理系统
- 任务 4.4: 预留 Skills 和 MCP 接口

**模块五: API 路由实现 (Week 5)**
- 任务 5.1: 实现项目管理 API
- 任务 5.2: 实现 Agent 执行 API

**模块六: 前端基础搭建 (Week 5-6)**
- 任务 6.1: 创建前端项目结构
- 任务 6.2: 实现状态管理
- 任务 6.3: 实现 API 客户端

---

### 11.4 第二阶段增强功能

**功能完善 (预计 2-3 周):**

```
能力提升:
⏸️ 搜索工具 - 代码搜索
⏸️ Git工具 - 版本控制集成
⏸️ Skills系统 - 可复用技能库
⏸️ MCP协议 - 外部工具接入

体验优化:
⏸️ 错误处理完善 - 智能恢复
⏸️ Prompt优化 - 模板迭代
⏸️ 执行历史管理 - 经验复用
⏸️ 多LLM支持 - Claude/Ollama
```

### 11.5 第三阶段高级功能

**扩展能力 (预计 2-3 周):**

```
智能增强:
🟢 向量记忆 - 长期记忆
🟢 知识库 - 项目知识积累
🟢 插件系统 - 能力扩展
🟢 多Agent协作 - 复杂任务分解

生态建设:
🟢 Gateway - 外部应用接入
🟢 插件市场 - 社区贡献
🟢 API开放 - 第三方集成
```

### 11.6 架构完整性检查清单

#### ✅ 已具备组件

- [x] 执行引擎核心设计
- [x] LLM适配层架构
- [x] 工具层基础实现
- [x] 安全控制机制
- [x] Prompt管理系统设计
- [x] Skills系统框架
- [x] MCP协议预留
- [x] 前端架构设计
- [x] API接口设计
- [x] 数据流设计
- [x] 详细实施计划

#### 🔴 MVP必须补充

- [ ] Patch工具实现 (任务3.5)
- [ ] SQLite持久化层 (任务3.6)
- [ ] 配置管理完善 (任务3.7)
- [ ] WebSocket后端实现 (任务3.8)
- [ ] 前端核心UI组件

#### 🟡 第二阶段补充

- [ ] 搜索工具
- [ ] Git工具集成
- [ ] 错误处理完善
- [ ] Skills完整实现
- [ ] MCP协议实现

#### 🟢 未来扩展

- [ ] 向量记忆系统
- [ ] 插件系统
- [ ] 多Agent协作
- [ ] 工作流引擎
- [ ] 监控和分析

### 11.7 技术债务清单

**已知限制 (可在后续迭代解决):**

1. **Patch工具**: 当前设计较简单,需要更健壮的冲突处理
2. **错误恢复**: 第一版采用简单重试,第二阶段增加智能恢复
3. **上下文管理**: 轻量级设计,无法处理复杂推理链
4. **配置验证**: 基础验证,第二阶段增强类型检查
5. **WebSocket**: 基础实现,后续增加断线重连和心跳
6. **Skills/MCP**: 仅框架预留,第二阶段完整实现

**优化方向:**

1. **性能优化**: 大文件处理、虚拟滚动、懒加载
2. **安全加固**: 更细粒度的权限控制
3. **用户体验**: 快捷键、主题、国际化
4. **测试覆盖**: E2E测试、性能测试、压力测试

---

## 十二、总结

ReflexionOS 采用紧耦合单体架构,基于 Electron + React + FastAPI 技术栈,实现了类似 Codex 的本地执行型 Agent 桌面应用。

**核心设计要点:**

1. **执行驱动**: 小步执行、反馈驱动、自动修复的执行循环
2. **统一接口**: 自研LLM适配层,支持多模型切换和流式输出
3. **Prompt管理**: 模板化设计,易于优化和迭代
4. **Skills系统**: 可复用的技能库,降低重复编写
5. **MCP协议**: 标准化工具接入,支持外部生态
6. **持久化存储**: SQLite轻量级存储,完整的历史记录
7. **配置管理**: 动态配置、验证和持久化
8. **安全可靠**: 完善的路径安全、命令安全和资源限制机制
9. **扩展预留**: Gateway、插件系统和向量记忆预留

**项目分三个阶段推进:**

- **第一阶段 (MVP, Week 1-6)**: 
  - 核心执行能力 (执行引擎、LLM适配、工具层)
  - 基础设施 (持久化存储、配置管理、WebSocket)
  - 用户界面 (项目管理、工作区、配置面板)
  - 详细实施计划见: `docs/superpowers/plans/2026-04-15-phase1-implementation.md`

- **第二阶段 (增强, Week 7-10)**: 
  - 能力提升 (搜索工具、Git工具、Skills完整实现)
  - 体验优化 (错误处理、Prompt优化、执行历史)
  - 多LLM支持 (Claude/Ollama适配器)

- **第三阶段 (扩展, Week 11-13)**: 
  - 智能增强 (向量记忆、知识库)
  - 生态建设 (插件系统、Gateway)
  - 高级功能 (多Agent协作)

**架构完整性评分:** 92/100

**实施状态:** 详细TDD实施计划已制定,可立即开始开发

通过渐进式开发策略,先验证核心功能可行性,再逐步增强能力,最终形成完善的 Agent 平台。
