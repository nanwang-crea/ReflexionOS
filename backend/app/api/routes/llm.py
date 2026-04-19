from fastapi import APIRouter, HTTPException

from app.models.llm_config import (
    DefaultLLMSelection,
    ProviderConnectionTestRequest,
    ProviderConnectionTestResult,
    ProviderInstanceConfig,
)
from app.services.agent_service import agent_service

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/providers", response_model=list[ProviderInstanceConfig])
async def list_providers():
    """获取已配置的供应商实例"""
    return agent_service.list_providers()


@router.post("/providers", response_model=ProviderInstanceConfig)
async def create_provider(provider: ProviderInstanceConfig):
    """创建供应商实例"""
    try:
        return agent_service.create_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/providers/{provider_id}", response_model=ProviderInstanceConfig)
async def update_provider(provider_id: str, provider: ProviderInstanceConfig):
    """更新供应商实例"""
    try:
        return agent_service.update_provider(provider_id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    """删除供应商实例"""
    try:
        agent_service.delete_provider(provider_id)
        return {"message": "供应商已删除"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/providers/test", response_model=ProviderConnectionTestResult)
async def test_provider_connection(request: ProviderConnectionTestRequest):
    """测试供应商连接"""
    try:
        return await agent_service.test_provider_connection(
            request.provider,
            request.model_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/default", response_model=DefaultLLMSelection)
async def get_default_selection():
    """获取全局默认供应商与模型"""
    return agent_service.get_default_selection()


@router.put("/default", response_model=DefaultLLMSelection)
async def set_default_selection(selection: DefaultLLMSelection):
    """设置全局默认供应商与模型"""
    try:
        return agent_service.set_default_selection(selection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
