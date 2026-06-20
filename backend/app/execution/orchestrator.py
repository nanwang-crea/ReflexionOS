"""
多 Worker 并行执行编排器

设计文档: docs/superpowers/specs/2026-06-19-multi-worker-parallel-execution-design.md
实施计划: docs/superpowers/plans/2026-06-20-multi-worker-parallel-execution.md
"""

import asyncio
import copy
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.execution.context_manager import LoopContext
from app.execution.models import LoopResult

logger = logging.getLogger(__name__)


@dataclass
class WorkerSpec:
    """描述分配给单个 worker 的子任务"""
    worker_id: str
    task: str
    files: list[str]  # 必填，用于冲突检测和文件访问边界
    context_hint: str = ""
    priority: int = 0
    depends_on: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=lambda: [
        "file_read", "file_write", "file_edit", "session_recall", "task_complete"
    ])


@dataclass
class WorkerResult:
    """单个 worker 的执行结果"""
    worker_id: str
    status: Literal["success", "failed", "timeout"]
    result: str
    loop_result: LoopResult | None = None
    events: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    tokens_used: int = 0


@dataclass
class OrchestrationResult:
    """整个编排的聚合结果"""
    status: Literal["success", "partial", "failed", "single_loop_fallback"]
    final_output: str
    worker_results: list[WorkerResult] = field(default_factory=list)
    total_duration_ms: int = 0
    total_tokens: int = 0
    synthesis_events: list[dict] = field(default_factory=list)
    decompose_tokens: int = 0
    synthesis_tokens: int = 0


@dataclass
class OrchestratorConfig:
    """编排器配置"""
    max_workers: int = 5
    worker_timeout_s: int = 300
    max_nesting_depth: int = 2
    worker_model: str | None = None
    synthesis_model: str | None = None
    enable_reflection: bool = False
    enable_plan_persistence: bool = True
    worker_max_iterations: int = 5
    worker_max_tool_calls: int = 10
    worker_allowed_tools: list[str] = field(default_factory=lambda: [
        "file_read", "file_write", "file_edit", "session_recall", "task_complete"
    ])
    max_concurrent_workers: int = 3
    max_concurrent_tools: int = 5
    worker_retry_count: int = 1
    worker_retry_delay_s: int = 5
    force_orchestration: bool = False
    disable_orchestration: bool = False

    @classmethod
    def from_settings(cls, settings: Any = None) -> "OrchestratorConfig":
        """从应用配置创建"""
        if settings is None:
            from app.config.settings import config_manager
            settings = config_manager.settings

        orch_settings = getattr(settings, 'orchestrator', None)

        config = cls()
        if orch_settings:
            config.max_workers = getattr(orch_settings, 'max_workers', 5)
            config.worker_timeout_s = getattr(orch_settings, 'worker_timeout_s', 300)
            config.max_nesting_depth = getattr(orch_settings, 'max_nesting_depth', 2)
            config.worker_model = getattr(orch_settings, 'worker_model', None)
            config.synthesis_model = getattr(orch_settings, 'synthesis_model', None)
            config.enable_reflection = getattr(orch_settings, 'enable_reflection', False)
            config.enable_plan_persistence = getattr(orch_settings, 'enable_plan_persistence', True)
            config.worker_max_iterations = getattr(orch_settings, 'worker_max_iterations', 5)
            config.worker_max_tool_calls = getattr(orch_settings, 'worker_max_tool_calls', 10)
            config.max_concurrent_workers = getattr(orch_settings, 'max_concurrent_workers', 3)
            config.max_concurrent_tools = getattr(orch_settings, 'max_concurrent_tools', 5)
            config.worker_retry_count = getattr(orch_settings, 'worker_retry_count', 1)
            config.worker_retry_delay_s = getattr(orch_settings, 'worker_retry_delay_s', 5)
            config.force_orchestration = getattr(orch_settings, 'force_orchestration', False)
            config.disable_orchestration = getattr(orch_settings, 'disable_orchestration', False)

        return config


@dataclass
class ContextSnapshot:
    """Worker 执行上下文的只读快照"""
    seed_messages: list[dict[str, Any]]
    system_sections: list[str]
    project_path: str | None
    session_id: str
    project_id: str | None = None
    supplemental_context: str | None = None
    snapshot_timestamp: datetime = field(default_factory=datetime.now)
    parent_run_id: str = ""
    depth: int = 0

    def __post_init__(self):
        """深拷贝输入数据，确保不可变性"""
        self.seed_messages = copy.deepcopy(self.seed_messages)
        self.system_sections = list(self.system_sections)

    def to_loop_context(self, worker_id: str, task: str) -> LoopContext:
        """为指定 Worker 创建独立的 LoopContext"""
        return LoopContext.from_run_input(
            task=task,
            project_path=self.project_path,
            run_id=f"{self.parent_run_id}-worker-{worker_id}",
            session_id=self.session_id,
            agent_mode="build",
            seed_messages=copy.deepcopy(self.seed_messages),
            system_sections=list(self.system_sections),
            supplemental_context=self.supplemental_context,
        )


def should_orchestrate(task: str, config: OrchestratorConfig) -> bool:
    """
    V1 策略：仅对明确编号列表触发编排。
    不使用启发式规则（长度、关键词），避免假阳性误判。
    """
    if config.disable_orchestration:
        return False
    if config.force_orchestration:
        return True

    # 匹配编号列表项：1. 2. 3. 或 1、2、3、或 1) 2) 3)
    # 每项内容至少 10 个字符（排除编号本身）
    # 多行格式：每行以编号开头
    numbered_pattern = re.compile(
        r'(?:^|\n)\s*(?!#)\d+[\.\、\)]\s*(\S.{9,})',
        re.MULTILINE
    )
    matches = numbered_pattern.findall(task)
    if len(matches) >= 2:
        return True

    # 单行格式：1. xxx 2. yyy 3. zzz
    # 使用前瞻断言分割
    inline_pattern = re.compile(
        r'\d+[\.\、\)]\s*',
    )
    parts = inline_pattern.split(task)
    # 过滤掉空字符串和标题
    valid_parts = [p.strip() for p in parts if p.strip() and not p.strip().startswith('#')]
    if len(valid_parts) >= 2:
        # 检查每项是否至少 10 个字符
        if all(len(p) >= 10 for p in valid_parts):
            return True

    return False


def _get_github_default_branch(owner: str, repo: str, timeout: int = 5) -> str:
    """获取 GitHub 仓库的默认分支"""
    try:
        import requests
        url = f"https://api.github.com/repos/{owner}/{repo}"
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            return data.get("default_branch", "main")
        elif response.status_code == 403:
            logger.warning("GitHub API 限流，尝试使用 git ls-remote")
            try:
                import subprocess
                result = subprocess.run(
                    ['git', 'ls-remote', '--symref', f'https://github.com/{owner}/{repo}', 'HEAD'],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.startswith('ref:'):
                            ref_path = line.split()[1]
                            return ref_path.split('/')[-1]
            except Exception as e:
                logger.warning("git ls-remote 失败: %s", e)
            return "main"
        else:
            logger.warning("无法获取 %s/%s 的默认分支 (状态码: %d)", owner, repo, response.status_code)
            return "main"
    except Exception as e:
        logger.warning("获取 %s/%s 的默认分支失败: %s", owner, repo, e)
        return "main"


class OrchestratorLoop:
    """多 Worker 并行执行编排器"""

    DECOMPOSE_PROMPT = """你是一个编排器。将以下任务分解为可由独立 worker 并行执行的独立子任务。

任务: {task}
对话上下文: {recent_messages}

文件分配约束（关键）：
- 每个子任务必须明确列出将读取或修改的文件路径
- 不同子任务的文件列表不能有交集（一个文件只能被一个 worker 操作）
- 如果多个子任务需要操作同一文件，将它们合并为一个子任务
- 如果无法避免文件交集，在 context_hint 中标注预期冲突

输出 JSON:
{{
  "workers": [
    {{"worker_id": "w_1", "task": "...", "context_hint": "...", "files": ["path/a.py", "path/b.py"], "priority": 0}},
    ...
  ]
}}
"""

    SYNTHESIZE_PROMPT = """你是一个编排器。多个 worker 已并行完成了子任务。
将它们的结果合成为单一连贯的回复。

原始任务: {task}

Worker 结果:
{worker_results}

请提供一个统一的回复，整合所有成功的结果并说明任何失败。"""

    def __init__(
        self,
        llm: Any,
        config: OrchestratorConfig,
        context: LoopContext,
        tool_registry: Any = None,
        event_callback: Any = None,
    ):
        self.llm = llm
        self.config = config
        self.context = context
        self.tool_registry = tool_registry
        self.event_callback = event_callback
        self._worker_semaphore = asyncio.Semaphore(config.max_concurrent_workers)
        self._tool_semaphore = asyncio.Semaphore(config.max_concurrent_tools)

    async def run(self, task: str) -> OrchestrationResult:
        """执行编排流程"""
        start_time = time.time()

        try:
            # Phase 1: DECOMPOSE
            worker_specs, decompose_tokens = await self._decompose(task)

            # Phase 2: SNAPSHOT
            snapshot = ContextSnapshot(
                seed_messages=list(self.context.messages),
                system_sections=list(self.context.system_sections),
                project_path=self.context.project_path,
                session_id=self.context.session_id,
                parent_run_id=self.context.run_id,
                depth=0,
            )

            # Phase 3: FAN-OUT
            worker_results = await self._fan_out(worker_specs, snapshot)

            # Phase 4: SYNTHESIZE
            final_output, synthesis_tokens = await self._synthesize(task, worker_results)

            total_duration_ms = int((time.time() - start_time) * 1000)
            total_tokens = decompose_tokens + sum(r.tokens_used for r in worker_results) + synthesis_tokens

            # Determine status
            success_count = sum(1 for r in worker_results if r.status == "success")
            if success_count == len(worker_results):
                status = "success"
            elif success_count > 0:
                status = "partial"
            else:
                status = "failed"

            return OrchestrationResult(
                status=status,
                final_output=final_output,
                worker_results=worker_results,
                total_duration_ms=total_duration_ms,
                total_tokens=total_tokens,
                decompose_tokens=decompose_tokens,
                synthesis_tokens=synthesis_tokens,
            )

        except Exception as e:
            logger.error("编排失败，回退到单循环: %s", e)
            return OrchestrationResult(
                status="single_loop_fallback",
                final_output=f"编排失败: {str(e)}",
                total_duration_ms=int((time.time() - start_time) * 1000),
            )

    async def _decompose(self, task: str) -> tuple[list[WorkerSpec], int]:
        """分解任务为多个 WorkerSpec"""
        from app.llm import LLMMessage, MessageRole

        recent_messages = ""
        for msg in self.context.messages[-5:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                recent_messages += f"{role}: {content[:200]}\n"

        prompt = self.DECOMPOSE_PROMPT.format(task=task, recent_messages=recent_messages)

        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="你是一个任务编排器，负责将任务分解为可并行执行的子任务。"),
            LLMMessage(role=MessageRole.USER, content=prompt),
        ]

        response = await self.llm.complete(messages)
        decompose_tokens = response.usage.get("total_tokens", 0)

        # Parse JSON response
        import json
        try:
            # Extract JSON from response
            content = response.content or ""
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                raise ValueError("无法从响应中提取 JSON")

            data = json.loads(json_match.group())
            workers = data.get("workers", [])

            if not workers:
                raise ValueError("分解结果为空")

            if len(workers) > self.config.max_workers:
                raise ValueError(f"Worker 数量 ({len(workers)}) 超过最大限制 ({self.config.max_workers})")

            # Validate and create WorkerSpec
            specs = []
            all_files = set()
            for w in workers:
                worker_id = w.get("worker_id", f"w_{len(specs)}")
                task_desc = w.get("task", "")
                files = w.get("files", [])
                context_hint = w.get("context_hint", "")
                priority = w.get("priority", 0)

                if not task_desc:
                    raise ValueError(f"Worker {worker_id} 的 task 为空")
                if not files:
                    raise ValueError(f"Worker {worker_id} 的 files 为空")

                # Check file conflicts
                file_set = set(files)
                conflicts = file_set & all_files
                if conflicts:
                    raise ValueError(f"文件冲突: {conflicts}")
                all_files.update(file_set)

                specs.append(WorkerSpec(
                    worker_id=worker_id,
                    task=task_desc,
                    files=files,
                    context_hint=context_hint,
                    priority=priority,
                ))

            return specs, decompose_tokens

        except Exception as e:
            logger.error("分解失败: %s", e)
            raise

    async def _fan_out(self, worker_specs: list[WorkerSpec], snapshot: ContextSnapshot) -> list[WorkerResult]:
        """并行执行所有 Worker"""
        tasks = [self._run_worker(spec, snapshot) for spec in worker_specs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        worker_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                worker_results.append(WorkerResult(
                    worker_id=worker_specs[i].worker_id,
                    status="failed",
                    result=str(result),
                ))
            else:
                worker_results.append(result)

        return worker_results

    async def _run_worker(self, spec: WorkerSpec, snapshot: ContextSnapshot) -> WorkerResult:
        """运行单个 Worker，受 Semaphore 控制"""
        start_time = time.time()

        for attempt in range(1 + self.config.worker_retry_count):
            try:
                async with self._worker_semaphore:
                    result = await asyncio.wait_for(
                        self._execute_worker(spec, snapshot),
                        timeout=self.config.worker_timeout_s,
                    )
                    return result

            except asyncio.TimeoutError:
                if attempt < self.config.worker_retry_count:
                    delay = self.config.worker_retry_delay_s * (attempt + 1)
                    logger.warning("Worker %s 超时，%ds 后重试", spec.worker_id, delay)
                    await asyncio.sleep(delay)
                    continue
                return WorkerResult(
                    worker_id=spec.worker_id,
                    status="timeout",
                    result=f"Worker {spec.worker_id} 执行超时 ({self.config.worker_timeout_s}s)",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            except Exception as e:
                if attempt < self.config.worker_retry_count:
                    delay = self.config.worker_retry_delay_s * (attempt + 1)
                    logger.warning("Worker %s 失败 (%s)，%ds 后重试", spec.worker_id, e, delay)
                    await asyncio.sleep(delay)
                    continue
                return WorkerResult(
                    worker_id=spec.worker_id,
                    status="failed",
                    result=str(e),
                    duration_ms=int((time.time() - start_time) * 1000),
                )

    async def _execute_worker(self, spec: WorkerSpec, snapshot: ContextSnapshot) -> WorkerResult:
        """执行单个 Worker"""
        from app.execution.rapid_loop import RapidExecutionLoop
        from app.llm import LLMAdapterFactory, LLMMessage, MessageRole

        start_time = time.time()

        # Create worker context
        worker_context = snapshot.to_loop_context(spec.worker_id, spec.task)

        # Create worker LLM
        resolved_llm = self._resolve_worker_llm()
        worker_llm = LLMAdapterFactory.create(resolved_llm)

        # Create event buffer
        events = []

        async def worker_event_callback(event_type: str, data: dict):
            events.append({"type": event_type, "data": data, "worker_id": spec.worker_id})
            if self.event_callback:
                await self.event_callback(event_type, data)

        # Create worker tool registry (simplified - use main registry for now)
        worker_registry = self.tool_registry

        # Create worker loop
        worker_loop = RapidExecutionLoop(
            llm=worker_llm,
            tool_registry=worker_registry,
            event_callback=worker_event_callback,
            max_steps=self.config.worker_max_iterations,
        )

        # Run worker
        loop_result = await worker_loop.run(worker_context)

        duration_ms = int((time.time() - start_time) * 1000)
        tokens_used = sum(e.get("data", {}).get("tokens", 0) for e in events)

        return WorkerResult(
            worker_id=spec.worker_id,
            status="success" if loop_result.status == "completed" else "failed",
            result=loop_result.result or "",
            loop_result=loop_result,
            events=events,
            duration_ms=duration_ms,
            tokens_used=tokens_used,
        )

    async def _synthesize(self, task: str, worker_results: list[WorkerResult]) -> tuple[str, int]:
        """合成所有 Worker 结果"""
        from app.llm import LLMMessage, MessageRole

        worker_results_text = ""
        for result in worker_results:
            status_emoji = "✅" if result.status == "success" else "❌"
            worker_results_text += f"\n--- Worker {result.worker_id} ({result.status}) {status_emoji} ---\n"
            worker_results_text += result.result or "(无结果)"
            worker_results_text += "\n"

        prompt = self.SYNTHESIZE_PROMPT.format(task=task, worker_results=worker_results_text)

        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="你是一个任务编排器，负责合并多个并行任务的结果。"),
            LLMMessage(role=MessageRole.USER, content=prompt),
        ]

        response = await self.llm.complete(messages)
        synthesis_tokens = response.usage.get("total_tokens", 0)

        return response.content or "", synthesis_tokens

    def _resolve_worker_llm(self) -> Any:
        """解析 Worker 使用的 LLM 配置"""
        from app.config.settings import config_manager
        from app.models.llm_config import ResolvedLLMConfig

        llm_provider_service = getattr(config_manager, 'llm_provider_service', None)
        if llm_provider_service:
            return llm_provider_service.resolve_llm_config()

        # Fallback: create a basic config
        settings = config_manager.settings
        llm_settings = settings.llm
        return ResolvedLLMConfig(
            provider_type=llm_settings.provider_type,
            model=self.config.worker_model or llm_settings.model,
            api_key=llm_settings.api_key,
            base_url=llm_settings.base_url,
            temperature=llm_settings.temperature,
            max_tokens=llm_settings.max_tokens,
            context_window=llm_settings.context_window,
        )
