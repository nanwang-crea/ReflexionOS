"""
集中式日志配置

- 开发模式 & 打包模式统一将日志写入 ~/.reflexion/logs/reflexion.log
- 使用 RotatingFileHandler 限制日志大小和数量
- 同时保留控制台输出（StreamHandler）
- 跨平台兼容（macOS / Windows / Linux）
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ---------- 日志参数 ----------
_LOG_DIR_NAME = "logs"
_LOG_FILE_NAME = "reflexion.log"
_MAX_BYTES = 10 * 1024 * 1024  # 单个日志文件最大 10MB
_BACKUP_COUNT = 5  # 保留 5 个轮转备份
_CONSOLE_FORMAT = "%(levelname)s:     %(message)s"
_FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _resolve_log_dir() -> Path:
    """
    解析日志目录路径，优先使用环境变量，否则使用 ~/.reflexion/logs

    环境变量 REFLEXION_LOG_DIR 可覆盖默认路径（便于调试或打包场景指定）
    """
    env_dir = os.environ.get("REFLEXION_LOG_DIR")
    if env_dir:
        return Path(env_dir)

    return Path.home() / ".reflexion" / _LOG_DIR_NAME


def setup_logging(level: int = logging.INFO) -> None:
    """
    配置应用日志系统

    - 为 "app" logger 配置控制台 + 文件双输出
    - 文件日志使用 RotatingFileHandler，自动轮转
    - 同时配置 root logger 确保第三方库日志也能写入文件
    - 幂等：重复调用不会重复添加 handler
    """
    log_dir = _resolve_log_dir()

    # 创建日志目录（忽略已存在的情况，跨平台兼容）
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # 如果无法创建日志目录（例如权限问题），仅使用控制台日志
        print(
            f"[ReflexionOS] 警告: 无法创建日志目录 {log_dir}，仅使用控制台日志",
            file=sys.stderr,
        )
        _setup_console_only(level)
        return

    log_file = log_dir / _LOG_FILE_NAME

    # ---- 文件 Handler ----
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter(_FILE_FORMAT, datefmt=_FILE_DATE_FORMAT)
        )
        file_handler.setLevel(level)
    except OSError as exc:
        # 文件创建失败时降级为仅控制台
        print(
            f"[ReflexionOS] 警告: 无法创建日志文件 {log_file}: {exc}，仅使用控制台日志",
            file=sys.stderr,
        )
        _setup_console_only(level)
        return

    # ---- 控制台 Handler ----
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    console_handler.setLevel(level)

    # ---- 配置 "app" logger ----
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    app_logger.propagate = False  # 避免重复输出到 root

    # 幂等检查：避免重复添加 handler
    _remove_existing_handlers(app_logger)
    app_logger.addHandler(console_handler)
    app_logger.addHandler(file_handler)

    # ---- 配置 root logger ----
    # 确保第三方库（uvicorn、sqlalchemy 等）的日志也能写入文件
    root_logger = logging.getLogger()
    root_logger.setLevel(max(level, logging.WARNING))  # root 至少 WARNING
    _remove_existing_handlers(root_logger)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # ---- 配置 uvicorn logger ----
    # uvicorn 有自己的 logger，需要单独配置才能写入文件
    for uvicorn_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(uvicorn_name)
        uv_logger.setLevel(level)
        uv_logger.propagate = False
        _remove_existing_handlers(uv_logger)
        uv_logger.addHandler(console_handler)
        uv_logger.addHandler(file_handler)

    app_logger.info("日志系统初始化完成，日志文件: %s", log_file)


def _setup_console_only(level: int) -> None:
    """降级方案：仅使用控制台日志"""
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    console_handler.setLevel(level)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    app_logger.propagate = False
    _remove_existing_handlers(app_logger)
    app_logger.addHandler(console_handler)

    root_logger = logging.getLogger()
    root_logger.setLevel(max(level, logging.WARNING))
    _remove_existing_handlers(root_logger)
    root_logger.addHandler(console_handler)


def _remove_existing_handlers(logger: logging.Logger) -> None:
    """移除 logger 上所有现有 handler，避免重复添加"""
    # 复制列表避免在迭代时修改
    for handler in list(logger.handlers):
        # 先关闭文件 handler 释放文件句柄
        if isinstance(handler, (RotatingFileHandler, logging.FileHandler)):
            handler.close()
        logger.removeHandler(handler)


def get_log_file_path() -> Path | None:
    """返回当前日志文件路径，供前端或 API 查询"""
    log_dir = _resolve_log_dir()
    log_file = log_dir / _LOG_FILE_NAME
    return log_file if log_file.parent.exists() else None
