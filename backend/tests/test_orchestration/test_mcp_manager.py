import pytest

from app.orchestration.mcp_manager import MCPManager, MCPServerConfig, MCPTool


class TestMCPManager:
    
    def test_manager_initialization(self):
        manager = MCPManager()
        
        assert len(manager.servers) == 0
        assert len(manager.tools) == 0
    
    @pytest.mark.asyncio
    async def test_register_server(self):
        manager = MCPManager()
        config = MCPServerConfig(
            server_id="test_server",
            command="node",
            args=["server.js"]
        )
        
        result = await manager.register_server(config)
        
        assert result is True
        assert "test_server" in manager.servers
    
    @pytest.mark.asyncio
    async def test_unregister_server(self):
        manager = MCPManager()
        config = MCPServerConfig(server_id="to_remove", command="test")
        await manager.register_server(config)
        
        result = await manager.unregister_server("to_remove")
        
        assert result is True
        assert "to_remove" not in manager.servers
    
    @pytest.mark.asyncio
    async def test_unregister_nonexistent_server(self):
        manager = MCPManager()
        
        result = await manager.unregister_server("nonexistent")
        
        assert result is False
    
    def test_list_servers(self):
        manager = MCPManager()
        
        servers = manager.list_servers()
        
        assert isinstance(servers, list)
    
    def test_get_server(self):
        manager = MCPManager()
        
        server = manager.get_server("nonexistent")
        
        assert server is None
    
    def test_list_tools(self):
        manager = MCPManager()
        
        tools = manager.list_tools()
        
        assert isinstance(tools, list)
    
    @pytest.mark.asyncio
    async def test_call_tool_not_implemented(self):
        manager = MCPManager()
        
        with pytest.raises(NotImplementedError):
            await manager.call_tool("test", {})
    
    @pytest.mark.asyncio
    async def test_start_server_not_implemented(self):
        manager = MCPManager()
        
        result = await manager.start_server("test")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_stop_server_not_implemented(self):
        manager = MCPManager()
        
        result = await manager.stop_server("test")
        
        assert result is False


class TestMCPServerConfig:
    
    def test_config_creation(self):
        config = MCPServerConfig(
            server_id="test",
            command="node",
            args=["server.js"],
            env={"NODE_ENV": "production"}
        )
        
        assert config.server_id == "test"
        assert config.command == "node"
        assert len(config.args) == 1
        assert config.enabled is True
    
    def test_config_default_values(self):
        config = MCPServerConfig(
            server_id="minimal",
            command="test"
        )
        
        assert config.args == []
        assert config.env == {}
        assert config.enabled is True


class TestMCPTool:
    
    def test_tool_creation(self):
        tool = MCPTool(
            name="test_tool",
            description="测试工具",
            input_schema={"type": "object"}
        )
        
        assert tool.name == "test_tool"
        assert tool.description == "测试工具"
    
    def test_tool_default_values(self):
        tool = MCPTool(name="minimal", description="最小工具")
        
        assert tool.input_schema == {}
