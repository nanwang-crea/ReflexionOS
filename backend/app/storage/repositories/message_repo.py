"""
文件功能：消息（Message）数据仓储
文件描述：封装 messages 表的增删改查，支撑会话消息的正序/倒序分页加载、
    按轮次查询、附件（attachments）序列化与反序列化、以及为"续写摘要"
    场景挑选最近的候选消息等能力，是聊天记录相关功能的核心数据层。
核心逻辑：
    1. 消息在数据库中以 attachments_json（JSON 文本）存储附件列表，读取
       时反序列化为 MessageAttachment 对象列表，写入时序列化为 JSON 字符串，
       因此重写了基类的 _to_domain/_to_domain_list 完成这一额外转换。
    2. 多数分页/排序查询通过 outerjoin TurnModel 拿到 turn_index 参与
       排序，兼容 turn_id 尚未关联到具体轮次（TurnModel.turn_index 为
       None）的历史数据，用 case 表达式把这类记录排到最后。
"""
import json
import logging

from sqlalchemy import and_, case, func, or_

from app.errors import NotFoundValueError
from app.models.conversation import Message, MessageAttachment, MessageType, StreamState
from app.storage.models import MessageModel, TurnModel
from app.services.attachment_service import get_attachment_service

from .base_repo import BaseRepository

logger = logging.getLogger(__name__)


class MessageRepository(BaseRepository[Message]):
    """消息数据仓储"""

    def __init__(self, db):
        """
        函数名：__init__
        入参：
          - db: 数据库访问入口
        功能：初始化消息仓储，绑定领域模型 Message
        运行逻辑：调用父类构造函数完成初始化
        出参：无
        """
        super().__init__(db, Message)

    def _to_domain(self, model) -> Message | None:
        """
        函数名：_to_domain
        入参：
          - model: 单条 MessageModel ORM 实例，可为 None
        功能：将 ORM 消息模型转换为 Message 领域对象（覆写基类实现，
          额外处理 attachments_json 字段的反序列化）
        运行逻辑：
          1. model 为空直接返回 None
          2. 先手动拼装除 attachments 外的全部字段
          3. 若 attachments_json 有值，解析 JSON 并逐条构造
             MessageAttachment；解析失败（格式错误/类型错误）时降级为
             空列表，避免影响消息主体的读取
          4. 无 attachments_json 时附件列表直接置空
        出参：Message | None - 转换后的消息领域对象，输入为空时返回 None
        """
        if model is None:
            return None

        data = {
            "id": model.id,
            "session_id": model.session_id,
            "turn_id": model.turn_id,
            "run_id": model.run_id,
            "turn_message_index": model.turn_message_index,
            "role": model.role,
            "message_type": model.message_type,
            "stream_state": model.stream_state,
            "display_mode": model.display_mode,
            "content_text": model.content_text,
            "payload_json": model.payload_json,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
            "completed_at": model.completed_at,
        }

        # Convert attachments_json to attachments list
        if hasattr(model, "attachments_json") and model.attachments_json:
            try:
                attachments_data = json.loads(model.attachments_json)
                data["attachments"] = [MessageAttachment(**att) for att in attachments_data]
            except (json.JSONDecodeError, TypeError, ValueError):
                data["attachments"] = []
        else:
            data["attachments"] = []

        return Message(**data)

    def _to_domain_list(self, models) -> list[Message]:
        """
        函数名：_to_domain_list
        入参：
          - models: MessageModel ORM 实例的可迭代集合
        功能：批量转换消息列表（覆写基类实现，改用自定义 _to_domain 以
          正确处理附件字段）
        运行逻辑：跳过 None 元素，对每个非空模型调用 self._to_domain
        出参：list[Message] - 转换后的消息领域对象列表
        """
        return [self._to_domain(m) for m in models if m is not None]

    def create(self, message: Message, *, db_session=None) -> Message:
        """
        函数名：create
        入参：
          - message (Message): 待创建的消息领域对象
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：新建一条消息记录
        运行逻辑：
          1. 以 mode="json" 序列化 message，确保所有 datetime 字段先转为
             字符串（便于统一处理，避免类型不一致问题）
          2. 但 SQLAlchemy 的 DateTime 列需要原生 datetime 对象，因此将
             created_at/updated_at（及非空的 completed_at）替换回原始
             datetime 值
          3. 将 attachments 列表弹出，若非空则序列化为 JSON 字符串存入
             attachments_json，否则置为 None
          4. 用整理好的 data 构造 MessageModel 并写入，flush + refresh
             后返回领域对象
        出参：Message - 创建成功后的消息领域对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.create(message, db_session=managed_session)

        # 使用 mode="json" 确保所有 datetime 被序列化为字符串
        data = message.model_dump(mode="json")

        # 但 SQLAlchemy 的 DateTime 列需要 datetime 对象，所以转回来
        data["created_at"] = message.created_at
        data["updated_at"] = message.updated_at
        if message.completed_at is not None:
            data["completed_at"] = message.completed_at

        # Convert attachments list to JSON string for storage
        if "attachments" in data:
            attachments_data = data.pop("attachments")
            if attachments_data:
                # 已经是 mode="json" 序列化的结果，直接转 JSON 字符串
                data["attachments_json"] = json.dumps(attachments_data)
            else:
                data["attachments_json"] = None

        model = MessageModel(**data)
        db_session.add(model)
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def get(self, message_id: str, *, db_session=None) -> Message | None:
        """
        函数名：get
        入参：
          - message_id (str): 消息主键 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按主键获取单条消息
        运行逻辑：按 id 精确匹配查询 messages 表第一条记录
        出参：Message | None - 找到则返回消息对象，否则返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get(message_id, db_session=managed_session)

        model = db_session.query(MessageModel).filter_by(id=message_id).first()
        return self._to_domain(model)

    def list_by_session(self, session_id: str) -> list[Message]:
        """
        函数名：list_by_session
        入参：
          - session_id (str): 所属会话 ID
        功能：列出指定会话下的全部消息（按对话顺序正序）
        运行逻辑：outerjoin TurnModel 拿到消息所属轮次的 turn_index；
          排序依次为：turn_index 为空的记录排最后 -> turn_index 升序 ->
          轮次内消息序号（turn_message_index）升序 -> 创建时间升序，
          兜底保证顺序稳定
        出参：list[Message] - 消息列表（可能为空列表）
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .outerjoin(
                    TurnModel,
                    (TurnModel.id == MessageModel.turn_id)
                    & (TurnModel.session_id == MessageModel.session_id),
                )
                .filter(MessageModel.session_id == session_id)
                .order_by(
                    case((TurnModel.turn_index.is_(None), 1), else_=0).asc(),
                    TurnModel.turn_index.asc(),
                    MessageModel.turn_message_index.asc(),
                    MessageModel.created_at.asc(),
                )
                .all()
            )
            return self._to_domain_list(models)

    def count_by_session(self, session_id: str) -> int:
        """
        函数名：count_by_session
        入参：
          - session_id (str): 所属会话 ID
        功能：统计指定会话下的消息总数
        运行逻辑：按 session_id 过滤后执行 COUNT 聚合查询
        出参：int - 消息总条数（无记录时为 0）
        """
        with self.db.get_session() as db_session:
            count = (
                db_session.query(func.count(MessageModel.id))
                .filter(MessageModel.session_id == session_id)
                .scalar()
            )
            return int(count or 0)

    def list_by_session_latest(self, session_id: str, limit: int) -> list[Message]:
        """
        函数名：list_by_session_latest
        入参：
          - session_id (str): 所属会话 ID
          - limit (int): 最多返回的消息条数
        功能：获取指定会话最近的 N 条消息（用于首屏加载最新聊天记录）
        运行逻辑：outerjoin TurnModel 后按"轮次序号+轮内消息序号+创建
          时间"整体倒序取前 limit 条（即最新的若干条消息），再反转列表
          顺序，使结果保持从旧到新排列
        出参：list[Message] - 最近 limit 条消息，按时间升序排列
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .outerjoin(
                    TurnModel,
                    (TurnModel.id == MessageModel.turn_id)
                    & (TurnModel.session_id == MessageModel.session_id),
                )
                .filter(MessageModel.session_id == session_id)
                .order_by(
                    case((TurnModel.turn_index.is_(None), 1), else_=0).desc(),
                    TurnModel.turn_index.desc(),
                    MessageModel.turn_message_index.desc(),
                    MessageModel.created_at.desc(),
                )
                .limit(limit)
                .all()
            )
            return self._to_domain_list(list(reversed(models)))

    def list_by_session_before(self, session_id: str, before_message_id: str, limit: int) -> list[Message]:
        """
        函数名：list_by_session_before
        入参：
          - session_id (str): 所属会话 ID
          - before_message_id (str): 游标消息 ID，查询结果为该消息之前的
            历史消息
          - limit (int): 最多返回的消息条数
        功能：基于游标向前翻页加载更早的历史消息（用于"加载更多历史
          消息"）
        运行逻辑：
          1. 按 before_message_id 定位游标消息，找不到时记录警告日志并
             降级为返回最新的 limit 条消息（list_by_session_latest）
          2. 查出游标消息所属轮次的 turn_index（轮次缺失时按 0 处理）
          3. 过滤条件：轮次序号小于游标轮次序号，或轮次序号相同但轮内
             消息序号小于游标消息的序号（即严格早于游标位置的消息）
          4. 按"轮次序号+轮内消息序号+创建时间"整体倒序取前 limit 条，
             记录调试日志后反转列表，使结果保持从旧到新排列
        出参：list[Message] - 游标之前的 limit 条消息，按时间升序排列；
          游标不存在时返回该会话最新的 limit 条消息
        """
        with self.db.get_session() as db_session:
            cursor = db_session.query(MessageModel).filter_by(id=before_message_id).first()
            if cursor is None:
                logger.warning(
                    "message page fallback to latest session_id=%s before_message_id=%s limit=%s reason=cursor_missing",
                    session_id,
                    before_message_id,
                    limit,
                )
                return self.list_by_session_latest(session_id, limit)

            cursor_turn = db_session.query(TurnModel).filter_by(id=cursor.turn_id).first()
            cursor_turn_index = cursor_turn.turn_index if cursor_turn else 0

            models = (
                db_session.query(MessageModel)
                .outerjoin(
                    TurnModel,
                    (TurnModel.id == MessageModel.turn_id)
                    & (TurnModel.session_id == MessageModel.session_id),
                )
                .filter(
                    MessageModel.session_id == session_id,
                    or_(
                        TurnModel.turn_index < cursor_turn_index,
                        and_(
                            TurnModel.turn_index == cursor_turn_index,
                            MessageModel.turn_message_index < cursor.turn_message_index,
                        ),
                    ),
                )
                .order_by(
                    case((TurnModel.turn_index.is_(None), 1), else_=0).desc(),
                    TurnModel.turn_index.desc(),
                    MessageModel.turn_message_index.desc(),
                    MessageModel.created_at.desc(),
                )
                .limit(limit)
                .all()
            )
            logger.info(
                "message page before session_id=%s before_message_id=%s cursor_turn_id=%s cursor_turn_index=%s cursor_message_index=%s returned_ids=%s",
                session_id,
                before_message_id,
                cursor.turn_id,
                cursor_turn_index,
                cursor.turn_message_index,
                [model.id for model in models],
            )
            return self._to_domain_list(list(reversed(models)))

    def list_by_turn(self, turn_id: str) -> list[Message]:
        """
        函数名：list_by_turn
        入参：
          - turn_id (str): 所属轮次 ID
        功能：列出指定轮次下的全部消息
        运行逻辑：按 turn_id 过滤，按轮内消息序号（turn_message_index）
          升序排列
        出参：list[Message] - 消息列表（可能为空列表）
        """
        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .filter_by(turn_id=turn_id)
                .order_by(MessageModel.turn_message_index.asc())
                .all()
            )
            return self._to_domain_list(models)

    def list_by_turn_ids(self, session_id: str, turn_ids: list[str]) -> list[Message]:
        """
        函数名：list_by_turn_ids
        入参：
          - session_id (str): 所属会话 ID
          - turn_ids (list[str]): 轮次 ID 列表
        功能：按轮次 ID 批量获取消息（用于一次性加载多个轮次的完整消息）
        运行逻辑：turn_ids 为空直接返回空列表；否则 outerjoin TurnModel
          拿到轮次序号，过滤 session_id 与 turn_id 在给定列表中的记录，
          按"轮次序号+轮内消息序号+创建时间"升序排列
        出参：list[Message] - 匹配到的消息列表
        """
        if not turn_ids:
            return []

        with self.db.get_session() as db_session:
            models = (
                db_session.query(MessageModel)
                .outerjoin(
                    TurnModel,
                    (TurnModel.id == MessageModel.turn_id)
                    & (TurnModel.session_id == MessageModel.session_id),
                )
                .filter(
                    MessageModel.session_id == session_id,
                    MessageModel.turn_id.in_(turn_ids),
                )
                .order_by(
                    TurnModel.turn_index.asc(),
                    MessageModel.turn_message_index.asc(),
                    MessageModel.created_at.asc(),
                )
                .all()
            )
            return self._to_domain_list(models)

    def update(self, message: Message, *, db_session=None) -> Message:
        """
        函数名：update
        入参：
          - message (Message): 携带最新字段值的消息领域对象（以 id 定位
            要更新的记录）
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：更新消息的流式状态、正文内容、附加数据、附件、更新/完成
          时间（典型用于流式生成过程中持续刷新消息内容）
        运行逻辑：
          1. 按 message.id 查询记录，不存在则抛出 NotFoundValueError
          2. 覆盖 stream_state（取枚举 value）/content_text/payload_json
          3. attachments 非空时序列化为 JSON 字符串写入
             attachments_json，否则置为 None
          4. 覆盖 updated_at/completed_at，flush + refresh 后返回最新状态
        出参：Message - 更新后的消息领域对象
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.update(message, db_session=managed_session)

        model = db_session.query(MessageModel).filter_by(id=message.id).first()
        if model is None:
            raise NotFoundValueError("消息不存在")

        model.stream_state = message.stream_state.value
        model.content_text = message.content_text
        model.payload_json = message.payload_json
        if message.attachments:
            model.attachments_json = json.dumps([att.model_dump(mode="json") for att in message.attachments])
        else:
            model.attachments_json = None
        model.updated_at = message.updated_at
        model.completed_at = message.completed_at
        db_session.flush()
        db_session.refresh(model)
        return self._to_domain(model)

    def next_turn_message_index(self, turn_id: str, *, db_session=None) -> int:
        """
        函数名：next_turn_message_index
        入参：
          - turn_id (str): 所属轮次 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：计算指定轮次下一条消息应使用的轮内顺序号
        运行逻辑：查询该轮次当前最大的 turn_message_index（无记录时视为
          0），返回其加一的结果
        出参：int - 下一条消息应使用的 turn_message_index
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.next_turn_message_index(turn_id, db_session=managed_session)

        current = (
            db_session.query(MessageModel.turn_message_index)
            .filter_by(turn_id=turn_id)
            .order_by(MessageModel.turn_message_index.desc())
            .limit(1)
            .scalar()
        ) or 0
        return current + 1

    def list_recent_seed_candidates(
        self,
        session_id: str,
        *,
        current_turn_id: str | None = None,
        limit: int = 12,
        scan_limit: int = 200,
        max_tool_traces: int = 20,
    ) -> list[Message]:
        """
        函数名：list_recent_seed_candidates
        入参：
          - session_id (str): 所属会话 ID
          - current_turn_id (str | None): 当前轮次 ID，传入时会从候选中
            排除该轮次自身产生的消息（避免把当前轮次的消息当作历史上下文）
          - limit (int): 最终返回的候选消息条数上限
          - scan_limit (int): 文本类消息（用户/助手消息）的扫描条数上限，
            默认 200，实际取 max(50, scan_limit)
          - max_tool_traces (int): 工具调用轨迹类消息的扫描条数上限，
            默认 20
        功能：为"生成对话上下文种子/摘要"场景挑选最近的候选消息，混合
          文本消息与已完成的工具调用轨迹
        运行逻辑：
          1. limit <= 0 时直接返回空列表
          2. 查询该会话内 message_type 为用户消息或助手消息、且
             content_text 非空的记录，可选排除 current_turn_id，按创建
             时间倒序取前 resolved_scan 条
          3. 查询该会话内 message_type 为工具调用轨迹（TOOL_TRACE）且
             stream_state 已完成（COMPLETED）的记录，同样可选排除
             current_turn_id，按创建时间倒序取前 max_tool_traces 条
          4. 合并两类结果，按 created_at 升序重新排序，再取末尾
             resolved_limit 条（即时间上最新的 limit 条候选）
        出参：list[Message] - 最多 limit 条候选消息，按时间升序排列
        """
        resolved_limit = max(0, int(limit)) if limit else 0
        resolved_scan = max(50, int(scan_limit)) if scan_limit else 200
        if resolved_limit <= 0:
            return []

        with self.db.get_session() as db_session:
            text_query = db_session.query(MessageModel).filter(
                MessageModel.session_id == session_id,
                MessageModel.message_type.in_(
                    [
                        MessageType.USER_MESSAGE.value,
                        MessageType.ASSISTANT_MESSAGE.value,
                    ]
                ),
                MessageModel.content_text != "",
            )
            if current_turn_id:
                text_query = text_query.filter(MessageModel.turn_id != current_turn_id)

            text_models = text_query.order_by(MessageModel.created_at.desc()).limit(resolved_scan).all()

            tool_trace_query = (
                db_session.query(MessageModel)
                .filter(
                    MessageModel.session_id == session_id,
                    MessageModel.message_type == MessageType.TOOL_TRACE.value,
                    MessageModel.stream_state == StreamState.COMPLETED.value,
                )
            )
            if current_turn_id:
                tool_trace_query = tool_trace_query.filter(
                    MessageModel.turn_id != current_turn_id
                )
            tool_trace_models = (
                tool_trace_query.order_by(MessageModel.created_at.desc())
                .limit(max_tool_traces)
                .all()
            )

            all_models = list(text_models) + list(tool_trace_models)
            all_models.sort(key=lambda m: m.created_at)
            all_models = all_models[-resolved_limit:]

            return self._to_domain_list(all_models)

    def delete_by_turn_ids(self, turn_ids: list[str], *, db_session=None) -> int:
        """
        函数名：delete_by_turn_ids
        入参：
          - turn_ids (list[str]): 待清理消息所属的轮次 ID 列表
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：按轮次 ID 批量删除其下全部消息（配合轮次回退/删除场景，
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
            db_session.query(MessageModel)
            .filter(MessageModel.turn_id.in_(turn_ids))
            .delete(synchronize_session=False)
        )
        db_session.flush()
        return int(deleted or 0)

    def get_user_message_by_turn(self, turn_id: str, *, db_session=None) -> Message | None:
        """
        函数名：get_user_message_by_turn
        入参：
          - turn_id (str): 所属轮次 ID
          - db_session: 外部传入的数据库会话，为空则内部自动创建
        功能：获取指定轮次中的用户消息（一个轮次通常以一条用户消息开始）
        运行逻辑：过滤 turn_id 匹配且 message_type 为用户消息
          （USER_MESSAGE）的记录，按轮内消息序号升序取第一条
        出参：Message | None - 找到则返回该轮次的用户消息，否则返回 None
        """
        if db_session is None:
            with self.db.get_session() as managed_session:
                return self.get_user_message_by_turn(turn_id, db_session=managed_session)

        model = (
            db_session.query(MessageModel)
            .filter_by(turn_id=turn_id, message_type=MessageType.USER_MESSAGE.value)
            .order_by(MessageModel.turn_message_index.asc())
            .first()
        )
        return self._to_domain(model)

    def from_payload(self, *, session_id: str, payload: dict) -> Message:
        """
        函数名：from_payload
        入参：
          - session_id (str): 所属会话 ID
          - payload (dict): 外部传入的消息构造数据字典，需包含
            message_id/turn_id/turn_message_index/role/message_type/
            display_mode 等键，可选包含 run_id/content_text/
            payload_json/attachment_ids
        功能：将外部（如 API 请求体）传入的原始字典数据组装为 Message
          领域对象（不涉及数据库读写，纯内存构造）
        运行逻辑：
          1. 内部工具函数 _coerce_payload_json 负责把 payload_json 规范化
             为 dict：本身是 dict 则直接用；是字符串则尝试 JSON 解析，
             解析失败或结果非 dict 时降级为空字典
          2. 解析 message_type；若为用户消息，流式状态直接置为已完成
             （COMPLETED，因为用户消息一次性提交无需流式生成），否则置
             为空闲（IDLE，等待后续流式内容填充）
          3. 若 payload 中带有 attachment_ids，逐个调用附件服务
             （attachment_service）按 session_id + 附件 ID 构建附件
             元数据对象，跳过构建失败（返回空）的附件
          4. 用整理好的字段构造并返回 Message 对象
        出参：Message - 构造完成的消息领域对象
        """
        def _coerce_payload_json(value: object) -> dict:
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except (TypeError, ValueError):
                    return {}
                return parsed if isinstance(parsed, dict) else {}
            return {}

        message_type = MessageType(payload["message_type"])
        if message_type == MessageType.USER_MESSAGE:
            stream_state = StreamState.COMPLETED
        else:
            stream_state = StreamState.IDLE

        # 处理附件 IDs - 转换为 MessageAttachment 对象
        attachments = []
        attachment_ids = payload.get("attachment_ids", [])
        if attachment_ids:
            attachment_service = get_attachment_service()
            for att_id in attachment_ids:
                attachment = attachment_service.build_attachment_metadata(session_id, att_id)
                if attachment:
                    attachments.append(attachment)

        return Message(
            id=payload["message_id"],
            session_id=session_id,
            turn_id=payload["turn_id"],
            run_id=payload.get("run_id"),
            turn_message_index=payload["turn_message_index"],
            role=payload["role"],
            message_type=message_type,
            stream_state=stream_state,
            display_mode=payload["display_mode"],
            content_text=payload.get("content_text", ""),
            payload_json=_coerce_payload_json(payload.get("payload_json")),
            attachments=attachments,
        )
