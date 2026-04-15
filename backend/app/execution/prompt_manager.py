from typing import List, Dict, Any
from string import Template


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
        # System Prompt
        self.register_template(
            name="system",
            template="""You are an autonomous coding agent working in a local workspace.

You must:
- Solve tasks step by step using tools
- Prefer minimal edits (use apply_patch)
- Automatically fix errors
- Verify results via shell commands

Rules:
- Output MUST be valid JSON
- No explanation outside JSON
- Keep thought short

Available tools:
$tool_list""",
            variables=["tool_list"]
        )
        
        # Step Prompt
        self.register_template(
            name="step",
            template="""Task: $task

$history_context

$error_context

Workspace:
$workspace_context

What is your next action? (Output JSON only)""",
            variables=["task", "history_context", "error_context", "workspace_context"]
        )
        
        # Error Prompt
        self.register_template(
            name="error",
            template="""The previous action failed.

Tool: $tool
Error: $error

Relevant code:
$code_snippet

Fix the issue using available tools. Do not repeat the same action.""",
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
        tool_schemas = [tool.get_schema() for tool in tools]
        import json
        tool_list = json.dumps(tool_schemas, indent=2, ensure_ascii=False)
        
        return self.get_template("system").render(tool_list=tool_list)
    
    def get_step_prompt(self, context: Any) -> str:
        """获取步骤提示"""
        history_context = self._build_history_context(context)
        error_context = context.metadata.get("last_error", "")
        workspace_context = context.get_workspace_context()
        
        return self.get_template("step").render(
            task=context.task,
            history_context=history_context,
            error_context=error_context,
            workspace_context=workspace_context
        )
    
    def get_error_prompt(self, error: str, tool: str, code_snippet: str = "") -> str:
        """获取错误提示"""
        return self.get_template("error").render(
            tool=tool,
            error=error,
            code_snippet=code_snippet
        )
    
    def _build_history_context(self, context: Any) -> str:
        """构建历史上下文"""
        recent = context.get_recent_history(3)
        if not recent:
            return ""
        
        lines = ["Recent actions:"]
        for i, item in enumerate(recent, 1):
            action = item["action"]
            lines.append(f"{i}. {action.type}: {action.tool or 'finish'}")
            if item.get("result"):
                result_str = str(item["result"])
                lines.append(f"   Result: {result_str[:100]}")
        
        return "\n".join(lines)
