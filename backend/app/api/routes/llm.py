from fastapi import APIRouter

from app.errors import NotFoundError, ValidationError, value_error_to_app_error
from app.models.llm_config import (
    DefaultLLMSelection,
    ProviderConnectionTestRequest,
    ProviderConnectionTestResult,
    ProviderInstanceConfig,
)
from app.services.llm_provider_service import llm_provider_service

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/providers", response_model=list[ProviderInstanceConfig])
async def list_providers():
    return llm_provider_service.list_providers()


@router.post("/providers", response_model=ProviderInstanceConfig)
async def create_provider(provider: ProviderInstanceConfig):
    try:
        return llm_provider_service.create_provider(provider)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="供应商") from exc


@router.put("/providers/{provider_id}", response_model=ProviderInstanceConfig)
async def update_provider(provider_id: str, provider: ProviderInstanceConfig):
    try:
        return llm_provider_service.update_provider(provider_id, provider)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="供应商") from exc


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    try:
        llm_provider_service.delete_provider(provider_id)
        return {"message": "供应商已删除"}
    except ValueError as exc:
        raise NotFoundError(resource="供应商", resource_id=provider_id, message=str(exc)) from exc


@router.post("/providers/test", response_model=ProviderConnectionTestResult)
async def test_provider_connection(request: ProviderConnectionTestRequest):
    try:
        return await llm_provider_service.test_provider_connection(
            request.provider,
            request.model_id,
        )
    except ValueError as exc:
        raise ValidationError(message=str(exc)) from exc
    except Exception as exc:
        raise ValidationError(message=f"连接测试失败: {exc}") from exc


@router.get("/default", response_model=DefaultLLMSelection)
async def get_default_selection():
    return llm_provider_service.get_default_selection()


@router.put("/default", response_model=DefaultLLMSelection)
async def set_default_selection(selection: DefaultLLMSelection):
    try:
        return llm_provider_service.set_default_selection(selection)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="供应商") from exc
