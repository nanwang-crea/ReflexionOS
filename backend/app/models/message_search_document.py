# 消息搜索索引文档模型：用于全文检索（如消息历史搜索）场景下的搜索引擎/索引存储结构，
# 与数据库中的 Message 记录对应，但只保留检索所需字段。
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageSearchDocument(BaseModel):
    """消息搜索索引文档：对应一条消息的可检索表示，包含消息在会话/回合/运行中的定位信息
    及用于全文搜索的文本内容（search_text）。"""

    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    turn_id: str
    run_id: str | None = None
    role: str
    message_type: str
    turn_index: int  # 消息所属回合在会话中的序号
    turn_message_index: int  # 消息在所属回合内的序号
    search_text: str = ""  # 用于全文检索的纯文本内容
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
