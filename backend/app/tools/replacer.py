from __future__ import annotations

from typing import Generator


def _exact_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    if old_string and old_string in content:
        yield old_string


def _strip_common_indent(lines: list[str]) -> list[str]:
    min_indent = float("inf")
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            min_indent = min(min_indent, indent)
    if min_indent == float("inf"):
        return lines
    return [line[min_indent:] if line.strip() else line for line in lines]


def _whitespace_flex_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    if not old_string:
        return
    old_lines = old_string.splitlines()
    content_lines = content.splitlines()
    if len(old_lines) > len(content_lines):
        return

    old_trimmed = [l.strip() for l in old_lines]
    old_stripped = _strip_common_indent(old_lines)

    for start in range(len(content_lines) - len(old_lines) + 1):
        block = content_lines[start : start + len(old_lines)]
        if [l.strip() for l in block] == old_trimmed:
            candidate = "\n".join(block)
            if content.find(candidate) != -1:
                yield candidate
            else:
                block_stripped = _strip_common_indent(block)
                candidate2 = "\n".join(block_stripped)
                if old_stripped == block_stripped and content.find(candidate2) != -1:
                    yield candidate2


def _anchor_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    old_lines = old_string.splitlines()
    if len(old_lines) < 3:
        return
    content_lines = content.splitlines()

    first_anchor = old_lines[0].strip()
    last_anchor = old_lines[-1].strip()
    middle_old = old_lines[1:-1]

    for start in range(len(content_lines) - len(old_lines) + 1):
        block = content_lines[start : start + len(old_lines)]
        if block[0].strip() != first_anchor or block[-1].strip() != last_anchor:
            continue
        if len(middle_old) == 0:
            candidate = "\n".join(block)
            if content.find(candidate) != -1:
                yield candidate
            continue
        match_count = sum(
            1 for a, b in zip(middle_old, block[1:-1]) if a.strip() == b.strip()
        )
        if match_count / len(middle_old) >= 0.5:
            candidate = "\n".join(block)
            if content.find(candidate) != -1:
                yield candidate


_ESCAPE_MAP = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    "\\'": "'",
    '\\"': '"',
    "\\\\": "\\",
}


def _unescape(text: str) -> str:
    for esc, real in _ESCAPE_MAP.items():
        text = text.replace(esc, real)
    return text


def _escape_normalizer(content: str, old_string: str) -> Generator[str, None, None]:
    if not old_string:
        return
    unescaped = _unescape(old_string)
    if unescaped != old_string and unescaped in content:
        yield unescaped


def _global_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    if not old_string:
        return
    count = content.count(old_string)
    if count > 0:
        yield old_string


def replace(content: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    not_found = True
    for replacer in [
        _exact_replacer,
        _whitespace_flex_replacer,
        _anchor_replacer,
        _escape_normalizer,
        _global_replacer,
    ]:
        for candidate in replacer(content, old_string):
            idx = content.find(candidate)
            if idx == -1:
                continue
            not_found = False
            if replace_all:
                return content.replace(candidate, new_string)
            last_idx = content.rfind(candidate)
            if idx != last_idx:
                continue
            return content[:idx] + new_string + content[idx + len(candidate) :]
    if not_found:
        raise ValueError("未找到匹配内容，请检查 old_string 是否与文件内容一致")
    raise ValueError("匹配到多个位置，请增加上下文以唯一定位")
