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
    monitoring,
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
    agent_service.start_background_tasks()
    from app.app_services import monitoring_alert_dispatcher, observability_collector

    observability_collector.start_background_tasks()
    monitoring_alert_dispatcher.start_background_tasks()

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
        await monitoring_alert_dispatcher.stop_background_tasks()
        await observability_collector.stop_background_tasks()
        await agent_service.shutdown()
        await agent_service.stop_background_tasks()


app = FastAPI(
    title="ReflexionOS",
    version="0.1.0",
    lifespan=lifespan,
)

@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
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
app.include_router(monitoring.router)
app.include_router(files.router)
app.include_router(git.router)
app.include_router(browser_screenshot.router)
app.include_router(upload.router)


@app.get("/")
async def root():
    return {
        "name": "ReflexionOS",
        "version": "0.1.0",
        "status": "running",
        "features": {"websocket": True, "native_tools": True, "streaming": True},
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/api/logs/info")
async def logs_info():
    """返回日志文件路径和配置信息，方便前端定位日志"""
    log_path = get_log_file_path()
    return {
        "log_file": str(log_path) if log_path else None,
        "log_dir": str(log_path.parent) if log_path else None,
    }
