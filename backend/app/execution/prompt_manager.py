from datetime import datetime
from string import Template


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

        self.register_template(
            name="system",
            template="""You are an autonomous coding agent.
You help users with coding tasks by using tools.

## Environment:
- Working directory: $working_directory
- Platform: $platform
- Today's date: $date
- Is directory a git repo: $is_git_repo

## How to use tools:
You have access to the following tools.
When you need to use a tool, simply call it.
The system will handle the execution.

## Core discipline:
- Observe → Plan → Act. Never edit a file you have not read first.
- Keep changes minimal and scoped to the user's request.
  Do not refactor or modify unrelated code unless the user asks for it.
- Before editing a file, read the relevant section first unless the change is trivial.
- Prefer the edit tool with action=str_replace over patch or write.
  str_replace supports fuzzy matching (indentation, whitespace differences are tolerated).
- Use write ONLY when creating a brand-new file.
  NEVER use write to overwrite an existing file.
- Use patch only for complex multi-hunk changes where diff format is more appropriate.

## Tool and shell rules:
- Read only the minimum relevant file sections needed.
- Prefer targeted search (grep, glob) before large file reads.
- Avoid reading entire repositories or very large files when a specific section suffices.
- Shell commands are executed via argv, NOT through a shell.
- NEVER use pipe `|`, redirect `>` `>>` `2>` `/dev/null`,
  chain `&&` `||` `;`, or command substitution `` ` `` `$()`.
- Use a single simple command per call.
- NEVER run destructive commands (rm -rf, git reset --hard, sudo, git clean -fd)
  unless explicitly requested by the user.
- Do not use network-related commands unless required by the task.

## Stopping rules:
- Stop when the user's request is fully satisfied.
- Do not continue exploring once the required change is completed.
- Avoid repeated tool calls that do not produce new information.
- After 2 failed attempts on the same action, explain the issue and ask the user instead of retrying indefinitely.
- Never restart investigation from scratch unless a concrete prior finding was disproven.
- At most one broad exploration pass and one targeted follow-up pass per task.
- If the last tool batch produced no new facts, stop exploring and answer or ask for clarification.
- Before any re-check, state which exact prior claim is being verified.

## Error handling:
- If a tool call fails, first diagnose WHY it failed before retrying.
- Do not make speculative large changes without evidence.
- Do not blindly retry with the same parameters.

## Communication:
- Answer the user's actual question directly once you have enough information.
- Keep any explanation of your process brief and natural unless the user explicitly asks for details.
- When done, provide a helpful final answer, not a rigid operation log.

## Execution plan:
- Initial plan creation is handled before normal execution starts.
- If an execution plan is present, focus on the current step.
- Update the plan status in real time; do not batch completions.
- When a step is fully done, immediately call plan.step_done before moving to the next step.
- When a step is blocked, call plan.block with the reason.
- Do not create a second plan during normal execution.""",
            variables=["working_directory", "platform", "date", "is_git_repo"],
        )

        self.register_template(
            name="initial_plan",
            template="""You decide whether this coding-agent task needs an explicit execution plan.

Call plan.create only if the task clearly needs 3 or more distinct execution steps,
such as multi-file implementation, debugging investigation, or a risky refactor.
If the task can be answered or completed directly, respond exactly: NO_PLAN

When creating a plan:
- Use concise, high-level steps
- Do not explain the plan in normal text
- Do not include code or implementation details in the step text""",
            variables=[],
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
- Do not use headings like "Operation Summary", "Completed Actions", or "Results Obtained"
  unless the user explicitly asked for that format
- If the answer is based on repository structure or files,
  summarize the key conclusion instead of dumping unnecessary detail""",
            variables=["task"],
        )

        # Continuation Artifact compression (Task 6): single LLM-driven handoff note.
        self.register_template(
            name="continuation_compress_system",
            template="""You are generating a Continuation Artifact: a short handoff note
for continuing the SAME session in a future turn.

This artifact is DERIVED from the transcript below. Do not invent facts.
If unsure, state uncertainty.

Output MUST be plain text with EXACTLY these 4 lines (one per line, keep the labels):
Current goal: <one sentence>
Confirmed facts: <1-5 bullet-style phrases separated by '; '>
Unresolved issues: <1-5 bullet-style phrases separated by '; '>
Suggested next step: <one concrete next action>""",
            variables=[],
        )

        self.register_template(
            name="continuation_compress_input",
            template="""Use this input to generate the Continuation Artifact.

Task (current user input):
$task

Transcript (oldest to newest, may include tool traces):
$transcript
""",
            variables=["task", "transcript"],
        )

        self.register_template(
            name="midrun_compress_system",
            template="""You are generating a mid-run context compaction summary.
The agent is in the middle of executing a task and the context window is under pressure.
You must compress older conversation history into a concise summary.

This summary is DERIVED from the transcript below. Do not invent facts.
If unsure, state uncertainty.

Output MUST be plain text with EXACTLY these 5 sections:
User's original intent: <the user's original intent, preserving key phrasing>
Operations performed: <key operations performed, one per line, mark recallable items>
  - <operation description> [session_recall can retrieve full content]
Confirmed findings: <important findings confirmed so far>
Current progress: <what step are we at, what remains>
Unresolved issues: <open issues that still need attention>

Rules:
- For each file read or shell execution, include [session_recall can retrieve full content] marker
- Preserve the user's original intent verbatim as much as possible
- Keep operation descriptions short but specific (include file names, function names)
- If an existing summary is provided, integrate it with new information""",
            variables=[],
        )

        self.register_template(
            name="midrun_compress_input",
            template="""Compress the following conversation history into a mid-run summary.

Task (current user input):
$task

$existing_summary_block

New conversation history (oldest to newest):
$transcript
""",
            variables=["task", "transcript", "existing_summary_block"],
        )

        # Error Prompt
        self.register_template(
            name="error",
            template="""The previous tool call failed.

Tool: $tool
Error: $error

Please try a different approach or fix the issue.""",
            variables=["tool", "error", "code_snippet"],
        )

    def register_template(self, name: str, template: str, variables: list[str]):
        """注册模板"""
        self.templates[name] = PromptTemplate(name, template, variables)

    def get_template(self, name: str) -> PromptTemplate:
        """获取模板"""
        if name not in self.templates:
            raise ValueError(f"Template not found: {name}")
        return self.templates[name]

    def get_system_prompt(
        self,
        *,
        working_directory: str = "",
        platform: str = "",
        is_git_repo: bool = False,
    ) -> str:
        return self.get_template("system").render(
            working_directory=working_directory,
            platform=platform,
            date=datetime.now().strftime("%Y-%m-%d"),
            is_git_repo=str(is_git_repo),
        )

    def get_error_prompt(self, error: str, tool: str, code_snippet: str = "") -> str:
        """获取错误提示"""
        return self.get_template("error").render(tool=tool, error=error, code_snippet=code_snippet)

    def get_final_response_prompt(self, task: str) -> str:
        """获取最终回答提示"""
        return self.get_template("final_response").render(task=task)

    def get_initial_plan_prompt(self) -> str:
        """Prompt for the non-streamed initial planning preflight."""
        return self.get_template("initial_plan").render()

    def get_midrun_compression_system_prompt(self) -> str:
        return self.get_template("midrun_compress_system").render()

    def get_midrun_compression_prompt(
        self,
        *,
        task: str,
        transcript: str,
        existing_summary: str | None = None,
    ) -> str:
        if existing_summary:
            existing_summary_block = f"[Existing summary]\n{existing_summary}\n\n[New conversation]"
        else:
            existing_summary_block = ""
        return self.get_template("midrun_compress_input").render(
            task=task or "",
            transcript=transcript or "",
            existing_summary_block=existing_summary_block,
        )

    def get_continuation_compression_prompt(self, *, task: str, transcript: str) -> str:
        """User input for a single LLM-generated continuation/handoff artifact."""
        return self.get_template("continuation_compress_input").render(
            task=task or "",
            transcript=transcript or "",
        )

    def get_continuation_compression_system_prompt(self) -> str:
        """System instructions for a single LLM-generated continuation/handoff artifact."""
        return self.get_template("continuation_compress_system").render()
