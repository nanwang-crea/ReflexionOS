import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.models.llm_config import LLMSettings

logger = logging.getLogger(__name__)


class ExecutionSettings(BaseModel):
    """执行配置"""

    max_steps: int = Field(default=1000, ge=1, le=1000)
    max_execution_time: int = Field(default=600)
    # 预留的输出 token buffer，usable = context_window - compaction_buffer
    compaction_buffer: int = Field(default=20_000, ge=1_000)
    # Tier 2 触发比例：usable * tier2_ratio
    tier2_ratio: float = Field(default=0.5, ge=0.1, le=1.0)
    # Tier 3 触发比例：usable * tier3_ratio
    tier3_ratio: float = Field(default=0.85, ge=0.1, le=1.0)
    # Tier 2 中 tool output 的最大字符数，超出部分 head+tail 截断并标记 [可 session_recall 取回]
    tool_output_max_chars: int = Field(default=2_400, ge=100)
    # Pruning: 保护的最近消息分组数
    prune_protect_groups: int = Field(default=2, ge=1)
    # Pruning: 最少回收 token 数才触发
    prune_minimum_recovery_tokens: int = Field(default=20_000, ge=1_000)


class MemorySettings(BaseModel):
    """Curated memory 配置（项目级 USER.md / MEMORY.md 存储）"""

    base_dir: str = Field(default_factory=lambda: str(Path.home() / ".reflexion" / "memory"))


class SkillSettings(BaseModel):
    """技能配置"""

    scan_dirs: list[str] = Field(default_factory=list)
    auto_scan: bool = True
    install_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".reflexion" / "skills")
    )
    compat_dirs: list[str] = Field(
        default_factory=lambda: [
            str(Path.home() / ".agents" / "skills"),
        ]
    )


class PluginSettings(BaseModel):
    """插件配置"""

    plugins: list[str] = Field(default_factory=list)
    package_cache_dir: str = Field(
        default_factory=lambda: str(Path.home() / ".reflexion" / "packages")
    )
    auto_update: bool = False


class UISettings(BaseModel):
    """UI 偏好配置"""

    show_continuation_notices: bool = False


class AppSettings(BaseModel):
    """应用总配置"""

    llm: LLMSettings = LLMSettings()
    execution: ExecutionSettings = ExecutionSettings()
    memory: MemorySettings = MemorySettings()
    ui: UISettings = UISettings()
    skill: SkillSettings = SkillSettings()
    plugin: PluginSettings = PluginSettings()


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
            except json.JSONDecodeError:
                logger.warning("配置文件 JSON 格式损坏，使用默认值: %s", self.config_path)
            except ValidationError:
                logger.warning("配置文件内容校验失败，使用默认值: %s", self.config_path)
            except Exception:
                logger.warning("配置文件加载异常，使用默认值: %s", self.config_path, exc_info=True)

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


# 全局配置管理器（延迟初始化）
# 使用 PEP 562 __getattr__ 实现懒加载，测试时可通过 _config_manager 注入 mock
_config_manager = None


def __getattr__(name):
    global _config_manager
    if name == "config_manager":
        if _config_manager is None:
            _config_manager = ConfigManager()
        return _config_manager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
