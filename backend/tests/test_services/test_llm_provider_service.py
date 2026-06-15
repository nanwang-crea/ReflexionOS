from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.llm_config import (
    LLMSettings,
    ProviderInstanceConfig,
    ProviderModelConfig,
    ProviderType,
)
from app.services.llm_provider_service import LLMProviderService


class DummyConfigManager:
    def __init__(self, settings: LLMSettings | None = None):
        self.settings = SimpleNamespace(llm=settings or LLMSettings())

    def update_llm(self, llm_settings: LLMSettings):
        self.settings.llm = llm_settings


def build_provider(
    provider_id: str,
    name: str,
    model_ids: list[str],
    provider_type: ProviderType = ProviderType.OPENAI_COMPATIBLE,
):
    models = [
        ProviderModelConfig(
            id=model_id,
            display_name=model_id.upper(),
            model_name=model_id,
            enabled=True,
        )
        for model_id in model_ids
    ]
    return ProviderInstanceConfig(
        id=provider_id,
        name=name,
        provider_type=provider_type,
        api_key="test-key",
        base_url="https://example.com/v1",
        models=models,
        default_model_id=models[0].id,
        enabled=True,
    )


def build_service(settings: LLMSettings | None = None):
    dummy_config = DummyConfigManager(settings)
    return LLMProviderService(config_manager=dummy_config), dummy_config


def test_create_provider_initializes_default_selection():
    service, dummy_config = build_service()
    provider = build_provider("provider-openai", "OpenAI 官方", ["gpt-4.1", "gpt-4.1-mini"])

    saved_provider = service.create_provider(provider)
    selection = service.get_default_selection()

    assert saved_provider.id == "provider-openai"
    assert selection.configured is True
    assert selection.provider_id == "provider-openai"
    assert selection.model_id == "gpt-4.1"
    assert dummy_config.settings.llm.default_provider_id == "provider-openai"
    assert dummy_config.settings.llm.default_model_id == "gpt-4.1"


def test_resolve_llm_config_uses_explicit_provider_and_model():
    provider_a = build_provider("provider-a", "Provider A", ["model-a"])
    provider_b = build_provider("provider-b", "Provider B", ["model-b", "model-c"])
    settings = LLMSettings(
        providers=[provider_a, provider_b],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service(settings)

    resolved = service.resolve_llm_config("provider-b", "model-c")

    assert resolved.provider_id == "provider-b"
    assert resolved.model_id == "model-c"
    assert resolved.model == "model-c"
    assert resolved.provider_type == ProviderType.OPENAI_COMPATIBLE


def test_resolve_llm_config_rejects_unknown_explicit_model():
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service(settings)

    with pytest.raises(ValueError, match="所选模型不存在或已禁用"):
        service.resolve_llm_config("provider-a", "missing-model")


@pytest.mark.asyncio
async def test_test_provider_connection_sets_browser_like_default_headers():
    provider = build_provider("provider-openai", "OpenAI 官方", ["gpt-4.1"])
    service, _ = build_service()

    with patch("app.services.llm_provider_service.AsyncOpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create = AsyncMock(return_value=SimpleNamespace())

        await service.test_provider_connection(provider, "gpt-4.1")

    kwargs = mock_openai.call_args.kwargs
    headers = kwargs["default_headers"]

    assert "Chrome/125.0.0.0" in headers["User-Agent"]
    assert headers["Accept"] == "application/json"
    assert headers["Accept-Language"] == "en-US,en;q=0.9"
    assert headers["Cache-Control"] == "no-cache"
    assert headers["Pragma"] == "no-cache"


@pytest.mark.asyncio
async def test_vision_probe_success():
    """测试 vision 探测成功"""
    provider = build_provider("provider-openai", "OpenAI", ["gpt-4o"])
    settings = LLMSettings(providers=[provider])
    service, dummy_config = build_service(settings)

    with patch("app.services.llm_provider_service.AsyncOpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        # 两次调用都成功：文本测试 + vision 探测
        mock_client.chat.completions.create = AsyncMock(return_value=SimpleNamespace())

        result = await service.test_provider_connection(provider, "gpt-4o")

    assert result.success is True
    assert result.supports_vision is True
    # 验证配置已持久化
    saved_settings = service.get_llm_settings()
    saved_model = saved_settings.providers[0].models[0]
    assert saved_model.supports_vision is True


@pytest.mark.asyncio
async def test_vision_probe_not_supported():
    """测试 vision 探测失败（模型不支持）"""
    provider = build_provider("provider-openai", "OpenAI", ["gpt-3.5"])
    settings = LLMSettings(providers=[provider])
    service, dummy_config = build_service(settings)

    with patch("app.services.llm_provider_service.AsyncOpenAI") as mock_openai:
        mock_client = mock_openai.return_value

        # 第一次调用成功（文本测试），第二次失败（vision 探测）
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace()
            else:
                raise Exception("invalid_request_error: model does not support vision")

        mock_client.chat.completions.create = AsyncMock(side_effect=side_effect)

        result = await service.test_provider_connection(provider, "gpt-3.5")

    assert result.success is True
    assert result.supports_vision is False
    # 验证配置已持久化
    saved_settings = service.get_llm_settings()
    saved_model = saved_settings.providers[0].models[0]
    assert saved_model.supports_vision is False


@pytest.mark.asyncio
async def test_vision_probe_network_error():
    """测试 vision 探测遇到网络错误（保持 None 状态）"""
    provider = build_provider("provider-openai", "OpenAI", ["gpt-4"])
    settings = LLMSettings(providers=[provider])
    service, dummy_config = build_service(settings)

    with patch("app.services.llm_provider_service.AsyncOpenAI") as mock_openai:
        mock_client = mock_openai.return_value

        # 第一次调用成功（文本测试），第二次网络错误（vision 探测）
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace()
            else:
                raise Exception("Connection timeout")

        mock_client.chat.completions.create = AsyncMock(side_effect=side_effect)

        result = await service.test_provider_connection(provider, "gpt-4")

    assert result.success is True
    # 网络错误应该保持 None 状态
    assert result.supports_vision is None
    # 验证配置未更新（仍然是 None）
    saved_settings = service.get_llm_settings()
    saved_model = saved_settings.providers[0].models[0]
    assert saved_model.supports_vision is None
