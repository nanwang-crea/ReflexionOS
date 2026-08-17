"""应用级服务单例（延迟初始化）

使用 PEP 562 __getattr__ 实现懒加载，避免模块导入时立即创建实例。
现有 `from app.app_services import agent_service` 写法无需修改。
测试时可通过 `app.app_services._agent_service = mock` 注入替换。
"""

import asyncio

_agent_service = None
_conversation_broadcaster = None
_init_lock = asyncio.Lock()


def _get_conversation_broadcaster():
    """懒加载获取会话广播器单例（WebSocketConversationBroadcaster）。
    首次调用时基于 ws_manager 创建实例并缓存到模块级变量，后续直接复用。
    返回：WebSocketConversationBroadcaster 实例。
    """
    global _conversation_broadcaster

    if _conversation_broadcaster is None:
        from app.api.websocket_manager import ws_manager
        from app.services.conversation_broadcaster import WebSocketConversationBroadcaster
        _conversation_broadcaster = WebSocketConversationBroadcaster(ws_manager)
    return _conversation_broadcaster


async def _get_agent_service_async():
    """异步方式懒加载获取 AgentService 单例，使用 _init_lock 避免并发初始化的竞态问题。
    工作流程：若已初始化直接返回；否则加锁后二次检查（double-checked locking）再创建实例。
    返回：AgentService 实例。
    """
    global _agent_service

    if _agent_service is not None:
        return _agent_service

    async with _init_lock:
        if _agent_service is None:
            from app.services.agent_service import AgentService
            _agent_service = AgentService(conversation_broadcaster=_get_conversation_broadcaster())
        return _agent_service


def __getattr__(name):
    """模块级属性访问钩子（PEP 562），支持 `from app.app_services import agent_service` 写法。
    仅限模块级导入使用；运行时动态访问请走 _get_agent_service_async()，以避免异步竞态。
    参数：name 被访问的属性名（"agent_service" 或 "conversation_broadcaster"）。
    返回：对应的单例对象；若属性名不识别则抛出 AttributeError。
    """
    global _agent_service, _conversation_broadcaster

    if name == "conversation_broadcaster":
        return _get_conversation_broadcaster()

    if name == "agent_service":
        if _agent_service is None:
            from app.services.agent_service import AgentService
            _agent_service = AgentService(conversation_broadcaster=_get_conversation_broadcaster())
        return _agent_service

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
