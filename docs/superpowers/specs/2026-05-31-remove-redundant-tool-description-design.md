# Remove Redundant Tool Description from System Prompt

**Date:** 2026-05-31
**Status:** Approved

## Problem

Every LLM API call sends tool descriptions (name, description, parameter descriptions) twice:

1. As **markdown** in the system prompt, via `prompt_manager._format_tools()` → `system_tool_policy` template → `loop_message_builder.build()`
2. As **JSON Schema** in the OpenAI `tools` API parameter, via `openai_adapter._convert_tools()` → `stream_complete()`

The trigger is `rapid_loop.py:571-581`, where the same `tools` list flows into both channels.

This wastes ~450 tokens per LLM call (9 tools × ~50 tokens each). For models that natively support function calling (the design intent, as shown by `tool_choice: "auto"`), the markdown version in the system prompt is redundant.

## Approach

**Remove the markdown tool list from the system prompt entirely.** The OpenAI `tools` parameter is the sole, authoritative channel for tool definitions.

## Changes

### `backend/app/execution/prompt_manager.py`

1. `system_tool_policy` template: remove `## Available tools:\n$tool_list\n` paragraph; keep `## Tool and shell rules:` and its content
2. Template variables: `["tool_list"]` → `[]`
3. `get_system_prompt_sections()`: remove `tools` parameter; remove `tool_list = self._format_tools(tools)` and `tool_list=tool_list` kwarg
4. `get_system_prompt()`: remove `tools` parameter
5. Delete `_format_tools()` method
6. Remove `from app.llm.base import LLMToolDefinition` import

### `backend/app/execution/loop_message_builder.py`

1. `build()`: change call from `self.prompt_manager.get_system_prompt_sections(tools)` to `self.prompt_manager.get_system_prompt_sections()`
2. `build()` signature: remove `tools` parameter entirely (it was only used for `get_system_prompt_sections()`)
3. Remove `LLMToolDefinition` from imports (no longer referenced)

### `backend/app/execution/rapid_loop.py`

1. `_call_llm()`: change `self.message_builder.build(context, tools)` to `self.message_builder.build(context)`

### No changes to

- `openai_adapter.py` — `_convert_tools()` and `stream_complete()` remain the sole tool definition channel
- `runtime_tool_definitions.py` — still selects tools per phase
- `tools/registry.py` and `tools/base.py` — schema generation unchanged

## Token Savings

~450 tokens per LLM call removed (9 tools × ~50 tokens average for name + description + parameter descriptions).

## Risk

Very low. The OpenAI `tools` parameter is the standard mechanism for function calling. The `system_core` template already contains `You have access to the following tools. When you need to use a tool, simply call it.`, which is sufficient to guide the model to use tool definitions from the `tools` parameter.
