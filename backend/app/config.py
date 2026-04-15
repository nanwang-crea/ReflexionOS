from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "ReflexionOS"
    app_version: str = "0.1.0"
    debug: bool = False
    
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    
    llm_provider: str = "openai"
    llm_api_key: Optional[str] = "sk-f4a4ff4b0bf242df9bae933c165d5835"
    llm_model: str = "qwen3.6-plus"
    llm_base_url: Optional[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    max_execution_steps: int = 50
    max_file_size: int = 10 * 1024 * 1024
    max_execution_time: int = 600
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
