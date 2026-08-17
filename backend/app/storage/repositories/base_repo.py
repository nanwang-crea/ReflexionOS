"""
文件功能：Repository 模式的通用泛型基类
文件描述：为各业务 Repository（项目/会话/轮次/运行/消息等）提供统一的
    "ORM 模型 -> Pydantic 领域模型" 转换能力，避免每个子类重复实现相同的
    转换逻辑。
核心逻辑：通过 TypeVar 泛型参数 DomainModel 绑定具体的 Pydantic 领域模型
    类型，子类在 __init__ 中传入该类型后，即可复用 _to_domain /
    _to_domain_list 完成单条 / 批量转换。
"""
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.storage.database import Database

DomainModel = TypeVar("DomainModel", bound=BaseModel)


class BaseRepository(Generic[DomainModel]):
    """
    Repository 泛型基类，所有具体业务 Repository 均继承自此类。
    """

    def __init__(self, db: "Database", domain_cls: type[DomainModel]):
        """
        函数名：__init__
        入参：
          - db (Database): 数据库访问入口，封装了会话（Session）的获取
          - domain_cls (type[DomainModel]): 该 Repository 对应的 Pydantic
            领域模型类，用于后续 ORM 模型到领域模型的转换
        功能：初始化 Repository，保存数据库入口和领域模型类型引用
        运行逻辑：直接将传入的 db 和 domain_cls 挂载为实例属性
        出参：无
        """
        self.db = db
        self._domain_cls = domain_cls

    def _to_domain(self, model) -> DomainModel | None:
        """
        函数名：_to_domain
        入参：
          - model: 单条 SQLAlchemy ORM 模型实例，可为 None
        功能：将单条 ORM 模型转换为对应的 Pydantic 领域模型
        运行逻辑：若入参为 None 直接返回 None；否则调用
          domain_cls.model_validate 从 ORM 对象属性构造领域模型
        出参：DomainModel | None - 转换后的领域模型实例，输入为空时返回 None
        """
        if model is None:
            return None
        return self._domain_cls.model_validate(model)

    def _to_domain_list(self, models) -> list[DomainModel]:
        """
        函数名：_to_domain_list
        入参：
          - models: SQLAlchemy ORM 模型实例的可迭代集合（如查询结果列表）
        功能：批量将 ORM 模型列表转换为 Pydantic 领域模型列表
        运行逻辑：对集合中每个元素调用 domain_cls.model_validate 逐一转换
        出参：list[DomainModel] - 转换后的领域模型列表
        """
        return [self._domain_cls.model_validate(m) for m in models]
