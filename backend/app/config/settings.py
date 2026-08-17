"""
应用配置模块

- 定义各功能模块的配置模型（执行、子代理、记忆、UI、技能、插件、浏览器等）
- ConfigManager 负责配置的加载、保存与更新，配置文件默认存储于 ~/.reflexion/config.json
- 模块级 config_manager 通过 __getattr__ 懒加载，避免导入时提前实例化
"""

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
    # 同一批连续 delegate 调用的最大并发数
    max_concurrent: int = Field(default=3, ge=1, le=20)


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
        """
        初始化配置管理器

        参数：
            config_path: 配置文件路径，为 None 时默认使用 ~/.reflexion/config.json
        逻辑：确保配置目录存在，并立即从磁盘加载配置到 self.settings
        """
        if config_path is None:
            config_dir = Path.home() / ".reflexion"
            config_dir.mkdir(exist_ok=True)
            config_path = str(config_dir / "config.json")

        self.config_path = Path(config_path)
        self.settings = self._load()

    def _load(self) -> AppSettings:
        """
        从 config_path 加载配置文件并解析为 AppSettings

        返回：解析成功时返回对应的 AppSettings 实例；文件不存在、JSON 损坏、
        字段校验失败或其他异常时，均降级返回默认的 AppSettings()
        """
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
        """将当前 self.settings 序列化为 JSON 并写入 config_path（无返回值）"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.settings.model_dump(), f, indent=2, ensure_ascii=False)

    def update_llm(self, llm_settings: LLMSettings):
        """参数：llm_settings 新的 LLM 配置；替换 self.settings.llm 并立即持久化，无返回值"""
        self.settings.llm = llm_settings
        self.save()

    def update_ui(self, ui_settings: UISettings):
        """参数：ui_settings 新的 UI 偏好配置；替换 self.settings.ui 并立即持久化，无返回值"""
        self.settings.ui = ui_settings
        self.save()

    def update_browser(self, browser_settings: BrowserSettings):
        """参数：browser_settings 新的浏览器配置；替换 self.settings.browser 并立即持久化，无返回值"""
        self.settings.browser = browser_settings
        self.save()


# 全局配置管理器（延迟初始化）
# 使用 PEP 562 __getattr__ 实现懒加载，测试时可通过 _config_manager 注入 mock
_config_manager = None


def __getattr__(name):
    """
    模块级属性懒加载钩子（PEP 562）

    参数：name 被访问的模块属性名
    逻辑：当访问 app.config.settings.config_manager 时，首次访问触发 ConfigManager()
    实例化并缓存到全局变量 _config_manager，之后直接复用；其他属性名一律抛错
    返回：name 为 "config_manager" 时返回全局单例 ConfigManager 实例
    """
    global _config_manager
    if name == "config_manager":
        if _config_manager is None:
            _config_manager = ConfigManager()
        return _config_manager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
