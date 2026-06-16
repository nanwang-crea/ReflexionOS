from __future__ import annotations

import json

import tiktoken


def _get_encoding(model: str = "cl100k_base") -> tiktoken.Encoding:
    """Return the best matching tiktoken encoding for the given model name."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    """Count the token length for plain text."""
    if not text:
        return 0
    encoding = _get_encoding(model)
    return len(encoding.encode(text))


def count_messages_tokens(messages: list[dict], model: str = "cl100k_base") -> int:
    """Count tokens for chat messages, including multimodal content parts."""
    if not messages:
        return 0

    total = 0
    for msg in messages:
        total += 4
        content = msg.get("content")
        if isinstance(content, str):
            total += count_tokens(content, model)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    total += count_tokens(text, model)
                image_url = part.get("image_url")
                if isinstance(image_url, dict):
                    url = image_url.get("url")
                    if isinstance(url, str):
                        total += count_tokens(url, model)

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                total += count_tokens(tc.get("name", ""), model)
                args_str = json.dumps(tc.get("arguments", {}), ensure_ascii=False)
                total += count_tokens(args_str, model)
                total += 3

        tool_call_id = msg.get("tool_call_id")
        if tool_call_id:
            total += count_tokens(str(tool_call_id), model)

    total += 2
    return total
