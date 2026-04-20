from typing import List, Optional
from app.storage.models import ExecutionModel
from app.models.execution import Execution, ExecutionStep, ExecutionStatus
import logging

logger = logging.getLogger(__name__)


class ExecutionRepository:
    """执行记录仓储"""
    
    def __init__(self, db):
        self.db = db
    
    def save(self, execution: Execution) -> Execution:
        """保存执行记录"""
        with self.db.get_session() as session:
            # 检查是否已存在
            existing = session.query(ExecutionModel).filter_by(id=execution.id).first()
            
            if existing:
                # 更新
                existing.status = execution.status.value
                existing.session_id = execution.session_id
                existing.steps = [step.dict() for step in execution.steps]
                existing.result = execution.result
                existing.total_duration = int(execution.total_duration * 1000) if execution.total_duration else None
                existing.completed_at = execution.completed_at
                logger.info(f"更新执行记录: {execution.id}")
            else:
                # 新建
                model = ExecutionModel(
                    id=execution.id,
                    project_id=execution.project_id,
                    session_id=execution.session_id,
                    project_path=execution.project_path,
                    task=execution.task,
                    status=execution.status.value,
                    steps=[step.dict() for step in execution.steps],
                    result=execution.result,
                    total_duration=int(execution.total_duration * 1000) if execution.total_duration else None,
                    created_at=execution.created_at,
                    completed_at=execution.completed_at
                )
                session.add(model)
                logger.info(f"创建执行记录: {execution.id}")
            
            return execution
    
    def get(self, execution_id: str) -> Optional[Execution]:
        """获取执行记录"""
        with self.db.get_session() as session:
            model = session.query(ExecutionModel).filter_by(id=execution_id).first()
            if model:
                return Execution(
                    id=model.id,
                    project_id=model.project_id,
                    session_id=model.session_id,
                    project_path=model.project_path,
                    task=model.task,
                    status=ExecutionStatus(model.status),
                    steps=[ExecutionStep(**s) for s in model.steps],
                    result=model.result,
                    total_duration=model.total_duration / 1000 if model.total_duration else None,
                    created_at=model.created_at,
                    completed_at=model.completed_at
                )
            return None

    def list_all(self, limit: Optional[int] = None) -> List[Execution]:
        """列出所有执行记录"""
        with self.db.get_session() as session:
            query = session.query(ExecutionModel).order_by(
                ExecutionModel.created_at.desc()
            )
            if limit is not None:
                query = query.limit(limit)

            models = query.all()

            return [
                Execution(
                    id=m.id,
                    project_id=m.project_id,
                    session_id=m.session_id,
                    project_path=m.project_path,
                    task=m.task,
                    status=ExecutionStatus(m.status),
                    steps=[ExecutionStep(**s) for s in m.steps],
                    result=m.result,
                    total_duration=m.total_duration / 1000 if m.total_duration else None,
                    created_at=m.created_at,
                    completed_at=m.completed_at
                )
                for m in models
            ]
    
    def list_by_project(self, project_id: str, limit: int = 10) -> List[Execution]:
        """获取项目的执行历史"""
        with self.db.get_session() as session:
            models = session.query(ExecutionModel).filter_by(
                project_id=project_id
            ).order_by(
                ExecutionModel.created_at.desc()
            ).limit(limit).all()
            
            return [
                Execution(
                    id=m.id,
                    project_id=m.project_id,
                    session_id=m.session_id,
                    project_path=m.project_path,
                    task=m.task,
                    status=ExecutionStatus(m.status),
                    steps=[ExecutionStep(**s) for s in m.steps],
                    result=m.result,
                    total_duration=m.total_duration / 1000 if m.total_duration else None,
                    created_at=m.created_at,
                    completed_at=m.completed_at
                )
                for m in models
            ]
    
    def delete(self, execution_id: str) -> bool:
        """删除执行记录"""
        with self.db.get_session() as session:
            model = session.query(ExecutionModel).filter_by(id=execution_id).first()
            if model:
                session.delete(model)
                logger.info(f"删除执行记录: {execution_id}")
                return True
            return False
