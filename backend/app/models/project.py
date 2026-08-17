# 项目相关的数据模型：表示一个被 ReflexionOS 管理的代码项目（本地目录）。
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    """项目公共字段：名称、本地路径、主要编程语言（可选）、附加配置。"""

    name: str
    path: str
    language: str | None = None
    config: dict = Field(default_factory=dict)


class ProjectCreate(ProjectBase):
    """创建项目请求：字段与 ProjectBase 一致，不含服务端生成的 id/时间戳。"""

    pass


class Project(ProjectBase):
    """完整的项目模型：在 ProjectBase 基础上附加服务端生成的 id 及创建/更新时间。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=lambda: f"proj-{uuid.uuid4().hex[:8]}")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
