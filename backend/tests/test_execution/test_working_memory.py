"""WorkingMemory 和 MemoryExtractor 单元测试"""

import pytest
from app.memory.working_memory import WorkingMemory, MemoryEntry, MemoryEntryType
from app.memory.memory_extractor import MemoryExtractor
from app.memory.session_tracker import SessionTracker


class TestWorkingMemory:
    """WorkingMemory 数据模型测试"""

    def test_empty_memory_is_empty(self):
        wm = WorkingMemory()
        assert wm.is_empty()

    def test_add_decision(self):
        wm = WorkingMemory()
        wm.add_decision("使用 SQLite", "轻量级，无需额外部署", source="model")
        assert len(wm.decisions) == 1
        assert wm.decisions[0].key == "使用 SQLite"
        assert wm.decisions[0].value == "轻量级，无需额外部署"

    def test_set_variable(self):
        wm = WorkingMemory()
        wm.set_variable("PORT", "8080")
        assert wm.variables["PORT"].value == "8080"

    def test_set_variable_update(self):
        wm = WorkingMemory()
        wm.set_variable("PORT", "8080")
        wm.set_variable("PORT", "3000")
        assert wm.variables["PORT"].value == "3000"
        assert len(wm.variables) == 1

    def test_add_error(self):
        wm = WorkingMemory()
        wm.add_error("command_error", "`npm test` → exit code 1")
        assert len(wm.errors) == 1
        assert wm.errors[0].key == "command_error"

    def test_to_prompt_section_empty(self):
        wm = WorkingMemory()
        assert wm.to_prompt_section() == ""

    def test_to_prompt_section_with_all_types(self):
        """WM 注入包含 decisions、variables、errors"""
        wm = WorkingMemory()
        wm.add_decision("用 FastAPI", "性能好", source="model")
        wm.set_variable("PORT", "8080")
        wm.add_error("import_error", "No module named 'foo'")
        section = wm.to_prompt_section()
        assert "🎯 Key decisions:" in section
        assert "⚙️ Current state:" in section
        assert "⚠️ Errors encountered:" in section

    def test_to_prompt_section_includes_behavioral_instructions(self):
        """WM 注入应包含行为指令，提醒模型避免重复工作"""
        wm = WorkingMemory()
        wm.add_decision("d1", "Use approach X", "simpler")
        section = wm.to_prompt_section()
        assert "DO NOT re-read" in section or "session_recall" in section

    def test_to_prompt_section_token_budget(self):
        """Token 预算淘汰机制"""
        wm = WorkingMemory(max_tokens=50)  # 极小预算
        # 填充大量数据
        for i in range(20):
            wm.add_error(f"err_{i}", f"error description {i} " * 20)
        section = wm.to_prompt_section()
        # 应该被截断或淘汰
        assert len(section) < 2000  # 粗略验证

    def test_eviction_removes_errors_first(self):
        """淘汰顺序：errors 最先被淘汰"""
        wm = WorkingMemory(max_tokens=50)
        wm.add_error("err1", "x" * 100)
        wm.add_error("err2", "y" * 100)
        wm.add_error("err3", "z" * 100)
        wm.add_decision("d1", "important decision")
        wm.to_prompt_section()
        # errors 应该被缩减到 2 个
        assert len(wm.errors) <= 2

    def test_eviction_removes_variables_second(self):
        """淘汰顺序：variables 第二被淘汰"""
        wm = WorkingMemory(max_tokens=50)
        for i in range(20):
            wm.set_variable(f"VAR_{i}", f"value_{i}" * 10)
        wm.to_prompt_section()
        assert len(wm.variables) <= 10

    def test_full_update_roundtrip(self):
        """WM 包含 decisions、variables、errors"""
        wm = WorkingMemory()
        wm.add_decision("approach", "Use Strategy pattern", "more flexible")
        wm.set_variable("api_version", "v2")
        wm.add_error("auth", "401 Unauthorized", "check token")
        prompt = wm.to_prompt_section()
        assert "approach" in prompt
        assert "Strategy" in prompt
        assert "api_version" in prompt
        assert "v2" in prompt
        assert "auth" in prompt
        assert "401" in prompt

    def test_serialization_roundtrip(self):
        """序列化/反序列化保留 decisions 和 variables"""
        wm = WorkingMemory()
        wm.add_decision("d1", "Use regex extraction", "Avoids LLM latency")
        wm.set_variable("api_version", "v2")
        data = wm.to_dict()
        wm2 = WorkingMemory.from_dict(data)
        assert len(wm2.decisions) == 1
        assert wm2.decisions[0].key == "d1"
        assert wm2.variables["api_version"].value == "v2"

    def test_partial_slots_before_full_slots(self):
        wm = WorkingMemory()
        wm.add_decision("d1", "test")
        assert not wm.is_empty()
        section = wm.to_prompt_section()
        assert "🎯 Key decisions:" in section

    def test_partial_slots_clears_all_before_rebuild(self):
        wm = WorkingMemory()
        wm.add_decision("old_decision", "old")
        wm.set_variable("old_var", "old")
        wm.add_decision("new_decision", "new")
        section = wm.to_prompt_section()
        assert "new_decision" in section

    def test_concurrent_access(self):
        """并发安全性测试"""
        import threading
        wm = WorkingMemory()
        errors = []

        def add_decisions(prefix):
            try:
                for i in range(100):
                    wm.add_decision(f"{prefix}_d_{i}", f"value {i}")
                    wm.set_variable(f"{prefix}_v_{i}", f"val {i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_decisions, args=(f"t{i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # 所有 decisions 应该都存在（400 个）
        assert len(wm.decisions) == 400


class TestMemoryExtractor:
    """MemoryExtractor 自动提取测试"""

    def test_extract_from_file_read_tracks_in_session(self):
        """文件读取应记录到 SessionTracker"""
        wm = WorkingMemory()
        tracker = SessionTracker()
        ext = MemoryExtractor(wm, session_tracker=tracker)
        ext.extract("file", {"action": "read", "path": "src/main.py"}, "class Main:\n    pass", step=1)
        # 文件读取不写入 WM，只记录到 SessionTracker
        assert wm.is_empty()
        # SessionTracker 应记录文件读取
        assert "src/main.py" in tracker.read_files

    def test_extract_from_file_read_skips_error(self):
        wm = WorkingMemory()
        tracker = SessionTracker()
        ext = MemoryExtractor(wm, session_tracker=tracker)
        ext.extract("file", {"action": "read", "path": "missing.py"}, "Error: file not found", step=1)
        assert wm.is_empty()
        # SessionTracker 记录所有访问尝试（包括失败的），这是正确的
        assert "missing.py" in tracker.read_files

    def test_extract_from_edit_tracks_in_session(self):
        """文件编辑应记录到 SessionTracker 的 modified_files"""
        wm = WorkingMemory()
        tracker = SessionTracker()
        ext = MemoryExtractor(wm, session_tracker=tracker)
        ext.extract("edit", {"action": "str_replace", "path": "config.py"}, "Successfully replaced", step=2)
        assert wm.is_empty()
        assert "config.py" in tracker.modified_files

    def test_extract_from_shell_error(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("shell", {"command": "npm test"}, "Error: test failed with exit code 1")
        assert len(wm.errors) == 1
        assert wm.errors[0].key == "command_error"

    def test_extract_from_shell_variable(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("shell", {"command": "echo $PORT"}, "PORT=8080")
        assert "PORT" in wm.variables
        assert wm.variables["PORT"].value == "8080"

    def test_extract_from_explore(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("explore", {"query": "authentication"}, "Found auth module with login/logout")
        assert any("explore:" in k for k in wm.variables)

    def test_extract_failure_does_not_crash(self):
        """提取失败不应影响主流程"""
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("file", {}, "")
        ext.extract("file", {"action": "read"}, "")
        ext.extract("unknown_tool", {}, "")
        assert wm.is_empty()

    def test_extract_from_response_is_placeholder(self):
        """extract_from_response 在 Task 3 之前为 placeholder"""
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        # 当前不崩溃即可，Task 3 会完善
        assert hasattr(ext, 'memory')


class TestLoopContextWorkingMemory:
    """验证 LoopContext 正确持有 WorkingMemory 和 MemoryExtractor"""

    def test_context_has_working_memory(self):
        from app.execution.context_manager import LoopContext
        context = LoopContext(task="测试")
        assert hasattr(context, "working_memory")
        assert isinstance(context.working_memory, WorkingMemory)
        assert context.working_memory.is_empty()

    def test_context_has_memory_extractor(self):
        from app.execution.context_manager import LoopContext
        context = LoopContext(task="测试")
        assert hasattr(context, "memory_extractor")
        assert isinstance(context.memory_extractor, MemoryExtractor)
        assert context.memory_extractor.memory is context.working_memory


class TestLoopMessageBuilderWorkingMemory:
    """验证 LoopMessageBuilder 正确注入 Working Memory"""

    def _make_builder(self):
        from app.execution.loop_message_builder import LoopMessageBuilder
        from app.execution.prompt_manager import PromptManager

        return LoopMessageBuilder(prompt_manager=PromptManager(), max_context_groups=10)

    def test_build_injects_working_memory(self):
        from app.execution.context_manager import LoopContext

        context = LoopContext(task="测试")
        context.working_memory.add_decision("d1", "Use FastAPI", "performance")

        builder = self._make_builder()
        messages = builder.build(context)

        # 应该有一条 system message 包含 Working Memory
        wm_messages = [m for m in messages if m.role == "system" and "Working Memory" in (m.content or "")]
        assert len(wm_messages) == 1
        assert "FastAPI" in wm_messages[0].content

    def test_build_skips_empty_working_memory(self):
        from app.execution.context_manager import LoopContext

        context = LoopContext(task="测试")
        builder = self._make_builder()
        messages = builder.build(context)

        # 空 Working Memory 不应注入
        wm_messages = [m for m in messages if m.role == "system" and "Working Memory" in (m.content or "")]
        assert len(wm_messages) == 0

    def test_build_final_summary_injects_working_memory(self):
        from app.execution.context_manager import LoopContext

        context = LoopContext(task="测试")
        context.working_memory.add_decision("用 FastAPI", source="model")

        builder = self._make_builder()
        messages = builder.build_final_summary(context)

        wm_messages = [m for m in messages if m.role == "system" and "Working Memory" in (m.content or "")]
        assert len(wm_messages) == 1
