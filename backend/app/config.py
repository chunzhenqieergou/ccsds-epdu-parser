"""
STMS 配置模块
=============
集中管理所有运行配置：数据库连接、JWT、CORS、接收服务参数。
支持通过环境变量或 .env 文件覆盖默认值。
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 应用
    APP_NAME: str = "STMS 卫星遥测数据综合管理系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 数据库
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "stms"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    # JWT 认证
    JWT_SECRET_KEY: str = "stms-dev-secret-key-change-in-production-3f9a1c2b"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 小时
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 数据接收 / 模拟器
    SIMULATOR_ENABLED: bool = True
    SIMULATOR_INTERVAL_MS: int = 1000       # 模拟帧生成间隔（毫秒），实时刷新率 >=1Hz
    SIMULATOR_CYCLE: int = 200              # 模拟曲线周期（帧数）
    RECEIVER_ENABLED: bool = True           # 真实数据接收（TCP/UDP）开关
    RECEIVER_HOST: str = "127.0.0.1"
    RECEIVER_PORT: int = 9001                # Socket 接收服务器 TCP 端口（CCSDS CADU 定长帧）
    RECEIVER_UDP_PORT: int = 9002           # UDP 接收服务器端口（1553B/CAN/RS422 单报文帧）

    # 时序数据库（方案 4.2：TDengine / MongoDB，本项目实现 MongoDB + MySQL 回退）
    TSDB_BACKEND: str = "mongodb"           # mongodb | mysql
    MONGODB_URI: str = "mongodb://127.0.0.1:27017"
    MONGODB_DB: str = "stms"
    MONGODB_COLLECTION: str = "telemetry_data"
    MONGODB_TTL_DAYS: int = 90              # TTL 自动清理：0 表示不启用

    # CORS：允许的前端来源
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()