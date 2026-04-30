import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.models.llm_config import LLMSettings


class ExecutionSettings(BaseModel):
    """执行配置"""

    max_steps: int = Field(default=50, ge=1, le=200)
    max_execution_time: int = Field(default=600)  # 10分钟


class MemorySettings(BaseModel):
    """Curated memory 配置（项目级 USER.md / MEMORY.md 存储）"""

    base_dir: str = Field(default_factory=lambda: str(Path.home() / ".reflexion" / "memory"))


class AppSettings(BaseModel):
    """应用总配置"""

    llm: LLMSettings = LLMSettings()
    execution: ExecutionSettings = ExecutionSettings()
    memory: MemorySettings = MemorySettings()


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_dir = Path.home() / ".reflexion"
            config_dir.mkdir(exist_ok=True)
            config_path = str(config_dir / "config.json")

        self.config_path = Path(config_path)
        self.settings = self._load()

    def _load(self) -> AppSettings:
        """加载配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    data = json.load(f)
                    return AppSettings(**data)
            except Exception:
                pass

        return AppSettings()

    def save(self):
        """保存配置"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.settings.model_dump(), f, indent=2, ensure_ascii=False)

    def update_llm(self, llm_settings: LLMSettings):
        """更新 LLM 配置"""
        self.settings.llm = llm_settings
        self.save()


# 全局配置管理器
config_manager = ConfigManager()
