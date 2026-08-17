"""
文件功能：会话事件（ConversationEvent）数据仓储
文件描述：封装 conversation_events 表的增删查操作，管理会话内事件流的
    序号分配（seq）与增量拉取，是前端订阅/回放会话动态的数据来源。
核心逻辑：append_many 在同一批事件写入时统一分配连续递增的 seq（默认
    从该会话当前最大 seq + 1 开始，也可由调用方指定起始序号），保证
    事件序号在会话内严格单调且不重复。
"""
from app.models.conversation import ConversationEvent
from app.storage.models import ConversationEventModel

from .base_repo import BaseRepository


class ConversationEventRepository(BaseRepository[ConversationEvent]):
    """会话事件数据仓储"""

    def __init__(self, db):
        """
        函数名：__init__
        入参：
          - db: 数据库访问入口
        功能：初始化会话事件仓储，绑定领域模型 ConversationEvent
        运行逻辑：调用父类构造函数完成初始化
        出参：无
        """
        super().__init__(db, ConversationEvent)

    def append_many(
        self,
        events: list[ConversationEvent],
        *,
        db_session=None,
        start_seq: int | None = None,
    ) -> list[ConversationEvent]:
        """
        函数名：append_many
        入参：
          - events (list[ConversationEvent]): 待追加写入的事件领域对象
            列表，要求全部属于同一个会话
          - db_session: 外部传入的数据库会话，为空则内部自动创建
          - start_seq (int | None): 起始序号，为空时自动取该会话当前最大
            seq + 1 作为起点
        功能：批量追加会话事件，并为每条事件分配连续递增的序号（seq）
        运行逻辑：
          1. events 为空直接返回空列表
          2. 校验批次内所有事件的 session_id 一致，不一致则抛出
             ValueError（同批事件必须属于同一个会话）
          3. start_seq 为空时，查询该会话当前最大 seq（无记录则为 0），
             以 max_seq + 1 作为下一个可用序号；否则直接使用 start_seq
          4. 遍历 events，为每条事件填充 seq 后构造 ConversationEventModel
             并写入，序号逐条递增
          5. flush 后逐条 refresh，转换为领域对象列表返回
        出参：list[ConversationEvent] - 写入成功后的事件列表（含分配好的
          seq），events 为空时返回空列表
        """
        if not events:
            return []

        session_id = events[0].session_id
        if any(event.session_id != session_id for event in events):
            raise ValueError("同批事件必须属于同一个会话")

        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.append_many(events, db_session=managed_session, start_seq=start_seq)

        models: list[ConversationEventModel] = []
        if start_seq is None:
            max_seq = (
                db_session.query(ConversationEventModel.seq)
                .filter_by(session_id=session_id)
                .order_by(ConversationEventModel.seq.desc())
                .limit(1)
                .scalar()
            ) or 0
            next_seq = max_seq + 1
        else:
            next_seq = start_seq
        for event in events:
            model = ConversationEventModel(
                **event.model_dump(exclude={"seq"}),
                seq=next_seq,
            )
            db_session.add(model)
            models.append(model)
            next_seq += 1

        db_session.flush()
        for model in models:
            db_session.refresh(model)
        return self._to_domain_list(models)

    def list_after_seq(self, session_id: str, after_seq: int) -> list[ConversationEvent]:
        """
        函数名：list_after_seq
        入参：
          - session_id (str): 所属会话 ID
          - after_seq (int): 起始序号（不含），只返回 seq 大于该值的事件
        功能：增量拉取指定会话中序号大于 after_seq 的全部事件（典型用于
          前端按游标增量同步会话动态）
        运行逻辑：过滤 session_id 匹配且 seq > after_seq 的记录，按 seq
          升序排列
        出参：list[ConversationEvent] - 满足条件的事件列表，按 seq
          升序排列
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(ConversationEventModel)
                .filter(
                    ConversationEventModel.session_id == session_id,
                    ConversationEventModel.seq > after_seq,
                )
                .order_by(ConversationEventModel.seq.asc())
                .all()
            )
            return self._to_domain_list(models)

    def max_seq(self, session_id: str, *, db_session=None) -> int | None:
        """
        函数名：max_seq
        入参：
          - session_id (str): 所属会话 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：获取指定会话当前已写入事件的最大序号
        运行逻辑：按 session_id 过滤，按 seq 倒序取第一条记录的 seq 值
        出参：int | None - 最大序号，该会话无任何事件时返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.max_seq(session_id, db_session=managed_session)

        return (
            db_session.query(ConversationEventModel.seq)
            .filter_by(session_id=session_id)
            .order_by(ConversationEventModel.seq.desc())
            .limit(1)
            .scalar()
        )

    def first_seq(self, session_id: str, *, db_session=None) -> int | None:
        """
        函数名：first_seq
        入参：
          - session_id (str): 所属会话 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：获取指定会话当前已写入事件的最小（最早）序号
        运行逻辑：按 session_id 过滤，按 seq 升序取第一条记录的 seq 值
        出参：int | None - 最小序号，该会话无任何事件时返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.first_seq(session_id, db_session=managed_session)

        return (
            db_session.query(ConversationEventModel.seq)
            .filter_by(session_id=session_id)
            .order_by(ConversationEventModel.seq.asc())
            .limit(1)
            .scalar()
        )

    def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
        """
        函数名：delete_by_turn_ids
        入参：
          - turn_ids (list[str]): 待清理事件所属的轮次 ID 列表
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按轮次 ID 批量删除其关联的全部会话事件（配合轮次回退/删除
          场景，联动清理关联数据）
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
            db_session.query(ConversationEventModel)
            .filter(ConversationEventModel.turn_id.in_(turn_ids))
            .delete(synchronize_session=False)
        )
        db_session.flush()
        return int(deleted or 0)
