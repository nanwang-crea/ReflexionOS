"""LLM 文本/消息 token 计数工具。

基于 tiktoken 提供近似的 token 计数能力，用于上下文长度控制、用量估算等场景。
非严格准确（不同模型/不同 provider 的分词规则可能有差异），但足够用于预算控制。
"""

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
    """计算文本的 token 数

    输入: text - 待计数文本；model - 模型名（用于选择对应 encoding，找不到则回退 cl100k_base）
    逻辑: 空文本直接返回 0，否则取对应 encoding 编码后统计 token 数量
    返回: token 数量
    """
    if not text:
        return 0
    encoding = _get_encoding(model)
    return len(encoding.encode(text))


def count_messages_tokens(
    messages: list[dict], model: str = "cl100k_base"
) -> int:
    """计算消息列表的总 token 数（含消息开销），遵循 OpenAI 的计数规则

    输入: messages - 消息字典列表（含 content/tool_calls/tool_call_id 等字段）；
          model - 模型名，用于选择 encoding
    逻辑: 遍历每条消息，累加其固定开销（角色/分隔符等）、正文 token 数、
          工具调用（名称+参数 JSON 序列化后）的 token 数及其额外开销，
          最后加上整个对话的起始标记开销
    返回: 消息列表总 token 数（近似值）
    """
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
