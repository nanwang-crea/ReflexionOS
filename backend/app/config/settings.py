import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.models.llm_config import LLMSettings


class ExecutionSettings(BaseModel):
    """执行配置"""

    max_steps: int = Field(default=1000, ge=1, le=1000)
    max_execution_time: int = Field(default=600)
    # Tier 2: 超出窗口的旧消息逐条截断但始终可见（tool output 截断至 tool_output_max_chars）
    tier2_truncate_threshold_tokens: int = Field(default=50_000, ge=1)
    # Tier 3: Tier 2 之后仍超限，将旧消息经 LLM 压缩为摘要（不可逆，但可 session_recall 回溯）
    tier3_compact_threshold_tokens: int = Field(default=100_000, ge=1)
    # Tier 2 中 tool output 的最大字符数，超出部分 head+tail 截断并标记 [可 session_recall 取回]
    tool_output_max_chars: int = Field(default=2_400, ge=100)


class MemorySettings(BaseModel):
    """Curated memory 配置（项目级 USER.md / MEMORY.md 存储）"""

    base_dir: str = Field(default_factory=lambda: str(Path.home() / ".reflexion" / "memory"))


class UISettings(BaseModel):
    """UI 偏好配置"""

    show_continuation_notices: bool = False


class AppSettings(BaseModel):
    """应用总配置"""

    llm: LLMSettings = LLMSettings()
    execution: ExecutionSettings = ExecutionSettings()
    memory: MemorySettings = MemorySettings()
    ui: UISettings = UISettings()


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

    def update_ui(self, ui_settings: UISettings):
        """更新 UI 偏好配置"""
        self.settings.ui = ui_settings
        self.save()

    def should_show_continuation_notices(self) -> bool:
        """查询是否显示延续摘要通知"""
        return self.settings.ui.show_continuation_notices


# 全局配置管理器
config_manager = ConfigManager()
