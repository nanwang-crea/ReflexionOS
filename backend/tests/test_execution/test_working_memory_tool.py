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
        assert "content" in result.error

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
        assert "key" in result.error

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
        assert "key" in result.error


# ---------------------------------------------------------------------------
# update 操作测试 — 与 add 相同（upsert 语义）
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolUpdate:

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

    @pytest.mark.asyncio
    async def test_update_decision_upserts(self):
        """相同 key 的决策应被更新，而非重复追加"""
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "decisions",
            "content": "使用 FastAPI",
        })
        result = await tool.execute({
            "action": "add", "slot": "decisions",
            "content": "使用 FastAPI", "rationale": "异步支持好",
        })
        assert result.success is True
        assert len(wm.decisions) == 1  # upsert，不是 append
        assert wm.decisions[0].value == "异步支持好"

    @pytest.mark.asyncio
    async def test_update_error_upserts(self):
        """相同 key 的错误应被更新，而非重复追加"""
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "errors",
            "key": "ImportError", "content": "缺少依赖",
        })
        result = await tool.execute({
            "action": "add", "slot": "errors",
            "key": "ImportError", "content": "已安装依赖，版本不兼容",
        })
        assert result.success is True
        assert len(wm.errors) == 1  # upsert，不是 append
        assert wm.errors[0].value == "已安装依赖，版本不兼容"


# ---------------------------------------------------------------------------
# remove 操作测试
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolRemove:

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
        # 精确 key 匹配：必须传完整的决策内容
        result = await tool.execute({
            "action": "remove", "slot": "decisions",
            "content": "使用 FastAPI",
        })
        assert result.success is True
        assert "已移除" in result.output
        assert len(wm.decisions) == 0

    @pytest.mark.asyncio
    async def test_remove_decision_partial_match_fails(self):
        """精确匹配下，子串不应命中"""
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
        assert result.success is False
        assert "未找到" in result.error

    @pytest.mark.asyncio
    async def test_remove_error(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "errors",
            "key": "ImportError", "content": "缺少依赖",
        })
        # errors 的匹配键是 key（错误类型）
        result = await tool.execute({
            "action": "remove", "slot": "errors",
            "key": "ImportError",
        })
        assert result.success is True
        assert "已移除" in result.output
        assert len(wm.errors) == 0


# ---------------------------------------------------------------------------
# clear 操作测试
# ---------------------------------------------------------------------------

class TestWorkingMemoryToolClear:

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
        result = await tool.execute({"action": "invalid", "slot": "decisions"})
        assert result.success is False
        assert "action" in result.error

    @pytest.mark.asyncio
    async def test_invalid_slot(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({"action": "add", "slot": "nonexistent"})
        assert result.success is False
        assert "slot" in result.error

    @pytest.mark.asyncio
    async def test_empty_action(self):
        wm = WorkingMemory()
        tool = _make_tool(wm)
        result = await tool.execute({"slot": "decisions"})
        assert result.success is False
        assert "action" in result.error

    @pytest.mark.asyncio
    async def test_no_working_memory(self):
        tool = WorkingMemoryTool()
        # 不调用 set_working_memory，_working_memory 为 None
        result = await tool.execute({
            "action": "add", "slot": "variables", "key": "port", "content": "8080",
        })
        assert result.success is False
        assert "不可用" in result.error


# ---------------------------------------------------------------------------
# source 参数传递测试
# ---------------------------------------------------------------------------


class TestWorkingMemoryToolSource:

    @pytest.mark.asyncio
    async def test_default_source_is_model(self):
        """add 操作不传 source 时，默认为 'model'"""
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "variables",
            "key": "port", "content": "8080",
        })
        assert wm.variables["port"].source == "model"

    @pytest.mark.asyncio
    async def test_explicit_source_auto(self):
        """add 操作传 source='auto' 时，MemoryEntry.source 应为 'auto'"""
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "variables",
            "key": "env", "content": "prod", "source": "auto",
        })
        assert wm.variables["env"].source == "auto"

    @pytest.mark.asyncio
    async def test_source_on_variable(self):
        """变量操作也应正确传递 source"""
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "variables",
            "key": "env", "content": "prod", "source": "auto",
        })
        assert wm.variables["env"].source == "auto"

    @pytest.mark.asyncio
    async def test_source_on_decision(self):
        """决策操作也应正确传递 source"""
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "decisions",
            "content": "用 SQLite", "source": "auto",
        })
        assert wm.decisions[0].source == "auto"

    @pytest.mark.asyncio
    async def test_source_on_error(self):
        """错误记录操作也应正确传递 source"""
        wm = WorkingMemory()
        tool = _make_tool(wm)
        await tool.execute({
            "action": "add", "slot": "errors",
            "key": "Timeout", "content": "超时", "source": "auto",
        })
        assert wm.errors[0].source == "auto"


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
