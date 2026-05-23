from app.llm.token_counter import count_messages_tokens, count_tokens


def test_count_tokens_english():
    text = "Hello world, this is a test."
    tokens = count_tokens(text)
    assert isinstance(tokens, int)
    assert tokens > 0


def test_count_tokens_chinese():
    text = "你好世界，这是一个测试。"
    tokens = count_tokens(text)
    assert isinstance(tokens, int)
    assert tokens > 0


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_count_messages_tokens():
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "tool", "content": "file contents here", "tool_call_id": "call_1"},
    ]
    tokens = count_messages_tokens(messages)
    assert isinstance(tokens, int)
    assert tokens > 0


def test_count_messages_tokens_empty():
    assert count_messages_tokens([]) == 0


def test_count_messages_tokens_with_tool_calls():
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "name": "read_file", "arguments": {"path": "foo.py"}}
            ],
        },
    ]
    tokens = count_messages_tokens(messages)
    assert tokens > 0


def test_count_tokens_model_fallback():
    text = "Hello world"
    tokens_default = count_tokens(text)
    tokens_custom = count_tokens(text, model="gpt-4")
    assert tokens_default > 0
    assert tokens_custom > 0
