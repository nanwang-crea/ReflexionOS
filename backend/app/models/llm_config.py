from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderType(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class ProviderModelConfig(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        protected_namespaces=(),
    )

    id: str
    display_name: str
    model_name: str
    enabled: bool = True


class ProviderInstanceConfig(BaseModel):
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
        if self.default_model_id and not any(
            model.id == self.default_model_id for model in self.models
        ):
            raise ValueError("default_model_id must reference an existing model")
        return self


class LLMSettings(BaseModel):
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
    model_config = ConfigDict(protected_namespaces=())

    provider_id: str | None = None
    model_id: str | None = None
    configured: bool = False


class ResolvedLLMConfig(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        protected_namespaces=(),
    )

    provider_id: str
    provider_type: ProviderType
    model_id: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)


class ProviderConnectionTestRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider: ProviderInstanceConfig
    model_id: str | None = None


class ProviderConnectionTestResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    success: bool = True
    provider_id: str
    provider_type: ProviderType
    model_id: str
    model: str
    message: str
