"""LLM 供应商配置服务：管理供应商（provider）及其模型列表的增删改查、配置归一化、默认供应商/模型选择、
连接测试（含视觉能力探测），并负责将请求解析为可直接用于调用 LLM 的 ResolvedLLMConfig。"""

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
    """LLM 供应商配置服务：所有读写都经过 _normalize_settings 归一化，保证 id、默认值等字段始终合法。"""

    def __init__(self, *, config_manager=config_manager):
        """初始化服务，加载并归一化当前持久化的 LLM 配置。
        输入：config_manager（配置管理器，默认使用全局单例，便于测试替换）
        """
        self.config_manager = config_manager
        self.llm_settings = self._load_llm_settings()

    def _load_llm_settings(self) -> LLMSettings:
        """从配置管理器读取原始 LLM 配置并归一化。
        输出：归一化后的 LLMSettings
        """
        return self._normalize_settings(self.config_manager.settings.llm)

    def _persist_llm_settings(self, settings: LLMSettings) -> None:
        """归一化配置后写入内存缓存并持久化到配置文件。
        输入：settings（待保存的 LLMSettings）
        输出：无（更新 self.llm_settings 并调用 config_manager.update_llm 落盘）
        """
        normalized = self._normalize_settings(settings)
        self.llm_settings = normalized
        self.config_manager.update_llm(normalized)

    def _available_models(self, provider: ProviderInstanceConfig) -> list[ProviderModelConfig]:
        """筛选供应商下已启用的模型。
        输入：provider
        输出：enabled=True 的模型列表
        """
        return [model for model in provider.models if model.enabled]

    def _normalize_model(self, model: ProviderModelConfig) -> ProviderModelConfig:
        """归一化单个模型配置：校验必填字段、缺失 id 时自动生成。
        输入：model（原始模型配置）
        输出：归一化后的 ProviderModelConfig（id 缺省时补 "model-<8位随机hex>"）
        异常：ValueError（显示名称或模型名称为空）
        """
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
        """归一化单个供应商配置：校验名称、去重并归一化模型列表、推断默认模型 ID。
        输入：provider（原始供应商配置）
        逻辑：
          1. 名称必填，id 缺省时自动生成；
          2. 逐个归一化模型并检查模型 id 在同供应商内不重复，且至少保留一个模型；
          3. default_model_id 优先沿用原值（若仍存在），否则取第一个已启用模型，都没有则取第一个模型；
          4. base_url / api_key 去除首尾空白，空字符串归一化为 None。
        输出：归一化后的 ProviderInstanceConfig
        异常：ValueError（名称为空 / 模型 id 重复 / 无可用模型）
        """
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
        """归一化整体 LLM 配置：归一化所有供应商，并重新计算全局默认供应商/模型。
        输入：settings（原始配置，含供应商列表和默认选择）
        逻辑：
          1. 逐个归一化 providers；
          2. 筛选出"已启用且有可用模型"的供应商列表 available_providers，为空则清空默认选择并直接返回；
          3. 默认供应商优先沿用原 default_provider_id（若仍在 available_providers 中），否则取第一个；
          4. 默认模型同理，优先沿用原 default_model_id，否则回退到该供应商的 default_model_id，最后兜底第一个可用模型。
        输出：归一化后的 LLMSettings（default_provider_id / default_model_id 始终指向合法值或均为 None）
        """
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
        """在给定供应商下选定具体模型，组装成可直接用于调用 LLM 的 ResolvedLLMConfig。
        输入：
          - provider：已选定的供应商
          - model_id：期望使用的模型 id（可选）
          - strict_model：True 时若 model_id 指定的模型不存在/未启用则抛异常；False 时静默回退
          - temperature / max_tokens：采样参数，透传到结果
        逻辑：优先使用显式 model_id 命中的模型，否则回退到供应商 default_model_id，最后兜底第一个可用模型
        输出：ResolvedLLMConfig（含供应商类型、模型名、api_key/base_url、能力标记等）
        异常：ValueError（供应商无可用模型 / strict_model 时指定模型不存在）
        """
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
        """重新加载并返回最新的 LLM 配置（每次调用都会从 config_manager 重新读取，保证读到最新落盘值）。
        输出：归一化后的 LLMSettings
        """
        self.llm_settings = self._load_llm_settings()
        return self.llm_settings

    def list_providers(self) -> list[ProviderInstanceConfig]:
        """列出所有已配置的供应商（含禁用的）。
        输出：ProviderInstanceConfig 列表
        """
        return self.get_llm_settings().providers

    def create_provider(self, provider: ProviderInstanceConfig) -> ProviderInstanceConfig:
        """新增一个供应商配置。
        输入：provider（新供应商配置）
        逻辑：归一化后校验 id 不与现有供应商冲突，追加并持久化
        输出：持久化后的 ProviderInstanceConfig
        异常：ValueError（供应商 id 已存在 / 归一化校验失败）
        """
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
        """更新指定供应商的配置（整体替换，id 保持不变）。
        输入：provider_id（目标供应商 id）、provider（新的完整配置）
        输出：更新后的 ProviderInstanceConfig
        异常：ValueError（供应商不存在 / 归一化校验失败）
        """
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
        """删除指定供应商。
        输入：provider_id
        输出：无（删除后重新归一化并持久化，若被删除的是默认供应商会在归一化中重新选取默认值）
        异常：ValueError（供应商不存在）
        """
        settings = self.get_llm_settings().model_copy(deep=True)
        next_providers = [provider for provider in settings.providers if provider.id != provider_id]
        if len(next_providers) == len(settings.providers):
            raise ValueError("供应商不存在")

        settings.providers = next_providers
        self._persist_llm_settings(settings)

    def get_default_selection(self) -> DefaultLLMSelection:
        """获取当前默认供应商/模型选择，附带是否"可正常解析使用"的标记。
        逻辑：尝试完整解析一次配置（resolve_llm_config），成功则 configured=True；
              若解析失败（如默认供应商已禁用等），回退读取原始 default_provider_id/default_model_id 并标记 configured=False
        输出：DefaultLLMSelection
        """
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
        """设置全局默认供应商和默认模型。
        输入：selection（含 provider_id、model_id）
        逻辑：校验目标供应商已启用、目标模型存在且已启用，通过后写入配置并持久化
        输出：写入后重新读取的 DefaultLLMSelection
        异常：ValueError（provider_id/model_id 为空 / 供应商不存在或禁用 / 模型不存在或禁用）
        """
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
        """测试供应商连接是否可用：发送一次最小文本请求验证可达性，并顺带探测视觉能力。
        输入：provider（待测试的供应商配置，未必已保存）、model_id（可选，指定测试的模型）
        逻辑：
          1. 归一化供应商配置并解析出具体模型（ResolvedLLMConfig）；
          2. 目前仅支持 OpenAI-compatible 类型供应商，其余类型直接报错；
          3. 用 AsyncOpenAI 客户端发送一条最小 "ping" 请求验证连通性（异常会向上抛出）；
          4. 调用 _probe_vision_capability 探测该模型是否支持图片输入；
          5. 若探测出明确结果，回写并持久化到模型配置的 supports_vision 字段。
        输出：ProviderConnectionTestResult（含探测出的视觉能力等信息）
        异常：ValueError（非 OpenAI-compatible 供应商）；网络/鉴权异常向上抛出
        """
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
        """通过发送一张最小图片请求，探测模型是否支持视觉（图片输入）能力。
        输入：client（已配置好的 AsyncOpenAI 客户端）、model（模型名称）
        逻辑：发送含 1x1 像素 PNG 的对话请求；成功即视为支持；若报错信息明确指向"不支持图片/视觉"则判定不支持；
              其余异常（网络、鉴权等不确定原因）不下结论，保持未知状态。

        Returns:
            True 表示明确支持视觉
            False 表示明确不支持（命中 400/invalid_request_error 等"不支持"类报错关键字）
            None 表示因网络/鉴权等问题探测失败，能力未知，不覆盖已有配置
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
        """回写模型探测出的能力字段并持久化配置。
        输入：provider_id、model_id（定位目标模型）、supports_vision（探测结果，None 表示不更新该字段）
        输出：无（供应商或模型不存在时静默跳过，不抛异常）
        """
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
        """解析出一份可直接用于调用 LLM 的完整配置，是对话服务发起请求前的入口方法。
        输入：provider_id（可选，指定供应商，缺省用全局默认）、model_id（可选，指定模型，缺省用默认）
        逻辑：
          1. 若指定 provider_id，必须命中已启用的供应商，否则报错（strict）；
          2. 未指定则回退全局默认供应商，默认供应商本身若不存在/已禁用也报错；
          3. 模型 id 若未显式传入，且当前供应商正是全局默认供应商，则复用全局默认模型 id；
          4. 交给 _resolve_provider_model 最终选定模型并组装结果。
        输出：ResolvedLLMConfig
        异常：ValueError（指定供应商不存在或禁用 / 未配置默认供应商 / 默认供应商失效）
        """
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
