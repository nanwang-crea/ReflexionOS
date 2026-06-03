"""
BrowserSecurityConfig — 浏览器安全策略配置模型。

定义浏览器工具的安全约束参数，包括 URL 黑名单、私有 IP 限制、
允许的协议和最大导航深度。被 BrowserManager 在 URL 校验时使用。

依赖：pydantic
"""

from pydantic import BaseModel, Field


class BrowserSecurityConfig(BaseModel):
    """浏览器安全策略配置。

    用于 BrowserManager._validate_url() 方法，在每次导航前校验目标 URL
    是否符合安全策略。不合规的 URL 将被拒绝并返回错误信息。
    """

    blocked_url_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns for URLs to block",
    )
    block_private_ips: bool = Field(
        default=False,
        description="Block access to private/reserved IP ranges",
    )
    allowed_schemes: list[str] = Field(
        default=["http", "https"],
        description="Allowed URL schemes",
    )
    max_navigation_depth: int = Field(
        default=10,
        description="Max consecutive navigations to prevent redirect loops",
    )
