"""
数据库引擎与会话管理
====================
SQLAlchemy 2.0 风格：关联式会话 + 显式 Session 依赖注入。
"""
import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)

# pool_pre_ping 防止连接失效, pool_recycle 处理 MySQL wait_timeout
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""


def get_db():
    """FastAPI 依赖：提供数据库会话并保证关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """同步数据库结构：优先使用 Alembic 迁移，失败时回退 create_all 建表。"""
    from . import models  # noqa: F401

    try:
        if _run_alembic_migrations():
            return
    except Exception:
        logger.exception("Alembic 迁移执行失败，回退到 create_all 建表")

    Base.metadata.create_all(bind=engine)


def _run_alembic_migrations() -> bool:
    """通过 Alembic 同步数据库结构，返回是否已由迁移接管。

    兼容三种场景：
      1. 全新数据库（无任何表）         -> alembic upgrade head 建全量表
      2. 旧库（有表但无 alembic_version）-> 先 stamp head 再 upgrade（幂等）
      3. 已由迁移管理的库               -> alembic upgrade head 应用待执行迁移
    """
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        logger.warning("未安装 alembic，跳过数据库迁移（仅使用 create_all 建表）")
        return False

    from sqlalchemy import inspect

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))

    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())

    if not tables:
        command.upgrade(cfg, "head")
    elif "alembic_version" not in tables:
        command.stamp(cfg, "head")
        command.upgrade(cfg, "head")
    else:
        command.upgrade(cfg, "head")
    return True
