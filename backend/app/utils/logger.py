import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "app",
    log_file: str | None = None,
    level: int = logging.DEBUG
) -> logging.Logger:
    """设置日志器 - 输出到控制台"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if logger.handlers:
        return logger
    
    # 详细格式，包含文件名和行号
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%H:%M:%S"
    )
    
    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if log_file:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_dir / log_file,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "app") -> logging.Logger:
    return logging.getLogger(name)


# 初始化根日志器
root_logger = setup_logger(name="app", level=logging.DEBUG)

# 设置所有 app 模块的日志级别
logging.getLogger("app").setLevel(logging.DEBUG)
logging.getLogger("app.execution").setLevel(logging.DEBUG)
logging.getLogger("app.tools").setLevel(logging.DEBUG)
logging.getLogger("app.llm").setLevel(logging.DEBUG)
logging.getLogger("app.services").setLevel(logging.DEBUG)

# 降低第三方库的日志级别
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

logger = root_logger
