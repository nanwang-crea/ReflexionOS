# LLM 服务商与模型配置相关的数据模型：定义支持的服务商类型、单个模型/服务商实例的配置、
# 全局 LLM 设置、解析后的最终生效配置，以及连接测试的请求/结果结构。
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderType(str, Enum):
    """支持的 LLM 服务商类型：OpenAI 兼容接口、Anthropic、Ollama（本地部署）。"""

    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class ProviderModelConfig(BaseModel):
    """单个模型的配置：归属某个服务商实例下的具体模型，记录展示名、上下文窗口大小、
    是否启用，以及模型能力探测结果（视觉/工具调用/推理）。"""

    model_config = ConfigDict(
        from_attributes=True,
        protected_namespaces=(),
    )

    id: str
    display_name: str
    model_name: str
    context_window: int = 128000
    enabled: bool = True
    # Model capabilities (None = not probed, True/False = known)
    # 模型能力标记：None 表示尚未探测，True/False 为已知的探测结果
    supports_vision: bool | None = None
    supports_tools: bool | None = True
    supports_reasoning: bool | None = True


class ProviderInstanceConfig(BaseModel):
    """服务商实例配置：一个具体的服务商接入配置（如某个 API Key + Base URL 组合），
    下辖多个可用模型，并指定该实例的默认模型。"""

    model_config = ConfigDict(
        from_attributes=True,
        protected_namespaces=(),
    )

    id: str
    name: str
    provider_type: ProviderType
    api_key: str | None = None
    base_url: str | None = None
    models: list[ProviderModelConfig] = Field(default_factory=list)
    default_model_id: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_default_model(self):
        """校验 default_model_id（若设置）必须能在 models 列表中找到对应模型，
        否则视为配置非法并抛出 ValueError。"""
        if self.default_model_id and not any(
            model.id == self.default_model_id for model in self.models
        ):
            raise ValueError("default_model_id must reference an existing model")
        return self


class LLMSettings(BaseModel):
    """全局 LLM 设置：所有已配置的服务商实例、默认使用的服务商/模型，以及默认的
    生成参数（温度、最大 token 数）。"""

    model_config = ConfigDict(
        from_attributes=True,
        protected_namespaces=(),
    )

    providers: list[ProviderInstanceConfig] = Field(default_factory=list)
    default_provider_id: str | None = None
    default_model_id: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)


class DefaultLLMSelection(BaseModel):
    """当前默认选中的 LLM：服务商 id、模型 id，以及是否已完成配置（configured）。"""

    model_config = ConfigDict(protected_namespaces=())

    provider_id: str | None = None
    model_id: str | None = None
    configured: bool = False


class ResolvedLLMConfig(BaseModel):
    """解析后的最终生效 LLM 配置：合并服务商实例与模型配置后，供实际调用 LLM 时
    直接使用的扁平化配置（含鉴权信息、生成参数、模型能力）。"""

    model_config = ConfigDict(
        from_attributes=True,
        protected_namespaces=(),
    )

    provider_id: str
    provider_type: ProviderType
    model_id: str
    model: str
    context_window: int = 128000
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    # Model capabilities (inherited from ProviderModelConfig)
    # 模型能力（继承自 ProviderModelConfig）
    supports_vision: bool | None = None
    supports_tools: bool | None = True
    supports_reasoning: bool | None = True


class ProviderConnectionTestRequest(BaseModel):
    """服务商连接测试请求：待测试的服务商实例配置，可选指定测试用的具体模型 id。"""

    model_config = ConfigDict(protected_namespaces=())

    provider: ProviderInstanceConfig
    model_id: str | None = None


class ProviderConnectionTestResult(BaseModel):
    """服务商连接测试结果：是否成功、对应服务商/模型信息、结果说明文本，
    以及连接测试过程中顺带探测到的能力（如是否支持视觉输入）。"""

    model_config = ConfigDict(protected_namespaces=())

    success: bool = True
    provider_id: str
    provider_type: ProviderType
    model_id: str
    model: str
    message: str
    # Capability probe results
    # 能力探测结果
    supports_vision: bool | None = None
