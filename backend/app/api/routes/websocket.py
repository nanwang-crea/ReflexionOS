from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.websocket import ws_manager
from app.services.agent_service import agent_service
from app.models.execution import ExecutionCreate
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/execution/{execution_id}")
async def websocket_execution(websocket: WebSocket, execution_id: str):
    """
    WebSocket 端点 - 执行任务实时通信
    
    客户端 → 服务端消息:
    - {"type": "start", "data": {"task": "...", "project_path": "...", "provider_id": "...", "model_id": "..."}}  启动任务
    - {"type": "cancel"}                                                 取消任务
    - {"type": "stop"}                                                   兼容旧端的取消任务
    
    服务端 → 客户端消息:
    - {"type": "execution:start", "data": {...}, "timestamp": "..."}
    - {"type": "llm:start", "data": {}, "timestamp": "..."}
    - {"type": "llm:content", "data": {"content": "..."}, "timestamp": "..."}
    - {"type": "llm:thought", "data": {"content": "..."}, "timestamp": "..."}
    - {"type": "llm:tool_call", "data": {"tool_name": "...", ...}, "timestamp": "..."}
    - {"type": "tool:start", "data": {...}, "timestamp": "..."}
    - {"type": "tool:result", "data": {...}, "timestamp": "..."}
    - {"type": "summary:start", "data": {}, "timestamp": "..."}
    - {"type": "summary:token", "data": {"token": "..."}, "timestamp": "..."}
    - {"type": "execution:cancelled", "data": {...}, "timestamp": "..."}
    - {"type": "execution:complete", "data": {...}, "timestamp": "..."}
    """
    current_execution_id = execution_id
    await ws_manager.connect(websocket, current_execution_id)
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                msg_data = message.get("data", {})
                
                if msg_type == "start":
                    # 启动任务
                    task = msg_data.get("task", "")
                    project_path = msg_data.get("project_path") or msg_data.get("project_id", "")
                    provider_id = msg_data.get("provider_id")
                    model_id = msg_data.get("model_id")
                    
                    # 创建执行
                    execution_create = ExecutionCreate(
                        project_id=project_path,
                        task=task,
                        provider_id=provider_id,
                        model_id=model_id,
                    )
                    
                    # 更新 execution_id
                    execution = await agent_service.create_execution(execution_create)
                    ws_manager.move_connection(
                        websocket,
                        current_execution_id,
                        execution.id
                    )
                    current_execution_id = execution.id
                    
                    # 发送确认
                    await ws_manager.send_event(current_execution_id, "execution:created", {
                        "execution_id": execution.id,
                        "task": task,
                        "status": "pending"
                    })
                    
                    # 后台运行执行
                    agent_service.schedule_execution(execution.id)
                
                elif msg_type in {"cancel", "stop"}:
                    await agent_service.cancel_execution(current_execution_id)
                
                elif msg_type == "ping":
                    # 心跳
                    await ws_manager.send_event(current_execution_id, "pong", {})
                
            except json.JSONDecodeError:
                logger.error(f"无效的 JSON 消息: {data}")
            except Exception as e:
                logger.error(f"处理消息失败: {e}")
                
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, current_execution_id)
        logger.info(f"WebSocket 断开连接: {current_execution_id}")
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        ws_manager.disconnect(websocket, current_execution_id)


@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """
    WebSocket 端点 - 全局状态
    
    用于获取系统状态、执行列表等
    """
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                
                if msg_type == "get_executions":
                    # 获取执行列表
                    executions = agent_service.list_executions()
                    await websocket.send_json({
                        "type": "executions",
                        "data": {
                            "executions": [
                                {
                                    "id": e.id,
                                    "task": e.task,
                                    "status": e.status.value,
                                    "steps_count": len(e.steps)
                                }
                                for e in executions
                            ]
                        }
                    })
                
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        logger.info("状态 WebSocket 断开")
