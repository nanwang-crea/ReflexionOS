"""
文件功能：消息搜索索引（MessageSearchDocument）数据仓储
文件描述：封装 message_search_documents 表的增删改查，负责维护每条消息
    对应的全文检索文档（search_text），供消息内容搜索功能使用。
核心逻辑：以 message_id 作为唯一标识执行 upsert（存在则更新、不存在则
    新建），保证同一条消息只对应一份搜索索引记录。
"""
from __future__ import annotations

from datetime import datetime

from app.models.message_search_document import MessageSearchDocument
from app.storage.models import MessageSearchDocumentModel

from .base_repo import BaseRepository


class MessageSearchDocumentRepository(BaseRepository[MessageSearchDocument]):
    """消息搜索索引数据仓储"""

    def __init__(self, db):
        """
        函数名：__init__
        入参：
          - db: 数据库访问入口
        功能：初始化消息搜索索引仓储，绑定领域模型 MessageSearchDocument
        运行逻辑：调用父类构造函数完成初始化
        出参：无
        """
        super().__init__(db, MessageSearchDocument)

    def get(self, message_id: str, *, db_session=None) -> MessageSearchDocument | None:
        """
        函数名：get
        入参：
          - message_id (str): 消息主键 ID（同时也是搜索文档的主键）
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按消息 ID 获取其对应的搜索索引文档
        运行逻辑：按 message_id 精确匹配查询 message_search_documents 表
          第一条记录
        出参：MessageSearchDocument | None - 找到则返回索引文档对象，
          否则返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(message_id, db_session=managed_session)

        model = (
            db_session.query(MessageSearchDocumentModel).filter_by(message_id=message_id).first()
        )
        return self._to_domain(model)

    def upsert(
        self,
        *,
        message_id: str,
        session_id: str,
        turn_id: str,
        run_id: str | None,
        role: str,
        message_type: str,
        turn_index: int,
        turn_message_index: int,
        search_text: str,
        db_session=None,
    ) -> MessageSearchDocument:
        """
        函数名：upsert
        入参：
          - message_id (str): 消息主键 ID（搜索文档的唯一标识）
          - session_id (str): 所属会话 ID
          - turn_id (str): 所属轮次 ID
          - run_id (str | None): 所属运行 ID，可为空
          - role (str): 消息角色
          - message_type (str): 消息类型
          - turn_index (int): 所属轮次的序号
          - turn_message_index (int): 消息在轮次内的顺序号
          - search_text (str): 用于全文检索的规范化文本内容
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：写入或更新指定消息的搜索索引文档（存在则更新全部字段，
          不存在则新建）
        运行逻辑：
          1. 按 message_id 查询是否已存在索引记录
          2. 不存在：以传入参数构造新的 MessageSearchDocumentModel，
             created_at/updated_at 均置为当前时间后写入
          3. 存在：逐字段覆盖为最新值，仅更新 updated_at
          4. flush + refresh 后返回最新状态
        出参：MessageSearchDocument - 写入/更新后的搜索索引文档对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.upsert(
                    message_id=message_id,
                    session_id=session_id,
                    turn_id=turn_id,
                    run_id=run_id,
                    role=role,
                    message_type=message_type,
                    turn_index=turn_index,
                    turn_message_index=turn_message_index,
                    search_text=search_text,
                    db_session=managed_session,
                )

        model = (
            db_session.query(MessageSearchDocumentModel).filter_by(message_id=message_id).first()
        )
        now = datetime.now()
        if model is None:
            model = MessageSearchDocumentModel(
                message_id=message_id,
                session_id=session_id,
                turn_id=turn_id,
                run_id=run_id,
                role=role,
                message_type=message_type,
                turn_index=turn_index,
                turn_message_index=turn_message_index,
                search_text=search_text,
                created_at=now,
                updated_at=now,
            )
            db_session.add(model)
        else:
            model.session_id = session_id
            model.turn_id = turn_id
            model.run_id = run_id
            model.role = role
            model.message_type = message_type
            model.turn_index = turn_index
            model.turn_message_index = turn_message_index
            model.search_text = search_text
            model.updated_at = now

        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
        """
        函数名：delete_by_turn_ids
        入参：
          - turn_ids (list[str]): 待清理搜索索引所属的轮次 ID 列表
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按轮次 ID 批量删除其下全部消息的搜索索引文档（配合轮次
          回退/删除场景，联动清理关联数据）
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
            db_session.query(MessageSearchDocumentModel)
            .filter(MessageSearchDocumentModel.turn_id.in_(turn_ids))
            .delete(synchronize_session=False)
        )
        db_session.flush()
        return int(deleted or 0)
