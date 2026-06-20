"""Orchestrator 数据结构与配置单元测试

验证数据结构的正确性、序列化、配置映射等
"""

import pytest
from datetime import datetime
from app.execution.orchestrator import (
    WorkerSpec,
    WorkerResult,
    OrchestrationResult,
    OrchestratorConfig,
    ContextSnapshot,
)
from app.execution.context_manager import LoopContext


class TestWorkerSpec:
    """WorkerSpec 测试"""

    def test_create_with_required_fields(self):
        """创建 WorkerSpec 必填字段"""
        spec = WorkerSpec(
            worker_id="w_1",
            task="重构 auth.py",
            files=["auth.py"],
        )
        assert spec.worker_id == "w_1"
        assert spec.task == "重构 auth.py"
        assert spec.files == ["auth.py"]
        assert spec.context_hint == ""
        assert spec.priority == 0
        assert spec.depends_on == []

    def test_default_allowed_tools(self):
        """默认工具白名单"""
        spec = WorkerSpec(worker_id="w_1", task="test", files=["test.py"])
        assert "file_read" in spec.allowed_tools
        assert "file_write" in spec.allowed_tools
        assert "file_edit" in spec.allowed_tools
        assert "session_recall" in spec.allowed_tools
        assert "task_complete" in spec.allowed_tools

    def test_custom_allowed_tools(self):
        """自定义工具白名单"""
        spec = WorkerSpec(
            worker_id="w_1",
            task="test",
            files=["test.py"],
            allowed_tools=["file_read", "grep"],
        )
        assert spec.allowed_tools == ["file_read", "grep"]


class TestWorkerResult:
    """WorkerResult 测试"""

    def test_create_success_result(self):
        """创建成功结果"""
        result = WorkerResult(
            worker_id="w_1",
            status="success",
            result="任务完成",
            duration_ms=1000,
            tokens_used=500,
        )
        assert result.worker_id == "w_1"
        assert result.status == "success"
        assert result.result == "任务完成"
        assert result.duration_ms == 1000
        assert result.tokens_used == 500

    def test_create_failed_result(self):
        """创建失败结果"""
        result = WorkerResult(
            worker_id="w_1",
            status="failed",
            result="错误信息",
        )
        assert result.status == "failed"

    def test_create_timeout_result(self):
        """创建超时结果"""
        result = WorkerResult(
            worker_id="w_1",
            status="timeout",
            result="执行超时",
        )
        assert result.status == "timeout"


class TestOrchestrationResult:
    """OrchestrationResult 测试"""

    def test_create_success_result(self):
        """创建成功编排结果"""
        result = OrchestrationResult(
            status="success",
            final_output="所有任务完成",
            total_duration_ms=5000,
            total_tokens=1000,
            decompose_tokens=200,
            synthesis_tokens=300,
        )
        assert result.status == "success"
        assert result.final_output == "所有任务完成"
        assert result.decompose_tokens == 200
        assert result.synthesis_tokens == 300

    def test_create_partial_result(self):
        """创建部分成功结果"""
        result = OrchestrationResult(
            status="partial",
            final_output="部分任务完成",
        )
        assert result.status == "partial"

    def test_create_single_loop_fallback(self):
        """创建单循环回退结果"""
        result = OrchestrationResult(
            status="single_loop_fallback",
            final_output="编排失败，回退到单循环",
        )
        assert result.status == "single_loop_fallback"


class TestOrchestratorConfig:
    """OrchestratorConfig 测试"""

    def test_default_values(self):
        """默认配置值"""
        config = OrchestratorConfig()
        assert config.max_workers == 5
        assert config.worker_timeout_s == 300
        assert config.max_nesting_depth == 2
        assert config.worker_max_iterations == 5
        assert config.worker_max_tool_calls == 10
        assert config.max_concurrent_workers == 3
        assert config.max_concurrent_tools == 5
        assert config.worker_retry_count == 1
        assert config.worker_retry_delay_s == 5
        assert config.force_orchestration is False
        assert config.disable_orchestration is False

    def test_custom_values(self):
        """自定义配置值"""
        config = OrchestratorConfig(
            max_workers=10,
            worker_timeout_s=600,
            force_orchestration=True,
        )
        assert config.max_workers == 10
        assert config.worker_timeout_s == 600
        assert config.force_orchestration is True


class TestContextSnapshot:
    """ContextSnapshot 测试"""

    def test_create_snapshot(self):
        """创建快照"""
        snapshot = ContextSnapshot(
            seed_messages=[{"role": "user", "content": "test"}],
            system_sections=["system prompt"],
            project_path="/path/to/project",
            session_id="session-123",
            project_id="project-456",
        )
        assert snapshot.session_id == "session-123"
        assert snapshot.project_id == "project-456"
        assert snapshot.depth == 0

    def test_to_loop_context(self):
        """转换为 LoopContext"""
        snapshot = ContextSnapshot(
            seed_messages=[{"role": "user", "content": "test"}],
            system_sections=["system prompt"],
            project_path="/path/to/project",
            session_id="session-123",
            parent_run_id="run-123",
        )
        context = snapshot.to_loop_context("w_1", "子任务")
        assert context.task == "子任务"
        assert context.project_path == "/path/to/project"
        assert context.session_id == "session-123"
        assert "w_1" in context.run_id
        assert context.orchestrated is False  # LoopContext 默认值
        assert context.worker_id is None  # LoopContext 默认值

    def test_snapshot_immutability(self):
        """快照不可变性（深拷贝）"""
        original_messages = [{"role": "user", "content": "test"}]
        snapshot = ContextSnapshot(
            seed_messages=original_messages,
            system_sections=["system prompt"],
            project_path="/path/to/project",
            session_id="session-123",
        )
        # 修改原始列表不应影响快照
        original_messages.append({"role": "assistant", "content": "response"})
        assert len(snapshot.seed_messages) == 1
