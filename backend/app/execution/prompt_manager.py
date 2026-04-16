from typing import List, Dict, Any
from string import Template
import json


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
        
        # System Prompt - 明确输出格式
        self.register_template(
            name="system",
            template="""You are an autonomous coding agent. You help users with coding tasks by using tools.

## Output Format
You MUST respond in JSON format:
```json
{
  "content": "Your message to the user",
  "tool_calls": [{"name": "tool_name", "args": {...}}]
}
```

**IMPORTANT**: 
- `content` is REQUIRED - always explain what you're doing or summarize results
- `tool_calls` should be [] when done with all operations

## Workflow:
1. **During task**: Use tools to accomplish the task
   - {"content": "Let me check the files...", "tool_calls": [{"name": "file", "args": {"action": "list", "path": "."}}]}
   
2. **After tools complete**: Provide a summary
   - {"content": "I found X files. Here's what I discovered...", "tool_calls": []}

## Available tools:
$tool_list

## Rules:
- ALWAYS include `content` field explaining your actions
- When finished with all tools, set `tool_calls` to [] and summarize your findings
- If user asks a question (not a task), just respond with content and empty tool_calls
- Keep responses concise but informative""",
            variables=["tool_list"]
        )
        
        # Error Prompt
        self.register_template(
            name="error",
            template="""The previous tool call failed.

Tool: $tool
Error: $error

Please fix the issue and try again, or explain why it cannot be fixed.""",
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
    
    def get_system_prompt(self, tools: List[Any]) -> str:
        """获取系统提示"""
        tool_schemas = []
        for tool in tools:
            schema = tool.get_schema()
            tool_schemas.append(schema)
        
        tool_list = json.dumps(tool_schemas, indent=2, ensure_ascii=False)
        return self.get_template("system").render(tool_list=tool_list)
    
    def get_error_prompt(self, error: str, tool: str, code_snippet: str = "") -> str:
        """获取错误提示"""
        return self.get_template("error").render(
            tool=tool,
            error=error,
            code_snippet=code_snippet
        )
