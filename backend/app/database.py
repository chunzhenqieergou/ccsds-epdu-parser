"""
数据库引擎与会话管理
====================
SQLAlchemy 2.0 风格：关联式会话 + 显式 Session 依赖注入。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

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
    """创建所有表（import models 确保模型已注册）"""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)