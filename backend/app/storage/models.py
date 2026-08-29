"""
文件功能：SQLAlchemy 数据模型定义
文件描述：定义 ReflexionOS 后端全部持久化表结构，覆盖项目/会话/轮次/运行/消息/
    消息搜索索引/会话事件七类实体，是 repositories 层增删改查的直接映射对象。
核心逻辑：使用 SQLAlchemy 2.x 声明式风格（Mapped + mapped_column）定义列；
    通过 session_id 外键 + ondelete="CASCADE" 维护"会话删除时级联清理其下
    轮次/运行/消息/事件"的数据一致性；高频查询字段（如 session_id、status、
    created_at）均建了索引以加速过滤和排序。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """SQLAlchemy 2.x 声明基类"""
    pass


class ProjectModel(Base):
    """
    项目数据模型，对应 projects 表。
    字段说明：
      - id: 项目主键 ID
      - name: 项目名称
      - path: 项目在本地磁盘上的绝对路径，唯一约束防止重复注册同一路径
      - language: 项目主语言（可为空，未识别时为 None）
      - config: 项目级配置，JSON 字典存储，默认空字典
      - created_at / updated_at: 创建时间 / 更新时间，updated_at 在每次
        更新时由数据库自动刷新为当前时间（onupdate=func.now()）
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    language: Mapped[str | None] = mapped_column(String)
    config: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class SessionModel(Base):
    """
    会话数据模型，对应 sessions 表。一个会话归属一个项目（project_id），
    是用户与 Agent 交互的顶层容器，包含多个 Turn（对话轮次）。
    字段说明：
      - id: 会话主键 ID
      - project_id: 所属项目 ID（建索引，按项目筛选会话列表用）
      - title: 会话标题，默认"新建聊天"
      - preferred_provider_id / preferred_model_id: 用户为该会话指定的
        首选模型供应商 / 模型 ID，可为空表示跟随全局默认
      - agent_mode: Agent 运行模式（如 build 等），默认 "build"
      - permission_mode: 权限模式（如自动/手动确认），默认 "auto"
      - last_event_seq: 该会话事件流的最新序号，用于事件增量拉取的游标
      - active_turn_id: 当前正在进行的轮次 ID，可为空表示无活跃轮次
      - created_at / updated_at: 创建 / 更新时间，均建索引以支持按时间排序
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="新建聊天")
    preferred_provider_id: Mapped[str | None] = mapped_column(String)
    preferred_model_id: Mapped[str | None] = mapped_column(String)
    agent_mode: Mapped[str] = mapped_column(String, nullable=False, default="build")
    permission_mode: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    last_event_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_turn_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), index=True)


class TurnModel(Base):
    """
    对话轮次数据模型，对应 turns 表。一个 Turn 代表用户发起的一次完整交互
    请求（可能触发多次 Run 重试），归属某个会话（session_id）。
    字段说明：
      - id: 轮次主键 ID
      - session_id: 所属会话 ID，外键关联 sessions.id，会话删除时级联删除
        该会话下所有轮次（ondelete="CASCADE"）
      - turn_index: 轮次在会话中的序号，从 0 或 1 开始递增
      - root_message_id: 该轮次根消息（通常是用户发出的消息）的 ID
      - status: 轮次状态（如进行中/完成/失败等），建索引用于状态筛选
      - active_run_id: 当前正在进行的运行（Run）ID，可为空
      - created_at / updated_at: 创建 / 更新时间
      - completed_at: 轮次完成时间，未完成时为空
    """

    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    root_message_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    active_run_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class RunModel(Base):
    """
    运行数据模型，对应 runs 表。一个 Run 代表某个 Turn 的一次具体执行尝试
    （同一 Turn 因重试/切换模型等可能产生多个 Run）。
    字段说明：
      - id: 运行主键 ID
      - session_id: 所属会话 ID，外键关联 sessions.id，会话删除时级联删除
      - turn_id: 所属轮次 ID（建索引，按轮次查询其全部运行记录用）
      - attempt_index: 该运行在所属轮次内的尝试序号
      - status: 运行状态（如运行中/成功/失败等），建索引
      - provider_id / model_id: 实际使用的模型供应商 / 模型 ID
      - workspace_ref: 关联的工作区引用标识
      - started_at / finished_at: 开始 / 结束时间，未发生时为空
      - error_code / error_message: 失败时记录的错误码与错误详情文本
    """

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider_id: Mapped[str | None] = mapped_column(String)
    model_id: Mapped[str | None] = mapped_column(String)
    workspace_ref: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    error_code: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)


class MessageModel(Base):
    """
    消息数据模型，对应 messages 表。存储会话中用户/Agent/工具产生的每一条
    消息，是聊天记录的核心数据。
    唯一约束：同一 turn_id 下 turn_message_index 不可重复
    （uq_messages_turn_turn_message_index），保证轮次内消息顺序唯一。
    字段说明：
      - id: 消息主键 ID
      - session_id: 所属会话 ID，外键关联 sessions.id，会话删除时级联删除
      - turn_id: 所属轮次 ID（建索引）
      - run_id: 所属运行 ID，可为空（建索引）
      - turn_message_index: 消息在所属轮次内的顺序号
      - role: 消息角色（如 user/assistant/tool 等）
      - message_type: 消息类型，建索引用于按类型筛选
      - stream_state: 流式生成状态（如流式中/已完成等）
      - display_mode: 前端展示模式
      - content_text: 消息正文文本内容，默认空字符串
      - payload_json: 消息附加结构化数据，JSON 存储，默认空字典
      - attachments_json: 附件信息（JSON 文本），可为空
      - created_at / updated_at: 创建 / 更新时间
      - completed_at: 消息内容生成完成时间，未完成时为空
    """

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "turn_id", "turn_message_index", name="uq_messages_turn_turn_message_index"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True)
    turn_message_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    message_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    stream_state: Mapped[str] = mapped_column(String, nullable=False)
    display_mode: Mapped[str] = mapped_column(String, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    attachments_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class MessageSearchDocumentModel(Base):
    """
    消息搜索索引数据模型，对应 message_search_documents 表。为每条消息
    维护一份用于全文检索的冗余文档（search_text），避免直接对 messages
    表做全文扫描，是消息搜索功能的专用索引表。
    字段说明：
      - message_id: 主键，即对应消息的 ID（一对一映射 MessageModel）
      - session_id: 所属会话 ID，外键关联 sessions.id，会话删除时级联删除
      - turn_id: 所属轮次 ID（建索引）
      - run_id: 所属运行 ID，可为空（建索引）
      - role: 消息角色（建索引，可按角色过滤搜索范围）
      - message_type: 消息类型（建索引）
      - turn_index: 所属轮次的序号（建索引，用于结果排序/定位）
      - turn_message_index: 消息在轮次内的顺序号
      - search_text: 用于全文检索的规范化文本内容，默认空字符串
      - created_at / updated_at: 创建 / 更新时间
    """

    __tablename__ = "message_search_documents"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    turn_message_index: Mapped[int] = mapped_column(Integer, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class ConversationEventModel(Base):
    """
    会话事件数据模型，对应 conversation_events 表。记录会话内发生的各类
    事件（消息新增/状态变更等），供前端按序号增量订阅/回放会话动态。
    唯一约束：同一 session_id 下 seq 不可重复
    （uq_conversation_events_session_seq），保证会话内事件序号严格唯一。
    字段说明：
      - id: 事件主键 ID
      - session_id: 所属会话 ID，外键关联 sessions.id，会话删除时级联删除
      - seq: 事件在所属会话内的序号，单调递增，对应
        SessionModel.last_event_seq 的取值来源
      - turn_id / run_id / message_id: 事件关联的轮次 / 运行 / 消息 ID，
        均可为空（建索引，用于按关联对象反查事件）
      - event_type: 事件类型
      - payload_json: 事件的结构化载荷数据，JSON 存储，默认空字典
      - created_at: 事件创建时间
    """

    __tablename__ = "conversation_events"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_conversation_events_session_seq"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_id: Mapped[str | None] = mapped_column(String, index=True)
    run_id: Mapped[str | None] = mapped_column(String, index=True)
    message_id: Mapped[str | None] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
