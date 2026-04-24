import json
import logging
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # session_id -> Set[WebSocket]
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """接受新连接"""
        await websocket.accept()

        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()

        self.active_connections[session_id].add(websocket)
        logger.info("WebSocket 连接: session_id=%s", session_id)

    def disconnect(self, websocket: WebSocket, session_id: str):
        """断开连接"""
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)

            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

        logger.info("WebSocket 断开: session_id=%s", session_id)

    async def send_event(self, session_id: str, event_type: str, data: dict):
        """发送事件到所有订阅该会话的客户端"""
        if session_id not in self.active_connections:
            return

        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)

        disconnected = []

        for connection in self.active_connections[session_id]:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error("发送消息失败: %s", e)
                disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn, session_id)


# 全局连接管理器
ws_manager = ConnectionManager()
