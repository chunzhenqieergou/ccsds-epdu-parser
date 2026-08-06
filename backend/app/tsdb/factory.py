"""
时序存储后端工厂
===============
按配置选择后端：TSDB_BACKEND=mongodb 时优先 MongoDB（不可用自动回退 MySQL），
其余情况使用 MySQL。模块级单例，避免重复建立连接。
"""
import logging
from functools import lru_cache

from ..config import settings
from .base import TimeSeriesStore

logger: logging.Logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_tsdb_store() -> TimeSeriesStore:
    """返回时序存储后端单例。

    - TSDB_BACKEND == "mongodb": 尝试 MongoDB，health() 失败则回退 MySQL
    - 其他值: 使用 MySQL
    """
    backend_name = (settings.TSDB_BACKEND or "mysql").lower()

    if backend_name == "mongodb":
        from .mongodb_store import MongoDBTimeSeriesStore
        try:
            store = MongoDBTimeSeriesStore()
            if store.health():
                logger.info("时序存储后端: MongoDB (%s)", settings.MONGODB_URI)
                return store
            logger.warning("MongoDB 未就绪（%s），回退 MySQL 时序后端", settings.MONGODB_URI)
        except Exception:
            logger.exception("初始化 MongoDB 时序后端失败，回退 MySQL")

    from .mysql_store import MySQLTimeSeriesStore
    logger.info("时序存储后端: MySQL")
    return MySQLTimeSeriesStore()
