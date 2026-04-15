from fastapi import APIRouter, HTTPException
from typing import List, Optional
from app.models.execution import Execution, ExecutionCreate
from app.services.agent_service import agent_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/execute", response_model=Execution)
async def execute_task(execution: ExecutionCreate):
    """执行任务"""
    try:
        result = await agent_service.execute_task(execution)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{execution_id}", response_model=Execution)
async def get_execution_status(execution_id: str):
    """获取执行状态"""
    execution = agent_service.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行不存在")
    return execution


@router.get("/history/{project_id}", response_model=List[Execution])
async def get_execution_history(project_id: str):
    """获取执行历史"""
    return agent_service.list_executions(project_id)
