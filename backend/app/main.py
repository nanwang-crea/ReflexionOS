# FastAPI 应用入口：注册所有路由、中间件、全局异常处理器，并管理应用生命周期（插件/技能扫描、Agent 服务启停）。

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    browser_screenshot,
    files,
    git,
    llm,
    plugins,
    projects,
    sessions,
    skills,
    ui_settings,
    upload,
    websocket,
)
from app.app_services import agent_service
from app.config.logging_config import get_log_file_path, setup_logging
from app.errors import AppError

# 初始化集中式日志配置（控制台 + 文件双输出，RotatingFileHandler 自动轮转）
setup_logging(level=logging.INFO)

logger = logging.getLogger("app")


class RequestLoggingMiddleware:
    """
    HTTP 请求日志中间件。
    记录每个请求的方法、路径、响应状态码和耗时（ms）。
    仅处理 HTTP scope，WebSocket 等其他 scope 直接透传。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "?")
        path = scope.get("path", "?")
        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message.get("status", "?")
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.info("%s %s → %s (%dms)", method, path, status_code, elapsed_ms)
            await send(message)

        await self.app(scope, receive, send_wrapper)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    FastAPI 应用生命周期管理。
    启动时：启动 Agent 后台任务，加载本地已缓存的插件（不触发网络操作），扫描技能目录。
    关闭时：关闭 Agent 服务，停止后台任务。
    """
    agent_service.start_background_tasks()

    try:
        from app.config.settings import config_manager
        from app.orchestration.skill_registry import skill_registry

        plugin_settings = config_manager.settings.plugin
        skill_settings = config_manager.settings.skill

        plugin_skill_dirs = []

        if plugin_settings.plugins:
            from app.api.routes.plugins import _get_resolver_and_loader

            # 启动时只加载本地已缓存的插件，不触发任何网络操作（clone/fetch）
            # 用户手动调用 POST /api/plugins/install 或 /update 时才会走 resolve → git clone 的路径
            try:
                resolver, loader = _get_resolver_and_loader()
                plugin_skill_dirs = loader.get_all_skill_dirs()
            except Exception as e:
                logging.getLogger(__name__).exception("Failed to load cached plugins: %s", e)

        if skill_settings.auto_scan:
            skill_registry.scan_all(plugin_skill_dirs=plugin_skill_dirs)

        yield
    finally:
        await agent_service.shutdown()
        await agent_service.stop_background_tasks()


app = FastAPI(
    title="ReflexionOS",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    """
    全局兜底异常处理器。
    捕获所有未被其他 handler 处理的异常，记录完整 traceback 到日志，
    并返回 JSON 格式的 500 响应（包含 detail 和 type 字段），便于前端和调试定位根因。
    """
    import traceback
    logger.error("未捕获异常: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": str(exc), "type": type(exc).__name__})


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    """
    AppError 业务异常处理器。
    将应用层错误映射到对应 HTTP 状态码：
    - not_found → 404
    - security_error → 403
    - 其他 → 400
    """
    status_code = 400
    if exc.code == "not_found":
        status_code = 404
    elif exc.code == "security_error":
        status_code = 403
    return JSONResponse(
        status_code=status_code,
        content=exc.to_dict(),
    )


app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(sessions.router)
app.include_router(llm.router)
app.include_router(skills.router)
app.include_router(plugins.router)
app.include_router(ui_settings.router)
app.include_router(websocket.router)
app.include_router(files.router)
app.include_router(git.router)
app.include_router(browser_screenshot.router)
app.include_router(upload.router)


@app.get("/")
async def root():
    """返回服务基本信息，用于健康探测和版本确认。"""
    return {
        "name": "ReflexionOS",
        "version": "0.1.0",
        "status": "running",
        "features": {"websocket": True, "native_tools": True, "streaming": True},
    }


@app.get("/health")
async def health_check():
    """健康检查端点，供 Electron 主进程探测后端是否就绪。"""
    return {"status": "healthy"}


@app.get("/api/logs/info")
async def logs_info():
    """
    返回日志文件路径和所在目录，便于前端或运维人员定位日志文件。
    输出：log_file（完整路径）、log_dir（所在目录）。
    """
    log_path = get_log_file_path()
    return {
        "log_file": str(log_path) if log_path else None,
        "log_dir": str(log_path.parent) if log_path else None,
    }
