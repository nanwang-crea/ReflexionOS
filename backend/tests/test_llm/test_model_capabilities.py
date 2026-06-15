import pytest
from app.llm.model_capabilities import supports_vision


def test_supports_vision_exact_match():
    """测试精确匹配支持视觉的模型"""
    assert supports_vision("gpt-4o") is True
    assert supports_vision("gpt-4o-mini") is True
    assert supports_vision("claude-3-5-sonnet") is True
    assert supports_vision("gemini-1.5-pro") is True


def test_supports_vision_wildcard_match():
    """测试通配符匹配"""
    assert supports_vision("gpt-4o-2024-05-13") is True
    assert supports_vision("claude-3-opus-20240229") is True
    assert supports_vision("gemini-pro-vision") is True


def test_does_not_support_vision():
    """测试不支持视觉的模型"""
    assert supports_vision("gpt-3.5-turbo") is False
    assert supports_vision("gpt-4") is False
    assert supports_vision("claude-2") is False
    assert supports_vision("text-davinci-003") is False


def test_unknown_model():
    """测试未知模型默认不支持"""
    assert supports_vision("unknown-model") is False
    assert supports_vision("") is False
