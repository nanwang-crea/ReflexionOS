"""
文件功能：对话轮次（Turn）数据仓储
文件描述：封装 turns 表的增删改查与分页/游标查询，支撑会话内轮次列表的
    正序/倒序分页加载、按状态清理过期轮次等场景。
核心逻辑：分页类方法（list_by_session_latest/list_by_session_before）统一
    采用"按 turn_index 倒序取 limit 条，再 reversed 还原正序"的模式，
    保证返回结果始终按轮次顺序（从旧到新）排列。
"""
from datetime import datetime

from app.errors import NotFoundValueError
from app.models.conversation import Turn
from app.storage.models import TurnModel

from .base_repo import BaseRepository


class TurnRepository(BaseRepository[Turn]):
    """对话轮次数据仓储"""

    def __init__(self, db):
        """
        函数名：__init__
        入参：
          - db: 数据库访问入口
        功能：初始化轮次仓储，绑定领域模型 Turn
        运行逻辑：调用父类构造函数完成初始化
        出参：无
        """
        super().__init__(db, Turn)

    def create(self, turn: Turn, *, db_session=None) -> Turn:
        """
        函数名：create
        入参：
          - turn (Turn): 待创建的轮次领域对象
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：新建一条轮次记录
        运行逻辑：将 turn 全部字段展开为 TurnModel 构造参数写入，
          flush + refresh 后返回最新状态
        出参：Turn - 创建成功后的轮次领域对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(turn, db_session=managed_session)

        model = TurnModel(**turn.model_dump())
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def get(self, turn_id: str, *, db_session=None) -> Turn | None:
        """
        函数名：get
        入参：
          - turn_id (str): 轮次主键 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按主键获取单个轮次
        运行逻辑：按 id 精确匹配查询 turns 表第一条记录
        出参：Turn | None - 找到则返回轮次对象，否则返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(turn_id, db_session=managed_session)

        model = db_session.query(TurnModel).filter_by(id=turn_id).first()
        return self._to_domain(model)

    def list_by_session(self, session_id: str) -> list[Turn]:
        """
        函数名：list_by_session
        入参：
          - session_id (str): 所属会话 ID
        功能：列出指定会话下的全部轮次
        运行逻辑：按 session_id 过滤，按 turn_index 升序排列（从第一轮到
          最后一轮）
        出参：list[Turn] - 轮次列表（可能为空列表）
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(TurnModel)
                .filter_by(session_id=session_id)
                .order_by(TurnModel.turn_index.asc())
                .all()
            )
            return self._to_domain_list(models)

    def list_by_session_latest(self, session_id: str, limit: int) -> list[Turn]:
        """
        函数名：list_by_session_latest
        入参：
          - session_id (str): 所属会话 ID
          - limit (int): 最多返回的轮次条数
        功能：获取指定会话最近的 N 条轮次（用于首屏加载最新对话）
        运行逻辑：按 turn_index 倒序取前 limit 条（即最新的若干轮次），
          再反转列表顺序，使返回结果保持从旧到新排列
        出参：list[Turn] - 最近 limit 条轮次，按 turn_index 升序排列
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(TurnModel)
                .filter(TurnModel.session_id == session_id)
                .order_by(TurnModel.turn_index.desc())
                .limit(limit)
                .all()
            )
            return self._to_domain_list(list(reversed(models)))

    def list_by_session_before(self, session_id: str, before_turn_id: str, limit: int) -> list[Turn]:
        """
        函数名：list_by_session_before
        入参：
          - session_id (str): 所属会话 ID
          - before_turn_id (str): 游标轮次 ID，查询结果为该轮次之前的数据
          - limit (int): 最多返回的轮次条数
        功能：基于游标向前翻页加载更早的历史轮次（用于"加载更多历史消息"）
        运行逻辑：
          1. 先按 before_turn_id + session_id 定位游标轮次，找不到则返回
             空列表
          2. 查询 turn_index 小于游标轮次 turn_index 的记录，按 turn_index
             倒序取前 limit 条
          3. 反转列表顺序，使返回结果保持从旧到新排列
        出参：list[Turn] - 游标之前的 limit 条轮次，按 turn_index 升序
          排列；游标不存在时返回空列表
        """
        with self.db.get_session() as db_session:
            cursor = (
                db_session.query(TurnModel)
                .filter_by(id=before_turn_id, session_id=session_id)
                .first()
            )
            if cursor is None:
                return []

            models = (
                db_session.query(TurnModel)
                .filter(
                    TurnModel.session_id == session_id,
                    TurnModel.turn_index < cursor.turn_index,
                )
                .order_by(TurnModel.turn_index.desc())
                .limit(limit)
                .all()
            )
            return self._to_domain_list(list(reversed(models)))

    def list_by_ids(self, turn_ids: list[str]) -> list[Turn]:
        """
        函数名：list_by_ids
        入参：
          - turn_ids (list[str]): 轮次 ID 列表
        功能：按 ID 批量获取轮次
        运行逻辑：turn_ids 为空直接返回空列表；否则用 IN 查询批量取出，
          按 turn_index 升序排列
        出参：list[Turn] - 匹配到的轮次列表（可能少于传入的 ID 数量）
        """
        if not turn_ids:
            return []
        with self.db.get_session() as db_session:
            models = (
                db_session.query(TurnModel)
                .filter(TurnModel.id.in_(turn_ids))
                .order_by(TurnModel.turn_index.asc())
                .all()
            )
            return self._to_domain_list(models)

    def delete_by_session_after_index(self, session_id: str, min_turn_index: int, *, db_session=None) -> list[str]:
        """
        函数名：delete_by_session_after_index
        入参：
          - session_id (str): 所属会话 ID
          - min_turn_index (int): 起始轮次序号（含）
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：删除指定会话中 turn_index >= min_turn_index 的全部轮次（常
          用于"回退到某一轮"场景，清理该轮之后产生的轮次）
        运行逻辑：
          1. 先查出待删除轮次的 id 列表（供调用方联动清理关联的
             消息/运行/事件）
          2. 按相同过滤条件执行批量删除（synchronize_session=False 表示
             不同步本地 ORM 会话缓存，需要调用方自行处理已加载的对象）
        出参：list[str] - 被删除的轮次 ID 列表
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.delete_by_session_after_index(session_id, min_turn_index, db_session=managed_session)

        turn_ids = (
            db_session.query(TurnModel.id)
            .filter(TurnModel.session_id == session_id, TurnModel.turn_index >= min_turn_index)
            .all()
        )
        turn_id_list = [tid[0] for tid in turn_ids]
        db_session.query(TurnModel).filter(
            TurnModel.session_id == session_id, TurnModel.turn_index >= min_turn_index
        ).delete(synchronize_session=False)
        db_session.flush()
        return turn_id_list

    def update(self, turn: Turn, *, db_session=None) -> Turn:
        """
        函数名：update
        入参：
          - turn (Turn): 携带最新字段值的轮次领域对象（以 id 定位要更新的
            记录）
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：更新轮次的状态、活跃运行 ID、完成时间、更新时间
        运行逻辑：
          1. 按 turn.id 查询记录，不存在则抛出 NotFoundValueError
          2. 覆盖 status/active_run_id/completed_at/updated_at 字段
          3. flush + refresh 后返回最新状态
        出参：Turn - 更新后的轮次领域对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(turn, db_session=managed_session)

        model = db_session.query(TurnModel).filter_by(id=turn.id).first()
        if model is None:
            raise NotFoundValueError("轮次不存在")

        model.status = turn.status.value
        model.active_run_id = turn.active_run_id
        model.completed_at = turn.completed_at
        model.updated_at = turn.updated_at
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def next_turn_index(self, session_id: str, *, db_session=None) -> int:
        """
        函数名：next_turn_index
        入参：
          - session_id (str): 所属会话 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：计算指定会话下一个可用的轮次序号
        运行逻辑：查询该会话当前最大的 turn_index（无记录时视为 0），
          返回其加一的结果
        出参：int - 下一个轮次应使用的 turn_index
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.next_turn_index(session_id, db_session=managed_session)

        current = (
            db_session.query(TurnModel.turn_index)
            .filter_by(session_id=session_id)
            .order_by(TurnModel.turn_index.desc())
            .limit(1)
            .scalar()
        ) or 0
        return current + 1

    def list_terminal_before(
        self, statuses: list[str], before: datetime, *, db_session=None
    ) -> list[Turn]:
        """
        函数名：list_terminal_before
        入参：
          - statuses (list[str]): 目标终态状态列表（如已完成/已失败等）
          - before (datetime): 时间上界，只查询完成时间早于该时刻的轮次
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：查询指定时间点之前已进入终态、且完成时间早于 before 的轮次
          （典型用途：定时任务清理/归档过期的历史轮次）
        运行逻辑：过滤条件为 status 在 statuses 中、completed_at 非空且
          小于 before，按 completed_at 升序、turn_index 升序排列
        出参：list[Turn] - 满足条件的轮次列表，按完成时间从早到晚排列
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.list_terminal_before(statuses, before, db_session=managed_session)

        models = (
            db_session.query(TurnModel)
            .filter(
                TurnModel.status.in_(statuses),
                TurnModel.completed_at.isnot(None),
                TurnModel.completed_at < before,
            )
            .order_by(TurnModel.completed_at.asc(), TurnModel.turn_index.asc())
            .all()
        )
        return self._to_domain_list(models)
