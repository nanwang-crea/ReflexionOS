"""
app.orchestration — 插件/技能编排模块。

负责 MCP 服务器管理、外部包解析、插件加载、技能注册与排序等编排逻辑，
是 Agent 运行时调用外部工具/技能能力的核心装配层。

导出：
    MCPManager / MCPServerConfig / MCPTool / mcp_manager: MCP 服务器生命周期与工具管理
    PackageResolver / PackageSpecifier / ResolvedPackage: 第三方包版本解析
    PluginLoader / PluginRegistration: 插件发现与加载
    SkillRegistry / SkillMetadata / SkillSource / skill_registry: 技能元数据注册表
"""

from app.orchestration.mcp_manager import MCPManager, MCPServerConfig, MCPTool, mcp_manager
from app.orchestration.package_resolver import PackageResolver, PackageSpecifier, ResolvedPackage
from app.orchestration.plugin_loader import PluginLoader, PluginRegistration
from app.orchestration.skill_registry import (
    SkillMetadata,
    SkillRegistry,
    SkillSource,
    skill_registry,
)

__all__ = [
    "SkillRegistry",
    "SkillMetadata",
    "SkillSource",
    "skill_registry",
    "MCPManager",
    "MCPServerConfig",
    "MCPTool",
    "mcp_manager",
    "PackageSpecifier",
    "PackageResolver",
    "ResolvedPackage",
    "PluginLoader",
    "PluginRegistration",
]
