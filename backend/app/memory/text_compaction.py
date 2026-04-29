from __future__ import annotations


def truncate_head_tail(
    text: str,
    max_chars: int,
    *,
    head_chars: int,
    tail_chars: int,
    reason: str,
) -> str:
    value = (text or "").strip()
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value

    marker = f"\n...[省略 {len(value) - max_chars} chars for {reason}]...\n"
    if max_chars <= len(marker) + 2:
        return value[:max_chars]

    resolved_head = min(head_chars, max_chars - len(marker) - 1)
    resolved_tail = min(tail_chars, max_chars - len(marker) - resolved_head)
    remaining = max_chars - len(marker) - resolved_head - resolved_tail
    if remaining > 0:
        resolved_head += remaining

    return f"{value[:resolved_head]}{marker}{value[-resolved_tail:]}"
