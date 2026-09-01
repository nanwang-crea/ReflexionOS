"""
文件功能：运行（Run）数据仓储
文件描述：封装 runs 表的增删改查，管理某一轮次（Turn）下每次执行尝试的
    状态、使用的模型、起止时间与错误信息。
核心逻辑：list_by_turn_ids 通过 join TurnModel 按轮次序号排序，保证跨
    多个轮次查询运行记录时结果仍按对话时间顺序排列。
"""
from app.errors import NotFoundValueError
from app.models.conversation import Run
from app.storage.models import RunModel, TurnModel

from .base_repo import BaseRepository


class RunRepository(BaseRepository[Run]):
    """运行数据仓储"""

    def __init__(self, db):
        """
        函数名：__init__
        入参：
          - db: 数据库访问入口
        功能：初始化运行仓储，绑定领域模型 Run
        运行逻辑：调用父类构造函数完成初始化
        出参：无
        """
        super().__init__(db, Run)

    def create(self, run: Run, *, db_session=None) -> Run:
        """
        函数名：create
        入参：
          - run (Run): 待创建的运行领域对象
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：新建一条运行记录
        运行逻辑：将 run 全部字段展开为 RunModel 构造参数写入，
          flush + refresh 后返回最新状态
        出参：Run - 创建成功后的运行领域对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(run, db_session=managed_session)

        model = RunModel(**run.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def get(self, run_id: str, *, db_session=None) -> Run | None:
        """
        函数名：get
        入参：
          - run_id (str): 运行主键 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按主键获取单个运行记录
        运行逻辑：按 id 精确匹配查询 runs 表第一条记录
        出参：Run | None - 找到则返回运行对象，否则返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(run_id, db_session=managed_session)

        model = db_session.query(RunModel).filter_by(id=run_id).first()
        return self._to_domain(model)

    def list_by_session(self, session_id: str) -> list[Run]:
        """
        函数名：list_by_session
        入参：
          - session_id (str): 所属会话 ID
        功能：列出指定会话下的全部运行记录
        运行逻辑：按 session_id 过滤，依次按 turn_id、attempt_index、id
          升序排列，保证同一轮次内的多次尝试按重试顺序排列
        出参：list[Run] - 运行记录列表（可能为空列表）
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(RunModel)
                .filter_by(session_id=session_id)
                .order_by(
                    RunModel.turn_id.asc(),
                    RunModel.attempt_index.asc(),
                    RunModel.id.asc(),
                )
                .all()
            )
            return self._to_domain_list(models)

    def list_by_status(self, status: str) -> list[Run]:
        """
        函数名：list_by_status
        入参：
          - status (str): 运行状态取值（RunStatus 枚举的 value）
        功能：跨会话查询处于指定状态的全部运行记录。用于服务启动时扫描
          上次进程退出前遗留的、卡在某个非终态（如等待审批）的孤儿运行。
        运行逻辑：按 status 精确匹配 runs 表，不做排序（调用方通常只关心
          数量少、需要逐条纠正状态的场景）
        出参：list[Run] - 匹配到的运行记录列表（可能为空列表）
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(RunModel)
                .filter_by(status=status)
                .all()
            )
            return self._to_domain_list(models)

    def list_by_turn_ids(self, session_id: str, turn_ids: list[str]) -> list[Run]:
        """
        函数名：list_by_turn_ids
        入参：
          - session_id (str): 所属会话 ID
          - turn_ids (list[str]): 轮次 ID 列表
        功能：按轮次 ID 批量获取运行记录（用于一次性加载多个轮次的运行
          历史）
        运行逻辑：
          1. turn_ids 为空直接返回空列表
          2. 通过 join TurnModel（同时匹配 turn_id 与 session_id）关联出
             每条运行所属轮次的 turn_index
          3. 过滤 session_id 与 turn_id 在给定列表中的记录
          4. 依次按轮次序号（turn_index）、尝试序号（attempt_index）、id
             升序排列，使结果按对话时间顺序展示
        出参：list[Run] - 匹配到的运行记录列表
        """
        if not turn_ids:
            return []
        with self.db.get_session() as db_session:
            models = (
                db_session.query(RunModel)
                .join(
                    TurnModel,
                    (TurnModel.id == RunModel.turn_id)
                    & (TurnModel.session_id == RunModel.session_id),
                )
                .filter(
                    RunModel.session_id == session_id,
                    RunModel.turn_id.in_(turn_ids),
                )
                .order_by(
                    TurnModel.turn_index.asc(),
                    RunModel.attempt_index.asc(),
                    RunModel.id.asc(),
                )
                .all()
            )
            return self._to_domain_list(models)

    def update(self, run: Run, *, db_session=None) -> Run:
        """
        函数名：update
        入参：
          - run (Run): 携带最新字段值的运行领域对象（以 id 定位要更新的
            记录）
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：更新运行的状态、起止时间、错误信息
        运行逻辑：
          1. 按 run.id 查询记录，不存在则抛出 NotFoundValueError
          2. 覆盖 status（取枚举 value）/started_at/finished_at/
             error_code/error_message 字段
          3. flush + refresh 后返回最新状态
        出参：Run - 更新后的运行领域对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(run, db_session=managed_session)

        model = db_session.query(RunModel).filter_by(id=run.id).first()
        if model is None:
            raise NotFoundValueError("运行不存在")

        model.status = run.status.value
        model.started_at = run.started_at
        model.finished_at = run.finished_at
        model.error_code = run.error_code
        model.error_message = run.error_message
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
        """
        函数名：delete_by_turn_ids
        入参：
          - turn_ids (list[str]): 待清理运行记录所属的轮次 ID 列表
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按轮次 ID 批量删除其下全部运行记录（配合轮次回退/删除场景，
          联动清理关联数据）
        运行逻辑：turn_ids 为空直接返回 0；否则按 turn_id IN 条件批量
          删除（synchronize_session=False 表示不同步本地 ORM 会话缓存）
        出参：int - 实际删除的记录条数
        """
        if not turn_ids:
            return 0

        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete_by_turn_ids(turn_ids, db_session=managed_session)

        deleted = (
            db_session.query(RunModel)
            .filter(RunModel.turn_id.in_(turn_ids))
            .delete(synchronize_session=False)
        )
        db_session.flush()
        return int(deleted or 0)
