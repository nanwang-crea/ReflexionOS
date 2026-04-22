
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "ReflexionOS"
    app_version: str = "0.1.0"
    debug: bool = False
    
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    
    llm_provider: str = "openai"
    # 填入自己的值
    llm_api_key: str | None = "sk-test"
    llm_model: str = "qwen3.6-plus"
    llm_base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    max_execution_steps: int = 50
    max_file_size: int = 10 * 1024 * 1024
    max_execution_time: int = 600
    
settings = Settings()
