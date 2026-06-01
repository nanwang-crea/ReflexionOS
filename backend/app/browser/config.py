from pydantic import BaseModel, Field


class BrowserSecurityConfig(BaseModel):
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
