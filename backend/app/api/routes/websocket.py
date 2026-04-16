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
    - {"type": "start", "data": {"task": "...", "project_id": "..."}}  启动任务
    - {"type": "pause"}                                                  暂停任务
    - {"type": "resume"}                                                 恢复任务
    - {"type": "stop"}                                                   停止任务
    
    服务端 → 客户端消息:
    - {"type": "execution:start", "data": {...}, "timestamp": "..."}
    - {"type": "llm:start", "data": {}, "timestamp": "..."}
    - {"type": "llm:content", "data": {"content": "..."}, "timestamp": "..."}
    - {"type": "llm:tool_call", "data": {"tool_name": "...", ...}, "timestamp": "..."}
    - {"type": "tool:start", "data": {...}, "timestamp": "..."}
    - {"type": "tool:result", "data": {...}, "timestamp": "..."}
    - {"type": "summary:start", "data": {}, "timestamp": "..."}
    - {"type": "summary:token", "data": {"token": "..."}, "timestamp": "..."}
    - {"type": "execution:complete", "data": {...}, "timestamp": "..."}
    """
    await ws_manager.connect(websocket, execution_id)
    
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
                    project_id = msg_data.get("project_id", "")
                    
                    # 创建执行
                    execution_create = ExecutionCreate(
                        project_id=project_id,
                        task=task
                    )
                    
                    # 更新 execution_id
                    execution = await agent_service.create_execution(execution_create)
                    
                    # 发送确认
                    await ws_manager.send_event(execution_id, "execution:created", {
                        "execution_id": execution.id,
                        "task": task,
                        "status": "pending"
                    })
                    
                    # 后台运行执行
                    import asyncio
                    asyncio.create_task(agent_service.run_execution(execution.id))
                
                elif msg_type == "pause":
                    # TODO: 实现暂停功能
                    await ws_manager.send_event(execution_id, "execution:paused", {})
                
                elif msg_type == "resume":
                    # TODO: 实现恢复功能
                    await ws_manager.send_event(execution_id, "execution:resumed", {})
                
                elif msg_type == "stop":
                    # TODO: 实现停止功能
                    await ws_manager.send_event(execution_id, "execution:stopped", {})
                    break
                
                elif msg_type == "ping":
                    # 心跳
                    await ws_manager.send_event(execution_id, "pong", {})
                
            except json.JSONDecodeError:
                logger.error(f"无效的 JSON 消息: {data}")
            except Exception as e:
                logger.error(f"处理消息失败: {e}")
                
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, execution_id)
        logger.info(f"WebSocket 断开连接: {execution_id}")
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        ws_manager.disconnect(websocket, execution_id)


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
