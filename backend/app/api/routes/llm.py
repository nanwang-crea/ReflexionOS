# 文件功能：LLM 供应商配置相关的 API 路由
# 文件描述：管理大模型供应商实例的增删改查、连接测试，以及默认模型选择的读写；
#           实际逻辑委托给 llm_provider_service。
# 核心逻辑：路由层只做参数透传和异常转换，ValueError 转为标准应用错误
#           （资源标记为"供应商"），连接测试单独捕获异常并转为 ValidationError。
from fastapi import APIRouter

from app.errors import ValidationError, value_error_to_app_error
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
    """
    GET /api/llm/providers：获取所有已配置的 LLM 供应商实例列表。
    入参：无。
    逻辑：直接调用 llm_provider_service.list_providers 读取配置。
    出参：list[ProviderInstanceConfig]（供应商配置列表）。
    """
    return llm_provider_service.list_providers()


@router.post("/providers", response_model=ProviderInstanceConfig)
async def create_provider(provider: ProviderInstanceConfig):
    """
    POST /api/llm/providers：新增一个 LLM 供应商实例配置。
    入参：provider（请求体，供应商配置信息）。
    逻辑：调用 llm_provider_service.create_provider 创建并持久化配置。
    出参：ProviderInstanceConfig（创建后的供应商配置）。
    """
    try:
        return llm_provider_service.create_provider(provider)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="供应商") from exc


@router.put("/providers/{provider_id}", response_model=ProviderInstanceConfig)
async def update_provider(provider_id: str, provider: ProviderInstanceConfig):
    """
    PUT /api/llm/providers/{provider_id}：更新指定供应商实例的配置。
    入参：provider_id（路径参数，供应商 ID）；provider（请求体，新的配置信息）。
    逻辑：调用 llm_provider_service.update_provider 覆盖更新配置。
    出参：ProviderInstanceConfig（更新后的供应商配置）。
    """
    try:
        return llm_provider_service.update_provider(provider_id, provider)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="供应商") from exc


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    """
    DELETE /api/llm/providers/{provider_id}：删除指定的供应商实例。
    入参：provider_id（路径参数，供应商 ID）。
    逻辑：调用 llm_provider_service.delete_provider 删除配置。
    出参：dict，包含删除成功提示信息 message。
    """
    try:
        llm_provider_service.delete_provider(provider_id)
        return {"message": "供应商已删除"}
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="供应商") from exc


@router.post("/providers/test", response_model=ProviderConnectionTestResult)
async def test_provider_connection(request: ProviderConnectionTestRequest):
    """
    POST /api/llm/providers/test：测试供应商配置的连通性。
    入参：request（含供应商配置 provider 和待测试的模型 ID model_id）。
    逻辑：调用 llm_provider_service.test_provider_connection 发起实际连接测试；
          ValueError 转为参数校验错误，其他异常统一包装为"连接测试失败"提示。
    出参：ProviderConnectionTestResult（连接测试结果）。
    """
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
    """
    GET /api/llm/default：获取当前默认使用的 LLM 供应商/模型选择。
    入参：无。
    逻辑：直接调用 llm_provider_service.get_default_selection 读取默认配置。
    出参：DefaultLLMSelection（默认供应商与模型信息）。
    """
    return llm_provider_service.get_default_selection()


@router.put("/default", response_model=DefaultLLMSelection)
async def set_default_selection(selection: DefaultLLMSelection):
    """
    PUT /api/llm/default：设置默认使用的 LLM 供应商/模型。
    入参：selection（请求体，指定的默认供应商与模型）。
    逻辑：调用 llm_provider_service.set_default_selection 保存默认选择。
    出参：DefaultLLMSelection（设置后的默认选择）。
    """
    try:
        return llm_provider_service.set_default_selection(selection)
    except ValueError as exc:
        raise value_error_to_app_error(exc, resource="供应商") from exc
