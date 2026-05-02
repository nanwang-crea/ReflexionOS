"""Parse DSML-format tool calls emitted by some models as text content.

Certain models (notably several Chinese LLMs served via OpenAI-compatible
APIs) output tool calls as text in DSML markup instead of using the
structured ``tool_calls`` field of the OpenAI Chat Completion API.

DSML example::

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

# <|DSML|tool_calls> ... </|DSML|tool_calls>
_DSML_BLOCK_RE = re.compile(
    r"<\|DSML\|tool_calls[^>]*>(.*?)</\|DSML\|tool_calls[^>]*>",
    re.DOTALL,
)

# <|DSML|invoke name="..."> ... </|DSML|invoke>
_INVOKE_RE = re.compile(
    r"""<\|DSML\|invoke\s+name=["']([^"']+)["'][^>]*>(.*?)</\|DSML\|invoke[^>]*>""",
    re.DOTALL,
)

# <|DSML|parameter name="..."> ... </|DSML|parameter>
_PARAM_RE = re.compile(
    r"""<\|DSML\|parameter\s+name=["']([^"']+)["'][^>]*>(.*?)</\|DSML\|parameter[^>]*>""",
    re.DOTALL,
)

# <![CDATA[ ... ]]>
_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)]]>", re.DOTALL)

# Any <|DSML|...> or </|DSML|...> tag (for stripping)
_DSML_ANY_TAG_RE = re.compile(r"</?\|DSML\|[^>]*>")


def _extract_value(text: str) -> str:
    """Extract parameter value, unwrapping CDATA if present."""
    m = _CDATA_RE.search(text)
    return m.group(1) if m else text.strip()


class DsmlParseResult:
    __slots__ = ("tool_calls", "clean_content")

    def __init__(self, tool_calls: list[LLMToolCall], clean_content: str):
        self.tool_calls = tool_calls
        self.clean_content = clean_content


def parse_dsml_tool_calls(content: str) -> DsmlParseResult:
    """Parse DSML tool calls from model text output.

    Returns:
        DsmlParseResult with extracted tool_calls and content with DSML stripped.
    """
    tool_calls: list[LLMToolCall] = []
    clean_parts: list[str] = []
    last_end = 0

    for block_match in _DSML_BLOCK_RE.finditer(content):
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

    clean_parts.append(content[last_end:])
    clean_content = _DSML_ANY_TAG_RE.sub("", "".join(clean_parts)).strip()
    clean_content = _CDATA_RE.sub(r"\1", clean_content).strip()

    return DsmlParseResult(tool_calls=tool_calls, clean_content=clean_content)


def contains_dsml(content: str) -> bool:
    """Check whether *content* contains DSML markup."""
    return _DSML_PREFIX in content
