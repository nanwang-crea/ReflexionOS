"""WorkingMemory 和 MemoryExtractor 单元测试"""

import pytest
from app.memory.working_memory import WorkingMemory, MemoryEntry, MemoryEntryType
from app.memory.memory_extractor import MemoryExtractor


class TestWorkingMemory:
    """WorkingMemory 数据模型测试"""

    def test_empty_memory_is_empty(self):
        wm = WorkingMemory()
        assert wm.is_empty()

    def test_upsert_file(self):
        wm = WorkingMemory()
        wm.upsert_file("src/main.py", "50 lines: main(), run()")
        assert not wm.is_empty()
        assert "src/main.py" in wm.file_index
        assert wm.file_index["src/main.py"].value == "50 lines: main(), run()"
        assert wm.file_index["src/main.py"].entry_type == MemoryEntryType.FILE_SUMMARY

    def test_upsert_file_update(self):
        """更新已有文件摘要"""
        wm = WorkingMemory()
        wm.upsert_file("src/main.py", "original summary")
        wm.upsert_file("src/main.py", "updated summary")
        assert wm.file_index["src/main.py"].value == "updated summary"
        assert len(wm.file_index) == 1  # 不应重复

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

    def test_to_prompt_section_with_file(self):
        wm = WorkingMemory()
        wm.upsert_file("src/main.py", "50 lines: main()")
        section = wm.to_prompt_section()
        assert "[Working Memory" in section
        assert "📂 Files read:" in section
        assert "src/main.py" in section
        assert "50 lines: main()" in section

    def test_to_prompt_section_with_all_types(self):
        wm = WorkingMemory()
        wm.upsert_file("src/app.py", "30 lines: App class")
        wm.add_decision("用 FastAPI", "性能好", source="model")
        wm.set_variable("PORT", "8080")
        wm.add_error("import_error", "No module named 'foo'")
        section = wm.to_prompt_section()
        assert "📂 Files read:" in section
        assert "🎯 Key decisions:" in section
        assert "⚙️ Current state:" in section
        assert "⚠️ Errors encountered:" in section

    def test_to_prompt_section_token_budget(self):
        """Token 预算淘汰机制"""
        wm = WorkingMemory(max_tokens=50)  # 极小预算
        # 填充大量数据
        for i in range(20):
            wm.upsert_file(f"file_{i}.py", f"summary of file {i} " * 20)
        section = wm.to_prompt_section()
        # 应该被截断或淘汰
        assert len(section) < 2000  # 粗略验证

    def test_eviction_removes_errors_first(self):
        """淘汰顺序：errors 最先被淘汰"""
        wm = WorkingMemory(max_tokens=50)
        wm.add_error("err1", "x" * 100)
        wm.add_error("err2", "y" * 100)
        wm.add_error("err3", "z" * 100)
        wm.upsert_file("a.py", "important file")
        wm.to_prompt_section()
        # errors 应该被缩减到 2 个
        assert len(wm.errors) <= 2

    def test_eviction_removes_variables_second(self):
        """淘汰顺序：variables 第二被淘汰"""
        wm = WorkingMemory(max_tokens=50)
        for i in range(20):
            wm.set_variable(f"VAR_{i}", f"value_{i}" * 10)
        wm.upsert_file("a.py", "important")
        wm.to_prompt_section()
        assert len(wm.variables) <= 10


class TestMemoryExtractor:
    """MemoryExtractor 自动提取测试"""

    def test_extract_from_file_read(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("file", {"action": "read", "path": "src/main.py"}, "class Main:\n    pass")
        assert "src/main.py" in wm.file_index
        assert "class Main" in wm.file_index["src/main.py"].value

    def test_extract_from_file_read_skips_error(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("file", {"action": "read", "path": "missing.py"}, "Error: file not found")
        assert wm.is_empty()

    def test_extract_from_file_read_skips_nonexistent(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("file", {"action": "read", "path": "x.py"}, "文件不存在")
        assert wm.is_empty()

    def test_extract_from_file_search_updates_existing(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        # 先读文件
        ext.extract("file", {"action": "read", "path": "src/app.py"}, "class App")
        # 再搜索
        ext.extract("file", {"action": "search", "path": "src/app.py", "query": "router"}, "found 3 matches")
        assert "search: router" in wm.file_index["src/app.py"].value

    def test_extract_from_file_list(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("file", {"action": "list", "path": "src/"}, "main.py\nutils.py\n__init__.py")
        assert "src/" in wm.file_index
        assert "3 items" in wm.file_index["src/"].value

    def test_extract_from_edit_marks_modified(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        # 先读文件
        ext.extract("file", {"action": "read", "path": "config.py"}, "PORT = 8080")
        # 再编辑
        ext.extract("edit", {"action": "str_replace", "path": "config.py"}, "Successfully replaced")
        assert "[MODIFIED]" in wm.file_index["config.py"].value

    def test_extract_from_edit_new_file(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("edit", {"action": "write", "path": "new_file.py"}, "File created successfully")
        assert "new_file.py" in wm.file_index
        assert "[MODIFIED]" in wm.file_index["new_file.py"].value

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

    def test_extract_from_grep(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("grep", {"pattern": "TODO"}, "src/main.py:10:TODO fix this\nsrc/utils.py:5:TODO refactor")
        assert "src/main.py" in wm.file_index
        assert "src/utils.py" in wm.file_index
        assert "found in search" in wm.file_index["src/main.py"].value

    def test_extract_from_explore(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        ext.extract("explore", {"query": "authentication"}, "Found auth module with login/logout")
        assert any("explore:" in k for k in wm.variables)

    def test_extract_failure_does_not_crash(self):
        """提取失败不应影响主流程"""
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        # 传入各种异常参数
        ext.extract("file", {}, "")  # 缺少 action
        ext.extract("file", {"action": "read"}, "")  # 缺少 path
        ext.extract("unknown_tool", {}, "")  # 未知工具
        # 不应崩溃，memory 应保持空
        assert wm.is_empty()

    def test_extract_summarize_python(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        content = "import os\n\nclass Foo:\n    pass\n\ndef bar():\n    return 42\n"
        ext.extract("file", {"action": "read", "path": "test.py"}, content)
        summary = wm.file_index["test.py"].value
        assert "class Foo" in summary
        assert "def bar" in summary

    def test_extract_summarize_javascript(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        content = "export function hello() {\n  return 'world';\n}\n"
        ext.extract("file", {"action": "read", "path": "index.js"}, content)
        summary = wm.file_index["index.js"].value
        assert "export function hello" in summary

    def test_extract_summarize_with_todo(self):
        wm = WorkingMemory()
        ext = MemoryExtractor(wm)
        content = "def main():\n    # TODO: refactor this\n    pass\n"
        ext.extract("file", {"action": "read", "path": "main.py"}, content)
        summary = wm.file_index["main.py"].value
        assert "TODO" in summary


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
        context.working_memory.upsert_file("src/main.py", "50 lines: main()")

        builder = self._make_builder()
        messages = builder.build(context)

        # 应该有一条 system message 包含 Working Memory
        wm_messages = [m for m in messages if m.role == "system" and "Working Memory" in (m.content or "")]
        assert len(wm_messages) == 1
        assert "src/main.py" in wm_messages[0].content

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
        context.working_memory.upsert_file("config.yaml", "10 lines")
        context.working_memory.add_decision("用 FastAPI", source="model")

        builder = self._make_builder()
        messages = builder.build_final_summary(context)

        wm_messages = [m for m in messages if m.role == "system" and "Working Memory" in (m.content or "")]
        assert len(wm_messages) == 1
