# 文本替换核心算法：供 edit_tool.py 使用，实现类似 Claude Code Edit 工具的
# "模糊匹配" old_string -> new_string 替换策略。
# 设计思路：依次尝试多种匹配策略（精确匹配 -> 空白容错 -> 首尾锚点 -> 转义符规整 -> 兜底全局匹配），
# 每种策略产出候选匹配文本，找到唯一匹配即执行替换；找不到或匹配到多处均报错，
# 避免因缩进/转义符差异导致 LLM 生成的 old_string 与文件实际内容无法匹配。
from __future__ import annotations

from collections.abc import Generator


def _exact_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    """精确匹配策略：old_string 原样是否出现在 content 中。

    入参：content (str) - 文件全文；old_string (str) - 待查找的原文本片段。
    出参：Generator[str] - 命中时 yield old_string 本身（作为候选匹配文本），否则不产出。
    """
    if old_string and old_string in content:
        yield old_string


def _strip_common_indent(lines: list[str]) -> list[str]:
    """去除多行文本的公共缩进（保留空行原样）。

    入参：lines (list[str]) - 按行拆分的文本。
    功能：找出所有非空行中最小的前导空白长度，将其从每个非空行统一裁掉，
    用于比较"整体缩进不同但相对结构相同"的代码块。
    出参：list[str] - 去除公共缩进后的行列表；全为空行时原样返回。
    """
    min_indent = float("inf")
    for line in lines:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            min_indent = min(min_indent, indent)
    if min_indent == float("inf"):
        return lines
    return [line[min_indent:] if line.strip() else line for line in lines]


def _whitespace_flex_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    """空白容错匹配策略：允许 old_string 与文件实际内容在行首/行尾空白上有差异。

    入参：content (str) - 文件全文；old_string (str) - 待查找的原文本片段（可能带有不精确的缩进）。
    功能：
      1. 按行数滑动窗口扫描 content，找出每行 strip 后与 old_string 逐行相同的候选块；
      2. 优先尝试候选块原文本是否能在 content 中原样定位到；
      3. 若不行，再各自去除公共缩进后比较，试图定位去缩进后的等价文本。
    出参：Generator[str] - 逐个 yield 在 content 中真实存在、可用于定位替换位置的候选文本。
    """
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
    """首尾锚点匹配策略：仅要求首行、尾行精确匹配，中间行允许部分差异（≥50%相似）。

    入参：content (str) - 文件全文；old_string (str) - 待查找的原文本片段（至少 3 行才生效）。
    功能：用 old_string 的首行和尾行（strip 后）作为"锚点"在 content 中滑动查找候选块，
    锚点吻合后再比较中间行的相似度，中间行完全为空则直接接受，否则要求逐行 strip 后
    相同的比例达到 50% 以上才认为是同一处需要替换的位置，用于容忍 LLM 复述中间行时的细微出入。
    出参：Generator[str] - 逐个 yield 满足锚点+相似度条件、且在 content 中真实存在的候选文本。
    """
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
            1 for a, b in zip(middle_old, block[1:-1], strict=False) if a.strip() == b.strip()
        )
        if match_count / len(middle_old) >= 0.5:
            candidate = "\n".join(block)
            if content.find(candidate) != -1:
                yield candidate


# 常见转义序列到真实字符的映射，用于修正 LLM 输出中把换行/引号等误写成转义形式的情况
_ESCAPE_MAP = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    "\\'": "'",
    '\\"': '"',
    "\\\\": "\\",
}


def _unescape(text: str) -> str:
    """将文本中的常见转义序列替换为真实字符。

    入参：text (str) - 可能包含 \\n \\t \\" 等转义序列的文本。
    功能：依次按 _ESCAPE_MAP 表做字符串替换（顺序敏感，"\\\\"放最后避免误伤已替换结果）。
    出参：str - 替换转义序列后的文本。
    """
    for esc, real in _ESCAPE_MAP.items():
        text = text.replace(esc, real)
    return text


def _escape_normalizer(content: str, old_string: str) -> Generator[str, None, None]:
    """转义符规整策略：old_string 中的转义序列被还原为真实字符后能否命中 content。

    入参：content (str) - 文件全文；old_string (str) - 可能被 LLM 错误转义的原文本片段。
    功能：处理 LLM 把文件里真实的换行/引号误写成字面转义序列（如 "\\n"）的情况。
    出参：Generator[str] - 命中时 yield 反转义后的文本。
    """
    if not old_string:
        return
    unescaped = _unescape(old_string)
    if unescaped != old_string and unescaped in content:
        yield unescaped


def _global_replacer(content: str, old_string: str) -> Generator[str, None, None]:
    """兜底策略：只要 old_string 在 content 中出现过（不管出现几次）就产出。

    入参：content (str) - 文件全文；old_string (str) - 待查找的原文本片段。
    功能：作为其他策略都失败后的最后兜底，允许后续 replace() 根据 replace_all
    参数决定是替换全部匹配还是因多处匹配而报错。
    出参：Generator[str] - 命中时 yield old_string 本身。
    """
    if not old_string:
        return
    count = content.count(old_string)
    if count > 0:
        yield old_string


def replace(content: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """执行字符串替换，依次尝试多种匹配策略直到唯一定位成功。

    入参：
      - content (str): 文件原始全文
      - old_string (str): 待替换的原文本（可能与文件内容有缩进/转义等细微差异）
      - new_string (str): 替换后的新文本
      - replace_all (bool): True 时替换所有匹配处；False（默认）要求唯一匹配，
        若匹配到多处则报错，避免误改不该改的位置
    功能：按 [精确匹配, 空白容错, 首尾锚点, 转义规整, 全局兜底] 顺序尝试各策略，
    对每个候选匹配文本，用 content.find/rfind 判断是否唯一出现；replace_all=True
    时只要能定位到就直接做全局替换；否则要求 idx == rfind 结果（即只出现一次）才替换。
    出参：str - 替换后的新文件内容；找不到匹配或匹配到多处时抛出 ValueError。
    """
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
