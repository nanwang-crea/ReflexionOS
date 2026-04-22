import logging

from app.utils.logger import get_logger, setup_logger


class TestLogger:
    
    def test_setup_logger(self):
        logger = setup_logger("test_logger")
        
        assert logger.name == "test_logger"
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) > 0
    
    def test_get_logger(self):
        logger = get_logger("app")
        
        assert logger.name == "app"
        assert isinstance(logger, logging.Logger)
