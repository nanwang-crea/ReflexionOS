"""
websocket_manager — WebSocket 连接管理与消息发送的公共工具模块。

提供统一的 JSON 序列化函数、WebSocket 消息发送函数，以及按 session_id
分组管理连接的 ConnectionManager，供各路由模块广播事件到前端。
"""

import json
import logging
from datetime import datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def json_dumps(data: object) -> str:
    """
    入参：data - 待序列化的任意对象
    功能：统一的 JSON 序列化，处理 datetime 等非标准类型
    出参：str - JSON 字符串（非 ASCII 转义，遇 datetime 等类型走 _json_default）
    """
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _json_default(obj: object) -> str:
    """
    入参：obj - json.dumps 无法直接序列化的对象
    功能：json.dumps 的 default 回调，负责把 datetime 转成 ISO 字符串
    出参：str - 转换后的字符串；若类型不支持则抛出 TypeError
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def send_ws_json(websocket: WebSocket, data: object) -> None:
    """
    入参：websocket - 目标 WebSocket 连接；data - 待发送的数据对象
    功能：统一的 WebSocket JSON 发送，所有 WebSocket 消息都应走这个函数
    出参：无，直接通过 websocket.send_text 发出序列化后的 JSON
    """
    await websocket.send_text(json_dumps(data))


class ConnectionManager:
    """WebSocket 连接管理器，按 session_id 分组维护多个客户端连接"""

    def __init__(self):
        """初始化连接表：session_id -> Set[WebSocket]"""
        # session_id -> Set[WebSocket]
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """
        入参：websocket - 新建立的 WebSocket 连接；session_id - 所属会话 ID
        功能：接受新连接，并将其加入对应 session_id 的连接集合
        出参：无
        """
        await websocket.accept()

        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()

        self.active_connections[session_id].add(websocket)
        logger.info("WebSocket 连接: session_id=%s", session_id)

    def disconnect(self, websocket: WebSocket, session_id: str):
        """
        入参：websocket - 要移除的连接；session_id - 所属会话 ID
        功能：断开连接，从连接集合中移除；若该会话已无连接则清空对应条目
        出参：无
        """
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)

            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

        logger.info("WebSocket 断开: session_id=%s", session_id)

    async def send_event(self, session_id: str, event_type: str, data: dict):
        """
        入参：session_id - 目标会话 ID；event_type - 事件类型标识；data - 事件负载数据
        功能：发送事件到所有订阅该会话的客户端，并清理发送失败（已断开）的连接
        运行逻辑：
            1. 若该 session_id 无任何连接，直接返回
            2. 组装带 type/data/timestamp 的消息并序列化
            3. 遍历该会话的所有连接逐个发送，发送异常的记入待清理列表
            4. 发送完成后统一断开清理失败的连接
        出参：无
        """
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
