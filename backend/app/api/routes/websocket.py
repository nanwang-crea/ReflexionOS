import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.websocket import ws_manager
from app.models.execution import ExecutionCreate
from app.services.agent_service import agent_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/execution/{execution_id}")
async def websocket_execution(websocket: WebSocket, execution_id: str):
    """
    WebSocket 端点 - 单执行流实时通信

    当前只支持一个客户端指令:
    - {"type": "start", "data": {...}} 启动任务，
      data 包含 task、project_id、session_id、provider_id、model_id

    服务端会推送 execution/llm/tool/summary 事件流与最终结果。
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
                    project_id = msg_data.get("project_id", "")
                    session_id = msg_data.get("session_id", "")
                    provider_id = msg_data.get("provider_id")
                    model_id = msg_data.get("model_id")
                    
                    # 创建执行
                    execution_create = ExecutionCreate(
                        project_id=project_id,
                        session_id=session_id,
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

            except json.JSONDecodeError:
                logger.error("无效的 JSON 消息: %s", data)
            except Exception as e:
                logger.error("处理消息失败: %s", e)
                
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, current_execution_id)
        logger.info("WebSocket 断开连接: %s", current_execution_id)
    except Exception as e:
        logger.error("WebSocket 错误: %s", e)
        ws_manager.disconnect(websocket, current_execution_id)
