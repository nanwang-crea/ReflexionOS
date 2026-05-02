import pytest

from app.llm.base import LLMToolCall
from app.llm.dsml_tool_parser import contains_dsml, parse_dsml_tool_calls


class TestContainsDsml:
    def test_detects_prefix(self):
        assert contains_dsml("Hello <|DSML|tool_calls>") is True

    def test_no_prefix(self):
        assert contains_dsml("Hello world") is False

    def test_empty_string(self):
        assert contains_dsml("") is False

    def test_similar_but_not_dsml(self):
        assert contains_dsml("<|OTHER|tool_calls>") is False


class TestParseDsmlToolCalls:
    def test_single_invoke(self):
        content = (
            '<|DSML|tool_calls>'
            '<|DSML|invoke name="file">'
            '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
            '<|DSML|parameter name="path"><![CDATA[/tmp/test.py]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '</|DSML|tool_calls>'
        )
        result = parse_dsml_tool_calls(content)
        assert result.clean_content == ""
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.name == "file"
        assert tc.arguments == {"action": "read", "path": "/tmp/test.py"}

    def test_multiple_invokes(self):
        content = (
            '<|DSML|tool_calls>'
            '<|DSML|invoke name="file">'
            '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
            '<|DSML|parameter name="path"><![CDATA[/a.py]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '<|DSML|invoke name="file">'
            '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
            '<|DSML|parameter name="path"><![CDATA[/b.py]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '<|DSML|invoke name="shell">'
            '<|DSML|parameter name="command"><![CDATA[ls -la]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '</|DSML|tool_calls>'
        )
        result = parse_dsml_tool_calls(content)
        assert len(result.tool_calls) == 3
        assert result.tool_calls[0].name == "file"
        assert result.tool_calls[0].arguments["path"] == "/a.py"
        assert result.tool_calls[1].name == "file"
        assert result.tool_calls[1].arguments["path"] == "/b.py"
        assert result.tool_calls[2].name == "shell"
        assert result.tool_calls[2].arguments["command"] == "ls -la"

    def test_pre_text_preserved(self):
        content = (
            'I will read the file for you. '
            '<|DSML|tool_calls>'
            '<|DSML|invoke name="file">'
            '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
            '<|DSML|parameter name="path"><![CDATA[/tmp/x]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '</|DSML|tool_calls>'
        )
        result = parse_dsml_tool_calls(content)
        assert result.clean_content == "I will read the file for you."
        assert len(result.tool_calls) == 1

    def test_no_dsml_passthrough(self):
        content = "Just a normal response with no tool calls."
        result = parse_dsml_tool_calls(content)
        assert result.clean_content == content
        assert result.tool_calls == []

    def test_malformed_dsml_fallback(self):
        content = '<|DSML|tool_calls> broken <'
        result = parse_dsml_tool_calls(content)
        # No valid invokes found, content preserved with DSML tags stripped
        assert result.tool_calls == []
        assert "broken" in result.clean_content

    def test_parameter_without_cdata(self):
        content = (
            '<|DSML|tool_calls>'
            '<|DSML|invoke name="plan">'
            '<|DSML|parameter name="goal">build the project</|DSML|parameter>'
            '</|DSML|invoke>'
            '</|DSML|tool_calls>'
        )
        result = parse_dsml_tool_calls(content)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].arguments["goal"] == "build the project"

    def test_single_quoted_attributes(self):
        content = (
            "<|DSML|tool_calls>"
            "<|DSML|invoke name='file'>"
            "<|DSML|parameter name='action'><![CDATA[read]]></|DSML|parameter>"
            "</|DSML|invoke>"
            "</|DSML|tool_calls>"
        )
        result = parse_dsml_tool_calls(content)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "file"

    def test_extra_tags_stripped_from_clean_content(self):
        content = (
            '<|DSML|thinking>planning...</|DSML|thinking>'
            '<|DSML|tool_calls>'
            '<|DSML|invoke name="file">'
            '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '</|DSML|tool_calls>'
        )
        result = parse_dsml_tool_calls(content)
        assert len(result.tool_calls) == 1
        assert "<|DSML|" not in result.clean_content
        assert "planning..." in result.clean_content

    def test_cdata_in_clean_content_stripped(self):
        content = (
            '<|DSML|thinking><![CDATA[let me think]]></|DSML|thinking>'
            '<|DSML|tool_calls>'
            '<|DSML|invoke name="file">'
            '<|DSML|parameter name="action"><![CDATA[read]]></|DSML|parameter>'
            '</|DSML|invoke>'
            '</|DSML|tool_calls>'
        )
        result = parse_dsml_tool_calls(content)
        assert "<![CDATA[" not in result.clean_content
        assert "let me think" in result.clean_content
