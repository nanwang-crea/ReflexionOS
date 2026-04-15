from sqlalchemy import Column, String, DateTime, JSON, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

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


class ExecutionModel(Base):
    """执行记录模型"""
    __tablename__ = "executions"
    
    id = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    task = Column(Text, nullable=False)
    status = Column(String, default="pending", index=True)
    steps = Column(JSON, default=[])
    result = Column(Text)
    total_duration = Column(Integer)  # 毫秒
    created_at = Column(DateTime, default=datetime.now, index=True)
    completed_at = Column(DateTime)


class ConversationModel(Base):
    """对话记录模型"""
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True)
    execution_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)


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
