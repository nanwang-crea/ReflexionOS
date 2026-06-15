from uuid import uuid4

from openai import AsyncOpenAI

from app.config.settings import config_manager
from app.llm.client_headers import browser_like_default_headers
from app.llm.base import MessageRole
from app.models.llm_config import (
    DefaultLLMSelection,
    LLMSettings,
    ProviderConnectionTestResult,
    ProviderInstanceConfig,
    ProviderModelConfig,
    ProviderType,
    ResolvedLLMConfig,
)


class LLMProviderService:
    def __init__(self, *, config_manager=config_manager):
        self.config_manager = config_manager
        self.llm_settings = self._load_llm_settings()

    def _load_llm_settings(self) -> LLMSettings:
        return self._normalize_settings(self.config_manager.settings.llm)

    def _persist_llm_settings(self, settings: LLMSettings) -> None:
        normalized = self._normalize_settings(settings)
        self.llm_settings = normalized
        self.config_manager.update_llm(normalized)

    def _available_models(self, provider: ProviderInstanceConfig) -> list[ProviderModelConfig]:
        return [model for model in provider.models if model.enabled]

    def _normalize_model(self, model: ProviderModelConfig) -> ProviderModelConfig:
        model_id = model.id.strip() if model.id else ""
        display_name = model.display_name.strip()
        model_name = model.model_name.strip()

        if not display_name:
            raise ValueError("模型显示名称不能为空")
        if not model_name:
            raise ValueError("模型名称不能为空")

        return ProviderModelConfig(
            id=model_id or f"model-{uuid4().hex[:8]}",
            display_name=display_name,
            model_name=model_name,
            context_window=model.context_window,
            enabled=model.enabled,
            supports_vision=model.supports_vision,
            supports_tools=model.supports_tools,
            supports_reasoning=model.supports_reasoning,
        )

    def _normalize_provider(self, provider: ProviderInstanceConfig) -> ProviderInstanceConfig:
        provider_id = provider.id.strip() if provider.id else ""
        name = provider.name.strip()
        if not name:
            raise ValueError("供应商名称不能为空")

        normalized_models: list[ProviderModelConfig] = []
        seen_model_ids: set[str] = set()

        for raw_model in provider.models:
            model = self._normalize_model(raw_model)
            if model.id in seen_model_ids:
                raise ValueError("同一个供应商下的模型 ID 不能重复")
            seen_model_ids.add(model.id)
            normalized_models.append(model)

        if not normalized_models:
            raise ValueError("请至少配置一个模型")

        enabled_models = [model for model in normalized_models if model.enabled]
        if provider.default_model_id and any(
            model.id == provider.default_model_id for model in normalized_models
        ):
            default_model_id = provider.default_model_id
        elif enabled_models:
            default_model_id = enabled_models[0].id
        else:
            default_model_id = normalized_models[0].id

        base_url = provider.base_url.strip() if provider.base_url else None
        api_key = provider.api_key.strip() if provider.api_key else None

        return ProviderInstanceConfig(
            id=provider_id or f"provider-{uuid4().hex[:8]}",
            name=name,
            provider_type=provider.provider_type,
            api_key=api_key or None,
            base_url=base_url or None,
            models=normalized_models,
            default_model_id=default_model_id,
            enabled=provider.enabled,
        )

    def _normalize_settings(self, settings: LLMSettings) -> LLMSettings:
        normalized_providers = [
            self._normalize_provider(provider) for provider in settings.providers
        ]

        normalized = LLMSettings(
            providers=normalized_providers,
            default_provider_id=settings.default_provider_id,
            default_model_id=settings.default_model_id,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

        available_providers = [
            provider
            for provider in normalized.providers
            if provider.enabled and self._available_models(provider)
        ]

        if not available_providers:
            normalized.default_provider_id = None
            normalized.default_model_id = None
            return normalized

        default_provider = next(
            (
                provider
                for provider in available_providers
                if provider.id == normalized.default_provider_id
            ),
            available_providers[0],
        )
        available_models = self._available_models(default_provider)

        default_model = next(
            (model for model in available_models if model.id == normalized.default_model_id), None
        )
        if not default_model:
            default_model = next(
                (
                    model
                    for model in available_models
                    if model.id == default_provider.default_model_id
                ),
                available_models[0],
            )

        normalized.default_provider_id = default_provider.id
        normalized.default_model_id = default_model.id
        return normalized

    def _resolve_provider_model(
        self,
        provider: ProviderInstanceConfig,
        model_id: str | None,
        *,
        strict_model: bool,
        temperature: float,
        max_tokens: int,
    ) -> ResolvedLLMConfig:
        available_models = self._available_models(provider)
        if not available_models:
            raise ValueError("所选供应商没有可用模型")

        selected_model = None
        if model_id:
            selected_model = next(
                (model for model in available_models if model.id == model_id),
                None,
            )
            if not selected_model and strict_model:
                raise ValueError("所选模型不存在或已禁用")

        if not selected_model and provider.default_model_id:
            selected_model = next(
                (model for model in available_models if model.id == provider.default_model_id), None
            )

        if not selected_model:
            selected_model = available_models[0]

        return ResolvedLLMConfig(
            provider_id=provider.id,
            provider_type=provider.provider_type,
            model_id=selected_model.id,
            model=selected_model.model_name,
            context_window=selected_model.context_window,
            api_key=provider.api_key,
            base_url=provider.base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            supports_vision=selected_model.supports_vision,
            supports_tools=selected_model.supports_tools,
            supports_reasoning=selected_model.supports_reasoning,
        )

    def get_llm_settings(self) -> LLMSettings:
        self.llm_settings = self._load_llm_settings()
        return self.llm_settings

    def list_providers(self) -> list[ProviderInstanceConfig]:
        return self.get_llm_settings().providers

    def create_provider(self, provider: ProviderInstanceConfig) -> ProviderInstanceConfig:
        settings = self.get_llm_settings().model_copy(deep=True)
        normalized_provider = self._normalize_provider(provider)

        if any(existing.id == normalized_provider.id for existing in settings.providers):
            raise ValueError("供应商 ID 已存在")

        settings.providers.append(normalized_provider)
        self._persist_llm_settings(settings)
        return next(
            item for item in self.llm_settings.providers if item.id == normalized_provider.id
        )

    def update_provider(
        self,
        provider_id: str,
        provider: ProviderInstanceConfig,
    ) -> ProviderInstanceConfig:
        settings = self.get_llm_settings().model_copy(deep=True)
        target_index = next(
            (index for index, item in enumerate(settings.providers) if item.id == provider_id), None
        )
        if target_index is None:
            raise ValueError("供应商不存在")

        normalized_provider = self._normalize_provider(
            provider.model_copy(update={"id": provider_id})
        )
        settings.providers[target_index] = normalized_provider
        self._persist_llm_settings(settings)
        return next(item for item in self.llm_settings.providers if item.id == provider_id)

    def delete_provider(self, provider_id: str) -> None:
        settings = self.get_llm_settings().model_copy(deep=True)
        next_providers = [provider for provider in settings.providers if provider.id != provider_id]
        if len(next_providers) == len(settings.providers):
            raise ValueError("供应商不存在")

        settings.providers = next_providers
        self._persist_llm_settings(settings)

    def get_default_selection(self) -> DefaultLLMSelection:
        try:
            resolved = self.resolve_llm_config()
            return DefaultLLMSelection(
                provider_id=resolved.provider_id,
                model_id=resolved.model_id,
                configured=True,
            )
        except ValueError:
            settings = self.get_llm_settings()
            return DefaultLLMSelection(
                provider_id=settings.default_provider_id,
                model_id=settings.default_model_id,
                configured=False,
            )

    def set_default_selection(self, selection: DefaultLLMSelection) -> DefaultLLMSelection:
        if not selection.provider_id or not selection.model_id:
            raise ValueError("默认供应商和默认模型不能为空")

        settings = self.get_llm_settings().model_copy(deep=True)
        provider = next(
            (
                item
                for item in settings.providers
                if item.id == selection.provider_id and item.enabled
            ),
            None,
        )
        if not provider:
            raise ValueError("默认供应商不存在或已禁用")

        if not any(model.id == selection.model_id and model.enabled for model in provider.models):
            raise ValueError("默认模型不存在或已禁用")

        settings.default_provider_id = selection.provider_id
        settings.default_model_id = selection.model_id
        self._persist_llm_settings(settings)
        return self.get_default_selection()

    async def test_provider_connection(
        self, provider: ProviderInstanceConfig, model_id: str | None = None
    ) -> ProviderConnectionTestResult:
        settings = self.get_llm_settings()
        normalized_provider = self._normalize_provider(provider)
        resolved = self._resolve_provider_model(
            normalized_provider,
            model_id,
            strict_model=bool(model_id),
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

        if resolved.provider_type != ProviderType.OPENAI_COMPATIBLE:
            raise ValueError("当前第一阶段仅支持 OpenAI-compatible 供应商的连接测试")

        client = AsyncOpenAI(
            api_key=resolved.api_key or "reflexion-placeholder-key",
            base_url=resolved.base_url if resolved.base_url else None,
            default_headers=browser_like_default_headers(),
        )

        # Text-only request test
        await client.chat.completions.create(
            model=resolved.model,
            messages=[{"role": MessageRole.USER, "content": "ping"}],
            temperature=0,
            max_tokens=1,
        )

        # Vision capability probe
        supports_vision = await self._probe_vision_capability(client, resolved.model)

        # Update model config with probe result
        if supports_vision is not None:
            await self._update_model_capability(
                normalized_provider.id,
                resolved.model_id,
                supports_vision=supports_vision
            )

        return ProviderConnectionTestResult(
            provider_id=resolved.provider_id,
            provider_type=resolved.provider_type,
            model_id=resolved.model_id,
            model=resolved.model,
            message="连接测试成功",
            supports_vision=supports_vision,
        )

    async def _probe_vision_capability(self, client: AsyncOpenAI, model: str) -> bool | None:
        """Probe vision capability by sending a minimal image request.

        Returns:
            True if vision is supported
            False if vision is explicitly not supported (400/invalid_request_error)
            None if probe failed due to network/auth issues (keep unknown state)
        """
        # Minimal 1x1 PNG (red pixel)
        TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        try:
            await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": MessageRole.USER,
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{TINY_PNG_B64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0,
                max_tokens=1,
            )
            return True
        except Exception as e:
            # Check if it's a clear "not supported" error
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in [
                "does not support",
                "invalid_request_error",
                "image",
                "vision",
                "multimodal",
                "content type",
            ]):
                return False
            # Network/auth/other errors - keep state as None
            return None

    async def _update_model_capability(
        self,
        provider_id: str,
        model_id: str,
        supports_vision: bool | None = None
    ) -> None:
        """Update model capability fields and persist to config."""
        settings = self.get_llm_settings().model_copy(deep=True)

        provider = next(
            (p for p in settings.providers if p.id == provider_id),
            None
        )
        if not provider:
            return

        model = next(
            (m for m in provider.models if m.id == model_id),
            None
        )
        if not model:
            return

        if supports_vision is not None:
            model.supports_vision = supports_vision

        self._persist_llm_settings(settings)

    def resolve_llm_config(
        self, provider_id: str | None = None, model_id: str | None = None
    ) -> ResolvedLLMConfig:
        settings = self.get_llm_settings()
        strict_provider = bool(provider_id)
        strict_model = bool(model_id)

        selected_provider = None
        if provider_id:
            selected_provider = next(
                (
                    provider
                    for provider in settings.providers
                    if provider.id == provider_id and provider.enabled
                ),
                None,
            )
            if not selected_provider and strict_provider:
                raise ValueError("所选供应商不存在或已禁用")

        if not selected_provider:
            if not settings.default_provider_id:
                raise ValueError("请先在设置页面配置默认供应商和默认模型")

            selected_provider = next(
                (
                    provider
                    for provider in settings.providers
                    if provider.id == settings.default_provider_id and provider.enabled
                ),
                None,
            )
            if not selected_provider:
                raise ValueError("默认供应商不存在或已禁用，请重新配置")

        selected_model_id = model_id
        if not selected_model_id and settings.default_provider_id == selected_provider.id:
            selected_model_id = settings.default_model_id

        return self._resolve_provider_model(
            selected_provider,
            selected_model_id,
            strict_model=strict_model,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )


llm_provider_service = LLMProviderService()
