"""
文本压缩工具模块。

提供"保头保尾、截断中间"的文本压缩策略，用于在记忆写入/召回时把超长文本
（如工具输出、长对话内容）裁剪到限定长度，同时尽量保留首尾的关键信息。
"""

from __future__ import annotations


def truncate_head_tail(
    text: str,
    max_chars: int,
    *,
    head_chars: int,
    tail_chars: int,
    reason: str,
) -> str:
    """
    按"保留头部 + 保留尾部 + 中间截断标记"的方式压缩文本。

    参数：
        text: 原始文本，可能为 None，会被当作空字符串处理。
        max_chars: 压缩后允许的最大字符数；<=0 时直接返回空字符串。
        head_chars: 期望保留的头部字符数（关键字参数）。
        tail_chars: 期望保留的尾部字符数（关键字参数）。
        reason: 写入截断标记中的原因说明，便于后续排查为何被截断。
    逻辑：
        1. 去除首尾空白后，若长度未超过 max_chars，原样返回；
        2. 否则构造形如 "...[truncated N chars, reason]..." 的中间标记；
        3. 若连标记都放不下（max_chars 太小），退化为简单头部截断；
        4. 否则按 head_chars/tail_chars 分配头尾长度，若还有剩余空间则优先补给头部；
        5. 最终拼接为 "头部 + 标记 + 尾部"。
    返回：
        压缩后的字符串，长度不超过 max_chars。
    """
    value = (text or "").strip()
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value

    marker = f"\n...[truncated {len(value) - max_chars} chars, {reason}]...\n"
    if max_chars <= len(marker) + 2:
        return value[:max_chars]

    resolved_head = min(head_chars, max_chars - len(marker) - 1)
    resolved_tail = min(tail_chars, max_chars - len(marker) - resolved_head)
    remaining = max_chars - len(marker) - resolved_head - resolved_tail
    if remaining > 0:
        resolved_head += remaining

    return f"{value[:resolved_head]}{marker}{value[-resolved_tail:]}"
