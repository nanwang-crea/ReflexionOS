from __future__ import annotations

import json

import tiktoken


def _get_encoding(model: str = "cl100k_base") -> tiktoken.Encoding:
    """获取 tiktoken encoding，优先按 model 名称查找，回退到 cl100k_base"""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """计算文本的 token 数"""
    if not text:
        return 0
    encoding = _get_encoding(model)
    return len(encoding.encode(text))


def count_messages_tokens(
    messages: list[dict], model: str = "cl100k_base"
) -> int:
    """计算消息列表的总 token 数（含消息开销），遵循 OpenAI 的计数规则"""
    if not messages:
        return 0
    total = 0
    for msg in messages:
        total += 4  # 每条消息的基础开销（role、分隔符等）
        content = msg.get("content")
        if isinstance(content, str):
            total += count_tokens(content, model)
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                total += count_tokens(tc.get("name", ""), model)
                args_str = json.dumps(tc.get("arguments", {}), ensure_ascii=False)
                total += count_tokens(args_str, model)
                total += 3  # tool_call 的额外开销
        tool_call_id = msg.get("tool_call_id")
        if tool_call_id:
            total += count_tokens(str(tool_call_id), model)
    total += 2  # priming tokens（对话开始标记）
    return total
