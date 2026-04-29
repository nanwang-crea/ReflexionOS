from string import Template

from app.llm.base import LLMToolDefinition


class PromptTemplate:
    """Prompt 模板"""
    
    def __init__(self, name: str, template: str, variables: list[str]):
        self.name = name
        self.template = Template(template)
        self.variables = variables
    
    def render(self, **kwargs) -> str:
        """渲染模板"""
        return self.template.safe_substitute(**kwargs)


class PromptManager:
    """Prompt 管理器"""
    
    def __init__(self):
        self.templates: dict[str, PromptTemplate] = {}
        self._load_default_templates()
    
    def _load_default_templates(self):
        """加载默认模板"""
        
        # System Prompt - 原生工具调用模式
        self.register_template(
            name="system",
            template="""You are an autonomous coding agent.
You help users with coding tasks by using tools.

## How to use tools:
You have access to the following tools.
When you need to use a tool, simply call it.
The system will handle the execution.

## Available tools:
$tool_list

## Rules:
- Use tools to accomplish tasks (read files, write files, run commands)
- Answer the user's actual question directly once you have enough information
- Keep any explanation of your process brief and natural unless the user explicitly asks for details
- If something fails, try to fix it and retry
- When done, provide a helpful final answer, not a rigid operation log
- Shell commands are executed via argv, NOT through a shell. NEVER use pipe `|`, redirect `>` `>>` `2>` `/dev/null`, chain `&&` `||` `;`, or command substitution `` ` `` `$()`. Use a single simple command per call.

## When to use the plan tool:
- If a task clearly requires 3 or more distinct steps (e.g. "refactor the auth module", "debug why the API returns 500"), FIRST call plan.create with a goal and step list, THEN execute step by step
- After finishing each plan step, call plan.step_done with a brief summary of what you found — this carries key information into the next step
- If you get stuck on a step, call plan.block with the reason
- If you discover the plan needs to change, call plan.adjust with updated remaining steps
- Do NOT call plan for simple tasks that can be answered directly (e.g. "what does this function do", "fix this typo")""",
            variables=["tool_list"]
        )

        self.register_template(
            name="final_response",
            template="""You have already finished the tool work.

Original user request:
$task

Write the final answer for the user now.

Requirements:
- Directly answer the user's real question first
- Keep the tone natural, clear, and helpful
- You may briefly mention how you verified or gathered the answer if it helps,
  but do not write a rigid "operation summary"
- Do not use headings like "操作总结", "完成的操作", or "获得的结果"
  unless the user explicitly asked for that format
- If the answer is based on repository structure or files,
  summarize the key conclusion instead of dumping unnecessary detail""",
            variables=["task"]
        )

        # Continuation Artifact compression (Task 6): single LLM-driven handoff note.
        self.register_template(
            name="continuation_compress",
            template="""You are generating a Continuation Artifact: a short handoff note for continuing the SAME session in a future turn.

This artifact is DERIVED from the transcript below. Do not invent facts. If unsure, state uncertainty.
Write in Chinese.

Output MUST be plain text with EXACTLY these 4 lines (one per line, keep the labels):
当前目标: <one sentence>
已确认事实: <1-5 bullet-style phrases separated by '; '>
未解决点: <1-5 bullet-style phrases separated by '; '>
下一步建议: <one concrete next action>

Task (current user input):
$task

Transcript (oldest to newest, may include tool traces):
$transcript
""",
            variables=["task", "transcript"],
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
    
    def register_template(self, name: str, template: str, variables: list[str]):
        """注册模板"""
        self.templates[name] = PromptTemplate(name, template, variables)
    
    def get_template(self, name: str) -> PromptTemplate:
        """获取模板"""
        if name not in self.templates:
            raise ValueError(f"Template not found: {name}")
        return self.templates[name]
    
    def get_system_prompt(self, tools: list[LLMToolDefinition]) -> str:
        """获取系统提示"""
        tool_list = self._format_tools(tools)
        return self.get_template("system").render(tool_list=tool_list)
    
    def _format_tools(self, tools: list[LLMToolDefinition]) -> str:
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

    def get_final_response_prompt(self, task: str) -> str:
        """获取最终回答提示"""
        return self.get_template("final_response").render(task=task)

    def get_continuation_compression_prompt(self, *, task: str, transcript: str) -> str:
        """Prompt for a single LLM-generated continuation/handoff artifact."""
        return self.get_template("continuation_compress").render(
            task=task or "",
            transcript=transcript or "",
        )
