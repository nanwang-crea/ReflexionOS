"""
WorkingMemoryTool 单元测试

测试 WorkingMemoryTool 类的各种操作（add/update/remove/clear），
通过 set_working_memory() 注入 WorkingMemory 实例，execute() 接收 args 字典。
"""

import pytest

from app.memory.working_memory import WorkingMemory
from app.tools.working_memory_tool import WorkingMemoryTool


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_tool(wm: WorkingMemory | None = None) -> WorkingMemoryTool:
    """创建 WorkingMemoryTool 并注入 WorkingMemory 实例"""
    tool = WorkingMemoryTool()
    tool.set_working_memory(wm)
    return tool


# ---------------------------------------------------------------------------
# add 操作测试
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolAdd:

    @pytest.mark.asyncio
    async def test_add_file_index(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "add", "slot": "file_index",
            "key": "src/main.py", "content": "主入口文件",
        })
        assert result.success is True
        assert "已添加文件摘要" in result.output
        assert "src/main.py" in wm.file_index
        assert wm.file_index["src/main.py"].value == "主入口文件"

    @pytest.mark.asyncio
    async def test_add_file_index_without_key_returns_error(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "add", "slot": "file_index", "content": "摘要",
        })
        assert result.success is False
        assert "错误" in result.output

    @pytest.mark.asyncio
    async def test_add_decision(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "add", "slot": "decisions",
            "content": "使用 FastAPI", "rationale": "项目需要异步支持",
        })
        assert result.success is True
        assert "已记录决策" in result.output
        assert len(wm.decisions) == 1
        assert wm.decisions[0].key == "使用 FastAPI"
        assert wm.decisions[0].value == "项目需要异步支持"

    @pytest.mark.asyncio
    async def test_add_decision_without_content_returns_error(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "add", "slot": "decisions",
        })
        assert result.success is False
        assert "错误" in result.output

    @pytest.mark.asyncio
    async def test_add_variable(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "add", "slot": "variables",
            "key": "port", "content": "8080",
        })
        assert result.success is True
        assert "已设置变量" in result.output
        assert "port" in wm.variables
        assert wm.variables["port"].value == "8080"

    @pytest.mark.asyncio
    async def test_add_variable_without_key_returns_error(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "add", "slot": "variables", "content": "8080",
        })
        assert result.success is False
        assert "错误" in result.output

    @pytest.mark.asyncio
    async def test_add_error(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "add", "slot": "errors",
            "key": "ImportError", "content": "缺少依赖包",
        })
        assert result.success is True
        assert "已记录错误" in result.output
        assert len(wm.errors) == 1
        assert wm.errors[0].key == "ImportError"

    @pytest.mark.asyncio
    async def test_add_error_without_key_returns_error(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "add", "slot": "errors", "content": "详情",
        })
        assert result.success is False
        assert "错误" in result.output


# ---------------------------------------------------------------------------
# update 操作测试 — 与 add 相同（upsert 语义）
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolUpdate:

    @pytest.mark.asyncio
    async def test_update_file_index_upsert(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        # 先 add
        await tool.execute({
            "action": "add", "slot": "file_index",
            "key": "src/main.py", "content": "旧摘要",
        })
        # 再 update（覆盖）
        result = await tool.execute({
            "action": "update", "slot": "file_index",
            "key": "src/main.py", "content": "新摘要",
        })
        assert result.success is True
        assert "已添加文件摘要" in result.output
        assert wm.file_index["src/main.py"].value == "新摘要"

    @pytest.mark.asyncio
    async def test_update_variable(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "variables",
            "key": "port", "content": "8080",
        })
        result = await tool.execute({
            "action": "update", "slot": "variables",
            "key": "port", "content": "9090",
        })
        assert result.success is True
        assert "已设置变量" in result.output
        assert wm.variables["port"].value == "9090"


# ---------------------------------------------------------------------------
# remove 操作测试
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolRemove:

    @pytest.mark.asyncio
    async def test_remove_file_index(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "file_index",
            "key": "src/main.py", "content": "摘要",
        })
        result = await tool.execute({
            "action": "remove", "slot": "file_index",
            "key": "src/main.py",
        })
        assert result.success is True
        assert "已移除" in result.output
        assert "src/main.py" not in wm.file_index

    @pytest.mark.asyncio
    async def test_remove_file_index_not_found(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({
            "action": "remove", "slot": "file_index",
            "key": "nonexistent.py",
        })
        assert result.success is False
        assert "错误" in result.output

    @pytest.mark.asyncio
    async def test_remove_variable(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "variables",
            "key": "port", "content": "8080",
        })
        result = await tool.execute({
            "action": "remove", "slot": "variables",
            "key": "port",
        })
        assert result.success is True
        assert "已移除" in result.output
        assert "port" not in wm.variables

    @pytest.mark.asyncio
    async def test_remove_decision_by_content(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "decisions",
            "content": "使用 FastAPI",
        })
        result = await tool.execute({
            "action": "remove", "slot": "decisions",
            "content": "FastAPI",
        })
        assert result.success is True
        assert "已移除" in result.output
        assert len(wm.decisions) == 0

    @pytest.mark.asyncio
    async def test_remove_error(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "errors",
            "key": "ImportError", "content": "缺少依赖",
        })
        result = await tool.execute({
            "action": "remove", "slot": "errors",
            "content": "ImportError",
        })
        assert result.success is True
        assert "已移除" in result.output
        assert len(wm.errors) == 0


# ---------------------------------------------------------------------------
# clear 操作测试
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolClear:

    @pytest.mark.asyncio
    async def test_clear_file_index(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "file_index",
            "key": "a.py", "content": "文件A",
        })
        result = await tool.execute({"action": "clear", "slot": "file_index"})
        assert result.success is True
        assert "已清空" in result.output
        assert len(wm.file_index) == 0

    @pytest.mark.asyncio
    async def test_clear_decisions(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "decisions",
            "content": "决策1",
        })
        result = await tool.execute({"action": "clear", "slot": "decisions"})
        assert result.success is True
        assert "已清空" in result.output
        assert len(wm.decisions) == 0

    @pytest.mark.asyncio
    async def test_clear_variables(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "variables",
            "key": "x", "content": "1",
        })
        result = await tool.execute({"action": "clear", "slot": "variables"})
        assert result.success is True
        assert "已清空" in result.output
        assert len(wm.variables) == 0

    @pytest.mark.asyncio
    async def test_clear_errors(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "errors",
            "key": "E1", "content": "错误1",
        })
        result = await tool.execute({"action": "clear", "slot": "errors"})
        assert result.success is True
        assert "已清空" in result.output
        assert len(wm.errors) == 0


# ---------------------------------------------------------------------------
# 参数验证测试
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolValidation:

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({"action": "invalid", "slot": "file_index"})
        assert result.success is False
        assert "错误" in result.output
        assert "action" in result.output

    @pytest.mark.asyncio
    async def test_invalid_slot(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({"action": "add", "slot": "nonexistent"})
        assert result.success is False
        assert "错误" in result.output
        assert "slot" in result.output

    @pytest.mark.asyncio
    async def test_empty_action(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({"slot": "file_index"})
        assert result.success is False
        assert "错误" in result.output

    @pytest.mark.asyncio
    async def test_no_working_memory(self):
        tool = WorkingMemoryTool()
        # 不调用 set_working_memory，_working_memory 为 None
        result = await tool.execute({
            "action": "add", "slot": "variables", "key": "port", "content": "8080",
        })
        assert result.success is False
        assert "不可用" in result.output


# ---------------------------------------------------------------------------
# Tool 属性和 schema 测试
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolProperties:

    def test_name(self):
        tool = WorkingMemoryTool()
        assert tool.name == "working_memory_update"

    def test_description_not_empty(self):
        tool = WorkingMemoryTool()
        assert len(tool.description) > 0

    def test_parameters_schema(self):
        tool = WorkingMemoryTool()
        params = tool.parameters
        assert "action" in params["properties"]
        assert "slot" in params["properties"]
        assert "key" in params["properties"]
        assert "content" in params["properties"]
        assert "rationale" in params["properties"]
        assert "action" in params["required"]
        assert "slot" in params["required"]

    def test_get_schema(self):
        tool = WorkingMemoryTool()
        schema = tool.get_schema()
        assert schema["name"] == "working_memory_update"
        assert "parameters" in schema

    def test_set_get_working_memory(self):
        tool = WorkingMemoryTool()
        assert tool.get_working_memory() is None
        wm = WorkingMemory()
        tool.set_working_memory(wm)
        assert tool.get_working_memory() is wm
