# Sub-Agent 并行执行与多模态支持设计文档

## 概述

本文档描述 ReflexionOS 的两个核心功能扩展：

1. **Sub-Agent 并行执行**：支持将复杂任务分解给多个 sub-agent 并行处理，支持任务依赖关系
2. **多模态消息支持**：用户可以在对话中粘贴图片，agent 分析图片内容

## 目标场景

### Sub-Agent 场景
1. **分解复杂任务**：用户问"分析这三个模块的性能问题"，系统分配三个 agent 并行分析
2. **探索多条路径**：用户问"用什么方案解决X问题"，系统并行探索多个方案后汇总对比
3. **独立任务并发**：用户明确说"同时做A、B、C"，系统并行执行多个独立任务

### 多模态场景
1. **用户上传图片**：在对话框粘贴 UI 截图、错误截图、架构图，agent 分析内容
2. **Agent 主动截图**：agent 使用 browser 工具截图后分析
3. **读取项目图片**：agent 读取项目中的图片文件并生成相关代码或文档

## 核心约束

1. **级联删除**：删除父 session 时，所有子 sub-session 必须自动清理
2. **级联取消**：取消主任务时，所有 sub-agent 同步取消
3. **超时控制**：sub-agent 默认超时 1 小时
4. **只读交互**：用户可以查看 sub-agent 的执行详情并提问，但不影响原任务流程
5. **图片清理**：上传的图片文件保留 1 天后自动清理

## 架构设计

### 方案：轻量级 Sub-Session 模式

**核心思路**：
- Sub-agent 复用现有的 session/turn/run 架构
- 每个 sub-agent 创建一个隐藏的 sub-session
- 主 agent 通过 `delegate` 工具启动 sub-agent
- UI 通过 `parent_session_id` 展示树形结构

**选择理由**：
- 复用现有代码（WebSocket、工具执行、approval 流程）
- 每个 sub-agent 有完整的上下文和历史
- 实现成本低，风险小
- 天然支持实时流式更新

---

## 详细设计

### 1. 数据模型扩展

#### Session 表
```python
class Session(BaseModel):
    id: str
    project_id: str
    title: str
    parent_session_id: str | None = None  # 新增：指向父 session
    is_sub_session: bool = False          # 新增：标记是否为子 session
    agent_mode: str = "build"
    created_at: datetime
    updated_at: datetime
    last_event_seq: int = 0
```

**数据库约束**：
```sql
ALTER TABLE sessions ADD COLUMN parent_session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE;
ALTER TABLE sessions ADD COLUMN is_sub_session BOOLEAN DEFAULT FALSE;
CREATE INDEX idx_sessions_parent ON sessions(parent_session_id);
```

#### Message 表（多模态支持）
```python
class Message(BaseModel):
    id: str
    session_id: str
    turn_id: str
    run_id: str | None
    role: str  # user, assistant, tool
    content_text: str
    message_type: MessageType
    attachments: list[MessageAttachment] = []  # 新增：附件列表
    # ... 其他字段

class MessageAttachment(BaseModel):
    id: str
    type: str  # image, file
    mime_type: str  # image/png, image/jpeg
    file_path: str  # storage/uploads/{session_id}/{timestamp}_{random}.png
    file_size: int  # bytes
    created_at: datetime
```

#### LLMMessage 扩展（多模态）
```python
class LLMContentPart(BaseModel):
    type: str  # text, image_url
    text: str | None = None
    image_url: dict | None = None  # {"url": "data:image/png;base64,..."}

class LLMMessage(BaseModel):
    role: str
    content: str | list[LLMContentPart] | None = None  # 支持多模态
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
```

---

### 2. Sub-Agent 编排

#### Delegate 工具
```python
class DelegateTool(BaseTool):
    """将任务委托给多个 sub-agent 并行执行"""
    
    name = "delegate"
    description = """
    将任务分解给多个 sub-agent 并行执行。支持任务依赖关系。
    
    适用场景：
    - 分析多个独立模块
    - 并行探索多个解决方案
    - 执行多个可以同时进行的任务
    
    注意：
    - 所有 sub-agent 默认超时 1 小时
    - 如果存在依赖关系，请在 dependencies 中声明
    - 返回时所有任务已完成或超时
    """
    
    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "子任务列表，最多 10 个",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "任务唯一标识"},
                            "description": {"type": "string", "description": "任务描述"},
                            "context": {"type": "string", "description": "可选：任务相关的上下文信息"}
                        },
                        "required": ["id", "description"]
                    },
                    "maxItems": 10
                },
                "dependencies": {
                    "type": "array",
                    "description": "任务依赖关系（可选）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string"},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "依赖的任务 ID 列表"
                            }
                        },
                        "required": ["task_id", "depends_on"]
                    }
                },
                "shared_context": {
                    "type": "string",
                    "description": "可选：所有子任务共享的背景信息"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时时间（秒），默认 3600（1小时），最大 7200（2小时）",
                    "default": 3600,
                    "minimum": 60,
                    "maximum": 7200
                }
            },
            "required": ["tasks"]
        }
    
    async def execute(self, args: dict) -> ToolResult:
        tasks = args["tasks"]
        dependencies = args.get("dependencies", [])
        shared_context = args.get("shared_context", "")
        timeout = min(args.get("timeout", 3600), 7200)  # 限制最大2小时
        
        # 验证任务数量
        if len(tasks) > 10:
            return ToolResult(
                success=False,
                error="子任务数量超过限制（最多 10 个）"
            )
        
        # 验证任务 ID 唯一性
        task_ids = [t["id"] for t in tasks]
        if len(task_ids) != len(set(task_ids)):
            return ToolResult(
                success=False,
                error="任务 ID 必须唯一"
            )
        
        # 验证依赖关系有效性
        dep_validation = self._validate_dependencies(task_ids, dependencies)
        if not dep_validation["valid"]:
            return ToolResult(
                success=False,
                error=dep_validation["error"]
            )
        
        # 1. 构建依赖图
        dep_graph = self._build_dependency_graph(tasks, dependencies)
        
        # 2. 拓扑排序，分批执行
        batches = self._topological_sort(dep_graph)
        
        # 3. 逐批执行（同批次内并行）
        all_results = {}
        for batch_idx, batch in enumerate(batches):
            logger.info(f"执行第 {batch_idx + 1}/{len(batches)} 批任务，包含 {len(batch)} 个子任务")
            batch_results = await self._execute_batch(
                batch, 
                shared_context,
                all_results,  # 前序任务结果
                timeout
            )
            all_results.update(batch_results)
        
        # 4. 汇总返回
        summary = self._format_summary(all_results)
        return ToolResult(
            success=True,
            output=summary,
            data={
                "sub_sessions": [r["session_id"] for r in all_results.values()],
                "results": all_results,
                "total_tasks": len(tasks),
                "completed": sum(1 for r in all_results.values() if r["status"] == "completed"),
                "failed": sum(1 for r in all_results.values() if r["status"] == "failed"),
                "timeout": sum(1 for r in all_results.values() if r["status"] == "timeout")
            }
        )
    
    def _validate_dependencies(self, task_ids: list[str], dependencies: list[dict]) -> dict:
        """验证依赖关系的有效性"""
        task_id_set = set(task_ids)
        
        for dep in dependencies:
            task_id = dep.get("task_id")
            depends_on = dep.get("depends_on", [])
            
            # 检查 task_id 是否存在
            if task_id not in task_id_set:
                return {
                    "valid": False,
                    "error": f"依赖关系中的任务 ID '{task_id}' 不存在"
                }
            
            # 检查 depends_on 中的任务是否存在
            for dep_task_id in depends_on:
                if dep_task_id not in task_id_set:
                    return {
                        "valid": False,
                        "error": f"依赖的任务 ID '{dep_task_id}' 不存在"
                    }
            
            # 检查是否自己依赖自己
            if task_id in depends_on:
                return {
                    "valid": False,
                    "error": f"任务 '{task_id}' 不能依赖自己"
                }
        
        # 检查循环依赖（简单检测：尝试拓扑排序）
        try:
            dep_graph = self._build_dependency_graph(
                [{"id": tid} for tid in task_ids],
                dependencies
            )
            self._topological_sort(dep_graph)
        except ValueError as e:
            return {
                "valid": False,
                "error": f"依赖关系存在循环: {str(e)}"
            }
        
        return {"valid": True}
    
    def _build_dependency_graph(self, tasks: list[dict], dependencies: list[dict]) -> dict:
        """构建依赖图"""
        graph = {task["id"]: {"task": task, "depends_on": []} for task in tasks}
        
        for dep in dependencies:
            task_id = dep["task_id"]
            depends_on = dep["depends_on"]
            graph[task_id]["depends_on"] = depends_on
        
        return graph
    
    def _topological_sort(self, graph: dict) -> list[list[dict]]:
        """拓扑排序，返回分批次的任务列表"""
        # 计算入度
        in_degree = {task_id: 0 for task_id in graph}
        for task_id, node in graph.items():
            for dep in node["depends_on"]:
                in_degree[task_id] += 1
        
        batches = []
        remaining = set(graph.keys())
        
        while remaining:
            # 找出所有入度为 0 的节点（可以并行执行）
            batch = [
                task_id for task_id in remaining
                if in_degree[task_id] == 0
            ]
            
            if not batch:
                # 存在循环依赖
                raise ValueError(f"检测到循环依赖，剩余任务: {remaining}")
            
            batches.append([graph[task_id]["task"] for task_id in batch])
            
            # 更新入度
            for task_id in batch:
                remaining.remove(task_id)
                # 减少依赖此任务的其他任务的入度
                for other_id in remaining:
                    if task_id in graph[other_id]["depends_on"]:
                        in_degree[other_id] -= 1
        
        return batches
    
    def _format_summary(self, results: dict) -> str:
        """格式化汇总结果"""
        lines = [f"已完成 {len(results)} 个子任务：\n"]
        
        for task_id, result in results.items():
            status_emoji = {
                "completed": "✅",
                "failed": "❌",
                "timeout": "⏱️"
            }.get(result["status"], "❓")
            
            lines.append(f"{status_emoji} {task_id}: {result['status']}")
            if result["status"] == "completed":
                # 截取输出的前200字符
                output_preview = result["output"][:200]
                if len(result["output"]) > 200:
                    output_preview += "..."
                lines.append(f"   输出: {output_preview}\n")
        
        return "\n".join(lines)
```

#### 依赖关系处理示例
```python
# 用户：先分析模块A和B，再基于结果分析模块C
{
    "tasks": [
        {"id": "analyze_a", "description": "分析模块A的性能"},
        {"id": "analyze_b", "description": "分析模块B的性能"},
        {"id": "analyze_c", "description": "分析模块C，重点关注与A、B的交互"}
    ],
    "dependencies": [
        {
            "task_id": "analyze_c",
            "depends_on": ["analyze_a", "analyze_b"]
        }
    ]
}

# 执行顺序：
# Batch 1: analyze_a, analyze_b (并行)
# Batch 2: analyze_c (等待 Batch 1 完成，获取结果作为上下文)
```

---

### 3. 执行流程

#### 主 Agent 调用流程
```
用户输入："分析模块A、B、C的性能问题"
    ↓
主 Agent 推理："需要并行分析三个模块"
    ↓
调用 delegate 工具
    ↓
创建 3 个 sub-session (标记 parent_session_id)
    ↓
并行启动 3 个 RapidExecutionLoop
    ↓
等待所有完成或超时（通过 asyncio.gather + timeout）
    ↓
汇总结果返回给主 Agent
    ↓
主 Agent 分析汇总结果，生成最终报告
```

#### Sub-Agent 生命周期
```python
# backend/app/tools/delegate_tool.py
async def _execute_batch(
    self, 
    tasks: list[dict],
    shared_context: str,
    previous_results: dict,
    timeout: int
) -> dict:
    """执行一批并行任务"""
    
    sub_agent_tasks = []
    for task in tasks:
        # 1. 创建 sub-session
        sub_session = await self._create_sub_session(
            parent_session_id=self.parent_session_id,
            parent_project_id=self.parent_project_id,
            title=f"[子任务] {task['description'][:30]}"
        )
        
        # 2. 构建子任务的完整提示（包含依赖结果）
        prompt = self._build_sub_agent_prompt(
            task=task,
            shared_context=shared_context,
            previous_results=previous_results
        )
        
        # 3. 启动 sub-agent（复用 AgentService.start_turn）
        sub_task = asyncio.create_task(
            self._start_sub_agent(
                session_id=sub_session.id,
                project_id=self.parent_project_id,
                prompt=prompt,
                provider_id=self.provider_id,
                model_id=self.model_id
            )
        )
        sub_agent_tasks.append((task["id"], sub_session.id, sub_task))
    
    # 4. 等待所有完成（with timeout）
    results = {}
    try:
        task_futures = [task for _, _, task in sub_agent_tasks]
        done, pending = await asyncio.wait(
            task_futures,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED
        )
        
        # 5. 处理超时：取消未完成的任务
        for task_future in pending:
            task_future.cancel()
            try:
                await task_future
            except asyncio.CancelledError:
                pass
        
        # 6. 收集结果
        for task_id, session_id, task_future in sub_agent_tasks:
            if task_future in done:
                try:
                    result = await task_future
                    results[task_id] = {
                        "session_id": session_id,
                        "status": "completed",
                        "output": result
                    }
                except Exception as e:
                    results[task_id] = {
                        "session_id": session_id,
                        "status": "failed",
                        "output": f"任务失败: {str(e)}"
                    }
            else:
                results[task_id] = {
                    "session_id": session_id,
                    "status": "timeout",
                    "output": f"任务超时（{timeout}秒）"
                }
    except Exception as e:
        logger.exception("批量执行子任务失败")
        raise
    
    return results

async def _create_sub_session(
    self,
    parent_session_id: str,
    parent_project_id: str,
    title: str
) -> Session:
    """创建子 session"""
    from app.services.session_service import session_service
    
    sub_session = session_service.create_session(
        project_id=parent_project_id,
        title=title,
        parent_session_id=parent_session_id,
        is_sub_session=True
    )
    return sub_session

async def _start_sub_agent(
    self,
    session_id: str,
    project_id: str,
    prompt: str,
    provider_id: str,
    model_id: str
) -> str:
    """启动子 agent 并等待完成"""
    from app.services.agent_service import agent_service
    
    # 启动 turn
    started = await agent_service.start_turn(
        project_id=project_id,
        session_id=session_id,
        content=prompt,
        provider_id=provider_id,
        model_id=model_id
    )
    
    # 等待 run 完成
    run_id = started.run.id
    task = agent_service.running_tasks.get(run_id)
    if task:
        await task
    
    # 提取最终输出（从 conversation 中获取 assistant 消息）
    from app.services.conversation_service import conversation_service
    messages = conversation_service.list_turn_messages(started.turn.id)
    assistant_messages = [
        m for m in messages 
        if m.role == "assistant" and m.content_text
    ]
    
    if assistant_messages:
        return assistant_messages[-1].content_text
    else:
        return "子任务完成，但未生成输出"

def _build_sub_agent_prompt(
    self,
    task: dict,
    shared_context: str,
    previous_results: dict
) -> str:
    """构建子任务提示"""
    prompt_parts = []
    
    # 共享上下文
    if shared_context:
        prompt_parts.append(f"## 背景信息\n{shared_context}\n")
    
    # 依赖任务结果
    if previous_results:
        prompt_parts.append("## 前序任务结果\n")
        for task_id, result in previous_results.items():
            if result["status"] == "completed":
                prompt_parts.append(f"### {task_id}\n{result['output']}\n")
    
    # 任务描述
    prompt_parts.append(f"## 你的任务\n{task['description']}")
    
    # 任务特定上下文
    if task.get("context"):
        prompt_parts.append(f"\n{task['context']}")
    
    return "\n".join(prompt_parts)
```

---

### 4. 取消机制

#### 级联取消
```python
# backend/app/services/agent_service.py
async def cancel_run(self, run_id: str) -> Run:
    # 1. 查找当前 run 所属的 session
    run = self.conversation_service.get_run(run_id)
    if not run:
        raise NotFoundValueError("运行不存在")
    
    # 2. 查找所有 sub-session 的活跃 run
    sub_sessions = self.session_repo.find_by_parent_session_id(run.session_id)
    
    # 3. 递归取消所有 sub-agent
    for sub_session in sub_sessions:
        if sub_session.active_turn_id:
            active_turn = self.conversation_service.get_turn(sub_session.active_turn_id)
            if active_turn and active_turn.active_run_id:
                try:
                    await self.cancel_run(active_turn.active_run_id)
                except Exception as e:
                    logger.warning(f"取消子任务失败: {e}")
    
    # 4. 取消主 run（现有逻辑）
    cancel_event = self._cancel_events.get(run_id)
    if cancel_event:
        cancel_event.set()
    
    # ... 其余现有逻辑
```

#### 级联删除
```python
# backend/app/services/session_service.py
async def delete_session(self, session_id: str) -> None:
    # 1. 递归查找所有子 session
    sub_sessions = self.session_repo.find_sub_sessions_recursive(session_id)
    
    # 2. 先删除所有子 session（深度优先）
    for sub_session in reversed(sub_sessions):  # 从叶子节点开始
        await self._delete_session_data(sub_session.id)
    
    # 3. 删除主 session
    await self._delete_session_data(session_id)
    
    # 4. 清理 browser 资源
    await self.agent_service.cleanup_browser_for_session(session_id)

async def _delete_session_data(self, session_id: str) -> None:
    """删除单个 session 的所有数据"""
    # 删除 conversation events
    self.conversation_service.delete_session_events(session_id)
    
    # 删除 messages, runs, turns
    self.conversation_service.delete_session_conversation(session_id)
    
    # 删除 session
    self.session_repo.delete(session_id)
    
    # 清理上传的图片文件
    self._cleanup_session_uploads(session_id)
```

---

### 5. 多模态支持

#### 图片上传流程
```
用户在前端粘贴图片
    ↓
前端读取图片为 base64
    ↓
POST /api/sessions/{session_id}/upload
    ↓
后端保存到 storage/uploads/{session_id}/{timestamp}_{uuid}.png
    ↓
返回 attachment_id
    ↓
前端发送消息时携带 attachment_ids
    ↓
后端创建 Message 时关联 attachments
    ↓
构建 LLM 请求时转换为多模态格式
```

#### 上传 API
```python
# backend/app/api/upload.py
@router.post("/sessions/{session_id}/upload")
async def upload_image(
    session_id: str,
    file: UploadFile = File(...),
) -> dict:
    # 1. 验证 session 存在
    session = session_repo.get(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    
    # 2. 验证文件类型
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "只支持图片文件")
    
    # 3. 保存文件
    upload_dir = Path("storage/uploads") / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    file_id = uuid.uuid4().hex[:8]
    file_ext = Path(file.filename).suffix
    file_path = upload_dir / f"{timestamp}_{file_id}{file_ext}"
    
    async with aio.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)
    
    # 4. 记录 attachment 元数据
    attachment = MessageAttachment(
        id=f"att_{file_id}",
        type="image",
        mime_type=file.content_type,
        file_path=str(file_path),
        file_size=len(content),
        created_at=datetime.now()
    )
    
    return {
        "attachment_id": attachment.id,
        "file_path": str(file_path),
        "file_size": len(content)
    }
```

#### LLM 消息转换
```python
# backend/app/llm/openai_adapter.py
def _convert_messages(self, messages: list[LLMMessage]) -> list[dict]:
    openai_messages = []
    
    for msg in messages:
        openai_msg = {"role": msg.role}
        
        # 多模态内容
        if isinstance(msg.content, list):
            openai_msg["content"] = [
                self._convert_content_part(part) for part in msg.content
            ]
        elif msg.content:
            openai_msg["content"] = msg.content
        elif msg.role == "tool":
            openai_msg["content"] = ""
        
        # ... tool_calls, tool_call_id 处理
        openai_messages.append(openai_msg)
    
    return openai_messages

def _convert_content_part(self, part: LLMContentPart) -> dict:
    if part.type == "text":
        return {"type": "text", "text": part.text}
    elif part.type == "image_url":
        return {"type": "image_url", "image_url": part.image_url}
```

#### 图片清理任务
```python
# backend/app/services/cleanup_service.py
class CleanupService:
    async def cleanup_old_uploads(self, max_age_days: int = 1):
        """清理超过指定天数的上传文件"""
        upload_root = Path("storage/uploads")
        if not upload_root.exists():
            return
        
        cutoff = datetime.now() - timedelta(days=max_age_days)
        deleted_count = 0
        
        for session_dir in upload_root.iterdir():
            if not session_dir.is_dir():
                continue
            
            for file_path in session_dir.iterdir():
                if file_path.stat().st_mtime < cutoff.timestamp():
                    file_path.unlink()
                    deleted_count += 1
            
            # 删除空目录
            if not any(session_dir.iterdir()):
                session_dir.rmdir()
        
        logger.info(f"清理过期上传文件: {deleted_count} 个")

# 在 agent_service 启动时注册定时任务
def start_background_tasks(self):
    # ... 现有逻辑
    self._cleanup_task = asyncio.create_task(
        self._cleanup_loop(),
        name="upload-cleanup"
    )

async def _cleanup_loop(self):
    cleanup_service = CleanupService()
    while True:
        try:
            await cleanup_service.cleanup_old_uploads(max_age_days=1)
        except Exception:
            logger.exception("清理上传文件失败")
        await asyncio.sleep(3600)  # 每小时执行一次
```

---

### 6. UI 交互设计

#### 树形结构展示
```typescript
// frontend/src/features/conversation/SubAgentTree.tsx
interface SubAgentNode {
  sessionId: string;
  title: string;
  status: 'running' | 'completed' | 'failed' | 'timeout';
  parentSessionId: string | null;
  children: SubAgentNode[];
}

// 递归构建树
function buildTree(sessions: Session[]): SubAgentNode[] {
  const nodeMap = new Map<string, SubAgentNode>();
  const roots: SubAgentNode[] = [];
  
  // 构建节点
  sessions.forEach(session => {
    nodeMap.set(session.id, {
      sessionId: session.id,
      title: session.title,
      status: session.status,
      parentSessionId: session.parentSessionId,
      children: []
    });
  });
  
  // 建立父子关系
  nodeMap.forEach(node => {
    if (node.parentSessionId) {
      const parent = nodeMap.get(node.parentSessionId);
      if (parent) {
        parent.children.push(node);
      }
    } else {
      roots.push(node);
    }
  });
  
  return roots;
}
```

#### 点击进入 Sub-Agent 详情
```typescript
// 用户点击 sub-agent 节点
function onSubAgentClick(sessionId: string) {
  // 1. 打开侧边栏或弹窗
  // 2. 加载 sub-agent 的完整对话历史
  // 3. 支持用户提问（只读模式）
  
  openSubAgentDialog({
    sessionId,
    mode: 'readonly-chat',  // 可以提问但不影响原任务
    onAsk: async (question: string) => {
      // 创建一个临时的查询 session，不影响原 sub-session
      const answer = await askSubAgent(sessionId, question);
      return answer;
    }
  });
}
```

#### 只读对话实现
```python
# backend/app/api/sub_agent.py
@router.post("/sub-agents/{session_id}/ask")
async def ask_sub_agent(
    session_id: str,
    request: SubAgentAskRequest
) -> dict:
    """
    向已完成的 sub-agent 提问（不影响原任务）
    
    实现：使用 sub-agent 的历史作为上下文，调用 LLM 回答问题，不创建新的 turn/run
    """
    # 1. 验证 session 是 sub-session
    session = session_repo.get(session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    if not session.is_sub_session:
        raise HTTPException(400, "只能查询子会话")
    
    # 2. 获取 sub-agent 的完整历史
    snapshot = conversation_service.get_snapshot(session_id)
    
    # 3. 构建临时查询上下文
    context_messages = []
    
    # 添加 sub-agent 的对话历史（最近 20 条消息）
    for turn in snapshot.turns[-5:]:  # 最近5个 turn
        for msg in conversation_service.list_turn_messages(turn.id):
            if msg.role in ("user", "assistant"):
                context_messages.append(
                    LLMMessage(role=msg.role, content=msg.content_text)
                )
    
    # 添加用户问题
    context_messages.append(
        LLMMessage(role="user", content=request.question)
    )
    
    # 4. 调用 LLM（不创建新 turn/run）
    resolved_llm = llm_provider_service.resolve_llm_config(None, None)
    llm = LLMAdapterFactory.create(resolved_llm)
    
    response = await llm.complete(context_messages, tools=None)
    
    return {
        "answer": response.content or "无响应",
        "context_turns": len(snapshot.turns[-5:])
    }

class SubAgentAskRequest(BaseModel):
    question: str
```

---

## 实现计划

### Phase 1: Sub-Agent 核心功能
1. 扩展数据模型（Session 表、级联删除）
2. 实现 DelegateTool（无依赖版本）
3. 实现 sub-session 创建和执行逻辑
4. 实现级联取消机制
5. 前端树形展示（基础版）

### Phase 2: 依赖关系支持
1. 实现依赖图构建和拓扑排序
2. 实现分批执行逻辑
3. 前端展示依赖关系

### Phase 3: 多模态支持
1. 扩展 Message/LLMMessage 模型
2. 实现图片上传 API
3. 实现 LLM 消息多模态转换
4. 前端图片粘贴和预览
5. 实现图片清理任务

### Phase 4: 交互增强
1. 实现只读对话功能
2. 前端 sub-agent 详情弹窗
3. 优化树形展示（状态实时更新）

---

## 测试策略

### 单元测试
- `DelegateTool` 的依赖图构建和拓扑排序
- 级联删除逻辑
- 多模态消息转换

### 集成测试
- 创建 sub-session → 执行 → 汇总结果
- 取消主任务 → 验证 sub-agent 同步取消
- 删除主 session → 验证 sub-session 清理
- 上传图片 → 发送消息 → LLM 分析 → 清理过期文件

### 性能测试
- 并发 10 个 sub-agent 的资源消耗
- 超时处理的准确性
- 图片上传和清理的效率

---

## 风险与缓解

### 风险1：Sub-Agent 过多导致资源耗尽
- **缓解**：限制单次 delegate 最多 10 个任务（schema 中强制）
- **缓解**：限制 sub-agent 的嵌套深度为 1（不允许 sub-agent 调用 delegate 工具）
- **缓解**：监控并发 sub-agent 数量，超过阈值时拒绝新的 delegate 请求

### 风险2：级联删除遗漏数据
- **缓解**：数据库外键约束 `ON DELETE CASCADE` + 应用层递归删除双重保障
- **缓解**：在 session_repo 中增加 `find_orphan_sessions()` 方法，定期检查孤儿 session
- **缓解**：删除操作记录审计日志，便于追踪问题

### 风险3：图片文件泄漏（未清理）
- **缓解**：定时任务每小时清理超过 1 天的文件
- **缓解**：session 删除时同步清理 `storage/uploads/{session_id}/` 目录
- **缓解**：监控 `storage/uploads/` 目录大小，超过阈值时告警

### 风险4：依赖图循环依赖
- **缓解**：拓扑排序前检测环，如有环则立即返回错误
- **缓解**：在 `_validate_dependencies()` 中预先验证

### 风险5：Sub-Agent 超时后主 Agent 无法继续
- **缓解**：超时任务标记为 "timeout" 状态，但不阻止其他任务完成
- **缓解**：主 agent 收到部分结果也能继续工作（在工具输出中明确标注哪些任务超时）

### 风险6：图片过大导致 LLM 请求失败
- **缓解**：上传接口限制图片大小（最大 10MB）
- **缓解**：前端压缩大图片后再上传
- **缓解**：捕获 LLM API 错误并返回友好提示

---

## 开放问题

1. **Sub-Agent 是否需要支持嵌套？** 
   - 当前设计：不支持（sub-agent 不能再调用 delegate 工具）
   - 实现方式：在 DelegateTool 中检查 `session.is_sub_session`，如果为 True 则拒绝执行
   - 未来可扩展：如果需要支持，需要限制嵌套深度（如最多2层）

2. **Sub-Agent 的 agent_mode 如何确定？**
   - 当前设计：继承主 agent 的 agent_mode（build/plan）
   - 未来可扩展：允许 delegate 工具在每个任务中指定 agent_mode

3. **图片是否需要支持云存储？**
   - 当前设计：本地文件系统 `storage/uploads/`
   - 未来可扩展：通过配置项支持 S3/OSS，保持接口不变

4. **是否需要限制单个 session 的总上传大小？**
   - 当前设计：单张图片限制 10MB，session 总大小不限
   - 建议扩展：增加 session 级别的配额（如 100MB），超过后拒绝上传

5. **Sub-Agent 失败是否应该立即终止所有任务？**
   - 当前设计：不终止，继续执行其他任务，最终汇总时标记失败的任务
   - 可选设计：增加 `fail_fast` 参数，允许用户选择是否快速失败

---

## 参考资料

- OpenAI Vision API: https://platform.openai.com/docs/guides/vision
- Claude 多模态: https://docs.anthropic.com/claude/docs/vision
- Asyncio 并发控制: https://docs.python.org/3/library/asyncio-task.html
