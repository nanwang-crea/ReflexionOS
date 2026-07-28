import logging
import os
import sys

import uvicorn

from app.main import app


def _setup_tiktoken_cache() -> None:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        cache_dir = os.path.join(base, "tiktoken-cache")
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["TIKTOKEN_CACHE_DIR"] = cache_dir


def main() -> None:
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
