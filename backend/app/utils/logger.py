import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from app.config import settings


def setup_logger(
    name: str = "reflexion",
    log_file: Optional[str] = None,
    level: int = logging.INFO
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
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


def get_logger(name: str = "reflexion") -> logging.Logger:
    return logging.getLogger(name)


logger = setup_logger(
    name="reflexion",
    log_file=f"reflexion-{datetime.now().strftime('%Y%m%d')}.log" if not settings.debug else None,
    level=logging.DEBUG if settings.debug else logging.INFO
)
