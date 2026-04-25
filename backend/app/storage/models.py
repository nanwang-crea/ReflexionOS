from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ProjectModel(Base):
    """项目数据模型"""
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True)
    language = Column(String)
    config = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SessionModel(Base):
    """会话数据模型"""
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, default="新建聊天")
    preferred_provider_id = Column(String)
    preferred_model_id = Column(String)
    last_event_seq = Column(Integer, nullable=False, default=0)
    active_turn_id = Column(String)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)


class TurnModel(Base):
    __tablename__ = "turns"

    id = Column(String, primary_key=True)
    session_id = Column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index = Column(Integer, nullable=False)
    root_message_id = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    active_run_id = Column(String)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    completed_at = Column(DateTime)


class RunModel(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True)
    session_id = Column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id = Column(String, nullable=False, index=True)
    attempt_index = Column(Integer, nullable=False)
    status = Column(String, nullable=False, index=True)
    provider_id = Column(String)
    model_id = Column(String)
    workspace_ref = Column(String)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    error_code = Column(String)
    error_message = Column(Text)


class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    session_id = Column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id = Column(String, nullable=False, index=True)
    run_id = Column(String, index=True)
    message_index = Column(Integer, nullable=False)
    role = Column(String, nullable=False)
    message_type = Column(String, nullable=False, index=True)
    stream_state = Column(String, nullable=False)
    display_mode = Column(String, nullable=False)
    content_text = Column(Text, nullable=False, default="")
    payload_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    completed_at = Column(DateTime)


class ConversationEventModel(Base):
    __tablename__ = "conversation_events"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_conversation_events_session_seq"),
    )

    id = Column(String, primary_key=True)
    session_id = Column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq = Column(Integer, nullable=False)
    turn_id = Column(String, index=True)
    run_id = Column(String, index=True)
    message_id = Column(String, index=True)
    event_type = Column(String, nullable=False)
    payload_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class LLMUsageModel(Base):
    """LLM 使用统计模型"""
    __tablename__ = "llm_usage"
    
    id = Column(String, primary_key=True)
    execution_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost = Column(Integer, default=0)  # 单位: 分
    timestamp = Column(DateTime, default=datetime.now)
