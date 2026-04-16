from typing import List, Dict, Any
from string import Template
import json

from app.llm.base import LLMToolDefinition


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
        
        # System Prompt - 原生工具调用模式
        self.register_template(
            name="system",
            template="""You are an autonomous coding agent. You help users with coding tasks by using tools.

## How to use tools:
You have access to the following tools. When you need to use a tool, simply call it - the system will handle the execution.

## Available tools:
$tool_list

## Rules:
- Use tools to accomplish tasks (read files, write files, run commands)
- After using tools, provide a brief summary of what you did
- If a task is complex, break it into steps
- If something fails, try to fix it and retry
- When done, provide a clear summary of the completed work""",
            variables=["tool_list"]
        )
        
        # Error Prompt
        self.register_template(
            name="error",
            template="""The previous tool call failed.

Tool: $tool
Error: $error

Please try a different approach or fix the issue.""",
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
    
    def get_system_prompt(self, tools: List[LLMToolDefinition]) -> str:
        """获取系统提示"""
        tool_list = self._format_tools(tools)
        return self.get_template("system").render(tool_list=tool_list)
    
    def _format_tools(self, tools: List[LLMToolDefinition]) -> str:
        """格式化工具列表"""
        lines = []
        for tool in tools:
            lines.append(f"\n### {tool.name}")
            lines.append(f"{tool.description}")
            if tool.parameters.get("properties"):
                lines.append("Parameters:")
                for prop, schema in tool.parameters["properties"].items():
                    prop_desc = schema.get("description", "")
                    lines.append(f"  - {prop}: {prop_desc}")
        return "\n".join(lines)
    
    def get_error_prompt(self, error: str, tool: str, code_snippet: str = "") -> str:
        """获取错误提示"""
        return self.get_template("error").render(
            tool=tool,
            error=error,
            code_snippet=code_snippet
        )
