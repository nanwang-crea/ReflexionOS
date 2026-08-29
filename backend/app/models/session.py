# 会话（Session）相关数据模型：一个会话归属于某个项目，承载多轮对话（Turn），
# 并记录当前使用的模型偏好、Agent 模式与权限模式等状态。
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_SESSION_TITLE = "新建聊天"


class SessionCreate(BaseModel):
    """创建会话请求：标题及首选服务商/模型均可选，不填则使用默认值。"""

    title: str | None = None
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None


class SessionUpdate(BaseModel):
    """更新会话请求：支持部分更新标题、首选服务商/模型、Agent 模式及权限模式。"""

    title: str | None = None
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None
    agent_mode: str | None = None
    permission_mode: str | None = None

    @field_validator("permission_mode")
    @classmethod
    def validate_permission_mode(cls, v: str | None) -> str | None:
        """校验 permission_mode 取值必须是 ask/auto/yolo 之一（或 None 表示不更新），
        否则抛出 ValueError。"""
        if v is not None and v not in ("ask", "auto", "yolo"):
            raise ValueError(f"permission_mode 必须是 'ask'、'auto' 或 'yolo'，收到: {v}")
        return v


class Session(BaseModel):
    """会话：归属于某个项目的一次持续对话，记录标题、模型偏好、Agent 模式、
    权限模式（ask/auto/yolo）、事件序号游标及当前活跃回合。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str = DEFAULT_SESSION_TITLE
    preferred_provider_id: str | None = None
    preferred_model_id: str | None = None
    agent_mode: str = "build"
    permission_mode: str = "auto"
    last_event_seq: int = 0  # 已产生的最新事件序号，用于事件流增量同步
    active_turn_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def default_updated_at_to_created_at(self):
        """若未显式提供 updated_at，则默认使用 created_at 填充，
        保证该字段始终有值，避免下游处理时需要额外判空。"""
        if self.updated_at is None:
            self.updated_at = self.created_at
        return self
