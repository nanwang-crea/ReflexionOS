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
    """Curated memory 配置（项目级 memory.md 存储路径）"""

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


class SubAgentSettings(BaseModel):
    """子代理配置"""

    # 子代理单次委托的最大执行步数
    max_steps: int = Field(default=100, ge=1, le=500)


class UISettings(BaseModel):
    """UI 偏好配置"""

    show_process_expanded: bool = True
    auto_collapse_process: bool = True


class BrowserSettings(BaseModel):
    """浏览器配置"""

    headless: bool = False
    browser_engine: str = "chromium"
    default_timeout: int = 30000
    action_timeout: int = 5000
    default_wait_until: str = "load"
    block_private_ips: bool = False
    blocked_url_patterns: list[str] = Field(default_factory=list)
    allowed_schemes: list[str] = Field(default=["http", "https"])


class AppSettings(BaseModel):
    """应用总配置"""

    llm: LLMSettings = LLMSettings()
    execution: ExecutionSettings = ExecutionSettings()
    subagent: SubAgentSettings = Field(default_factory=SubAgentSettings)
    memory: MemorySettings = MemorySettings()
    ui: UISettings = UISettings()
    skill: SkillSettings = SkillSettings()
    plugin: PluginSettings = PluginSettings()
    browser: BrowserSettings = Field(default_factory=BrowserSettings)


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

    def update_browser(self, browser_settings: BrowserSettings):
        """更新浏览器配置"""
        self.settings.browser = browser_settings
        self.save()


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
