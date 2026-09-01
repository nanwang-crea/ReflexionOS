"""解析部分模型以纯文本形式输出的 DSML 格式工具调用。

部分模型（尤其是一些通过 OpenAI 兼容接口提供服务的国产 LLM）不使用
Chat Completion API 标准的结构化 tool_calls 字段，而是把工具调用
以 DSML 标记语言的形式直接写在文本正文里。本模块负责从这种文本中
提取出结构化的工具调用列表，并把 DSML 标记从正文中剥离干净。

DSML 示例::

    <|DSML|tool_calls>
      <|DSML|invoke name="file">
        <|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>
        <|DSML|parameter name="path"><![CDATA[/tmp/test.py]]></|DSML|parameter>
      </|DSML|invoke>
    </|DSML|tool_calls>
"""

import re

from app.llm.base import LLMToolCall

_DSML_PREFIX = "<|DSML|"

# <|DSML|tool_calls> ... </|DSML|tool_calls>：匹配整个工具调用块
_DSML_BLOCK_RE = re.compile(
    r"<\|DSML\|tool_calls[^>]*>(.*?)</\|DSML\|tool_calls[^>]*>",
    re.DOTALL,
)

# <|DSML|invoke name="..."> ... </|DSML|invoke>：匹配块内单次工具调用（含工具名）
_INVOKE_RE = re.compile(
    r"""<\|DSML\|invoke\s+name=["']([^"']+)["'][^>]*>(.*?)</\|DSML\|invoke[^>]*>""",
    re.DOTALL,
)

# <|DSML|parameter name="..."> ... </|DSML|parameter>：匹配单个调用参数（含参数名）
_PARAM_RE = re.compile(
    r"""<\|DSML\|parameter\s+name=["']([^"']+)["'][^>]*>(.*?)</\|DSML\|parameter[^>]*>""",
    re.DOTALL,
)

# <![CDATA[ ... ]]>：参数值常见的 CDATA 包裹形式
_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)]]>", re.DOTALL)

# 任意 <|DSML|...> 或 </|DSML|...> 标签，用于兜底清理残留标记
_DSML_ANY_TAG_RE = re.compile(r"</?\|DSML\|[^>]*>")


def _extract_value(text: str) -> str:
    """提取参数值，若被 CDATA 包裹则先解包

    输入: text - 参数标签内的原始文本
    逻辑: 优先匹配 CDATA 包裹内容并取出，否则直接对原文本去除首尾空白
    返回: 参数的纯文本值
    """
    m = _CDATA_RE.search(text)
    return m.group(1) if m else text.strip()


class DsmlParseResult:
    """DSML 解析结果

    tool_calls: 从文本中解析出的工具调用列表
    clean_content: 剥离 DSML 标记后剩余的正文内容
    """

    __slots__ = ("tool_calls", "clean_content")

    def __init__(self, tool_calls: list[LLMToolCall], clean_content: str):
        self.tool_calls = tool_calls
        self.clean_content = clean_content


def parse_dsml_tool_calls(content: str) -> DsmlParseResult:
    """从模型文本输出中解析 DSML 格式的工具调用

    输入: content - 模型返回的原始文本（可能夹杂 DSML 标记）
    逻辑: 用正则依次定位所有 <|DSML|tool_calls> 块；对每个块再解析其中的
          <|DSML|invoke>（工具名）和 <|DSML|parameter>（参数名/值，含 CDATA 解包），
          组装为 LLMToolCall；同时把各 DSML 块之间的非 DSML 文本片段拼接保留，
          最后对拼接结果做一次兜底清理，去掉任何残留的 DSML 标签和 CDATA 包裹

    返回:
        DsmlParseResult，包含解析出的 tool_calls 和剥离 DSML 标记后的 clean_content
    """
    tool_calls: list[LLMToolCall] = []
    clean_parts: list[str] = []
    last_end = 0

    for block_match in _DSML_BLOCK_RE.finditer(content):
        # 保留当前 DSML 块之前的普通文本
        clean_parts.append(content[last_end:block_match.start()])
        last_end = block_match.end()

        block_body = block_match.group(1)
        for invoke_match in _INVOKE_RE.finditer(block_body):
            tool_name = invoke_match.group(1)
            params_body = invoke_match.group(2)

            arguments: dict[str, str] = {}
            for param_match in _PARAM_RE.finditer(params_body):
                param_name = param_match.group(1)
                param_value = _extract_value(param_match.group(2))
                arguments[param_name] = param_value

            tool_calls.append(LLMToolCall(name=tool_name, arguments=arguments))

    # 保留最后一个 DSML 块之后的剩余文本
    clean_parts.append(content[last_end:])
    # 兜底：清掉可能残留的 DSML 标签和 CDATA 包裹符号
    clean_content = _DSML_ANY_TAG_RE.sub("", "".join(clean_parts)).strip()
    clean_content = _CDATA_RE.sub(r"\1", clean_content).strip()

    return DsmlParseResult(tool_calls=tool_calls, clean_content=clean_content)


def contains_dsml(content: str) -> bool:
    """判断文本中是否包含 DSML 标记

    输入: content - 待检查文本
    逻辑: 简单检查是否包含 DSML 标记前缀，作为是否需要走 DSML 解析路径的快速判断
    返回: 是否包含 DSML 标记
    """
    return _DSML_PREFIX in content
