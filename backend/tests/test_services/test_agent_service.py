from types import SimpleNamespace

import pytest

import app.services.agent_service as agent_service_module
from app.models.llm_config import (
    LLMSettings,
    ProviderInstanceConfig,
    ProviderModelConfig,
    ProviderType,
)


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


def build_service(monkeypatch, settings: LLMSettings | None = None):
    dummy_config = DummyConfigManager(settings)
    monkeypatch.setattr(agent_service_module, "config_manager", dummy_config)
    return agent_service_module.AgentService(), dummy_config


def test_create_provider_initializes_default_selection(monkeypatch):
    service, dummy_config = build_service(monkeypatch)
    provider = build_provider("provider-openai", "OpenAI 官方", ["gpt-4.1", "gpt-4.1-mini"])

    saved_provider = service.create_provider(provider)
    selection = service.get_default_selection()

    assert saved_provider.id == "provider-openai"
    assert selection.configured is True
    assert selection.provider_id == "provider-openai"
    assert selection.model_id == "gpt-4.1"
    assert dummy_config.settings.llm.default_provider_id == "provider-openai"
    assert dummy_config.settings.llm.default_model_id == "gpt-4.1"


def test_resolve_llm_config_uses_explicit_provider_and_model(monkeypatch):
    provider_a = build_provider("provider-a", "Provider A", ["model-a"])
    provider_b = build_provider("provider-b", "Provider B", ["model-b", "model-c"])
    settings = LLMSettings(
        providers=[provider_a, provider_b],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service(monkeypatch, settings)

    resolved = service.resolve_llm_config("provider-b", "model-c")

    assert resolved.provider_id == "provider-b"
    assert resolved.model_id == "model-c"
    assert resolved.model == "model-c"
    assert resolved.provider_type == ProviderType.OPENAI_COMPATIBLE


def test_resolve_llm_config_rejects_unknown_explicit_model(monkeypatch):
    provider = build_provider("provider-a", "Provider A", ["model-a"])
    settings = LLMSettings(
        providers=[provider],
        default_provider_id="provider-a",
        default_model_id="model-a",
    )
    service, _ = build_service(monkeypatch, settings)

    with pytest.raises(ValueError, match="所选模型不存在或已禁用"):
        service.resolve_llm_config("provider-a", "missing-model")
