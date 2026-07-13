"""服务包导出入口。

文件功能：服务模块的懒加载导出
文件描述：避免在导入 app.services 子模块时提前加载所有服务，降低循环导入风险。
核心逻辑：通过 __getattr__ 按需导入具体服务类和全局实例，保持外部 from app.services import X 的兼容性。
"""

__all__ = [
    "ConversationProjection",
    "ConversationService",
    "conversation_service",
    "LLMProviderService",
    "llm_provider_service",
    "SessionCreate",
    "SessionService",
    "SessionUpdate",
    "session_service",
]


def __getattr__(name: str):
    """按需导入服务对象，避免包初始化阶段产生循环依赖。

    函数名：__getattr__
    入参：
      - name (str): 外部请求的导出名称
    功能：在访问 app.services.<name> 时懒加载对应服务模块。
    运行逻辑：
      1. 根据名称分派到真实服务模块。
      2. 只导入被请求的对象，避免导入 message_repo 时反向加载 conversation_projection。
      3. 未知名称抛 AttributeError，符合 Python 模块级 __getattr__ 语义。
    出参：object - 被请求的服务类或全局实例
    """
    if name == "ConversationProjection":
        from app.services.conversation_projection import ConversationProjection

        return ConversationProjection
    if name in {"ConversationService", "conversation_service"}:
        from app.services.conversation_service import ConversationService, conversation_service

        return {
            "ConversationService": ConversationService,
            "conversation_service": conversation_service,
        }[name]
    if name in {"LLMProviderService", "llm_provider_service"}:
        from app.services.llm_provider_service import LLMProviderService, llm_provider_service

        return {
            "LLMProviderService": LLMProviderService,
            "llm_provider_service": llm_provider_service,
        }[name]
    if name in {"SessionCreate", "SessionService", "SessionUpdate", "session_service"}:
        from app.services.session_service import (
            SessionCreate,
            SessionService,
            SessionUpdate,
            session_service,
        )

        return {
            "SessionCreate": SessionCreate,
            "SessionService": SessionService,
            "SessionUpdate": SessionUpdate,
            "session_service": session_service,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
