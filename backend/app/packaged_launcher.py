# 打包后可执行文件（PyInstaller 等）的启动入口。
# 负责在 frozen 环境下配置 tiktoken 缓存目录、初始化日志，并以 uvicorn 启动 FastAPI 应用。

import logging
import os
import sys

import uvicorn

from app.main import app


def _setup_tiktoken_cache() -> None:
    """在打包（frozen）环境下配置 tiktoken 的本地缓存目录。
    工作流程：仅当 sys.frozen 为 True（即运行于 PyInstaller 等打包产物）时生效，
    在可执行文件同级目录下创建 tiktoken-cache 文件夹，并通过环境变量 TIKTOKEN_CACHE_DIR 指向它，
    避免打包后因无法访问默认缓存路径或联网下载编码文件而报错。
    无参数，无返回值。
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        cache_dir = os.path.join(base, "tiktoken-cache")
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["TIKTOKEN_CACHE_DIR"] = cache_dir


def main() -> None:
    """打包模式下的程序主入口。
    工作流程：配置 tiktoken 缓存 → 确认日志已初始化 → 读取环境变量中的监听地址/端口 → 启动 uvicorn 服务。
    无参数，无返回值（uvicorn.run 阻塞运行直至进程退出）。
    """
    _setup_tiktoken_cache()

    # 打包模式下确认日志系统已初始化（main.py 模块导入时已调用 setup_logging）
    logger = logging.getLogger("app")
    logger.info("ReflexionOS 后端启动 (packaged mode)")

    host = os.environ.get("REFLEXION_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("REFLEXION_BACKEND_PORT", "8000"))

    # log_config=None 让 uvicorn 不覆盖我们已配置的日志 handler
    # 否则 uvicorn 默认会重置 root logger，导致文件日志丢失
    uvicorn.run(app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    main()
