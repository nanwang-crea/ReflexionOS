import json
import logging
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def json_dumps(data: object) -> str:
    """统一的 JSON 序列化，处理 datetime 等非标准类型"""
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def send_ws_json(websocket: WebSocket, data: object) -> None:
    """统一的 WebSocket JSON 发送，所有 WebSocket 消息都应走这个函数"""
    await websocket.send_text(json_dumps(data))


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

        message = json_dumps(
            {"type": event_type, "data": data, "timestamp": datetime.now().isoformat()},
        )

        disconnected = []

        for connection in list(self.active_connections[session_id]):
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
