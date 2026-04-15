from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # execution_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, execution_id: str):
        """接受新连接"""
        await websocket.accept()
        
        if execution_id not in self.active_connections:
            self.active_connections[execution_id] = set()
        
        self.active_connections[execution_id].add(websocket)
        logger.info(f"WebSocket 连接: execution_id={execution_id}")
    
    def disconnect(self, websocket: WebSocket, execution_id: str):
        """断开连接"""
        if execution_id in self.active_connections:
            self.active_connections[execution_id].discard(websocket)
            
            if not self.active_connections[execution_id]:
                del self.active_connections[execution_id]
        
        logger.info(f"WebSocket 断开: execution_id={execution_id}")
    
    async def send_event(self, execution_id: str, event_type: str, data: dict):
        """发送事件到所有订阅该执行的客户端"""
        if execution_id not in self.active_connections:
            return
        
        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)
        
        disconnected = []
        
        for connection in self.active_connections[execution_id]:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn, execution_id)


# 全局连接管理器
ws_manager = ConnectionManager()
