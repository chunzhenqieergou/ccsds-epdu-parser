"""
STMS 卫星遥测数据综合管理系统 — FastAPI 应用入口
=================================================
统一响应格式 { code, message, data }；CORS 跨域；路由注册；启动时初始化
数据库与接收服务。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表、启动数据接收服务"""
    init_db()
    from .receiver.manager import receiver_manager

    if settings.SIMULATOR_ENABLED:
        receiver_manager.start()
    yield
    from .receiver.manager import receiver_manager

    receiver_manager.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Vue3 + FastAPI + MySQL 全栈卫星遥测数据综合管理系统",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底异常处理：返回统一格式"""
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"服务器内部错误: {exc}", "data": None},
    )


# 路由注册
from .api import (  # noqa: E402
    auth,
    satellites,
    params,
    channels,
    commands,
    telemetry,
    statistics,
    alarms,
    export,
    system,
)

API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["认证"])
app.include_router(satellites.router, prefix=f"{API_PREFIX}/satellites", tags=["卫星配置"])
app.include_router(params.router, prefix=f"{API_PREFIX}/params", tags=["遥测参数"])
app.include_router(channels.router, prefix=f"{API_PREFIX}/channels", tags=["通道配置"])
app.include_router(commands.router, prefix=f"{API_PREFIX}/commands", tags=["遥控指令"])
app.include_router(telemetry.router, prefix=f"{API_PREFIX}/telemetry", tags=["遥测数据"])
app.include_router(statistics.router, prefix=f"{API_PREFIX}/statistics", tags=["统计分析"])
app.include_router(alarms.router, prefix=f"{API_PREFIX}/alarms", tags=["告警"])
app.include_router(export.router, prefix=f"{API_PREFIX}/export", tags=["数据导出"])
app.include_router(system.router, prefix=f"{API_PREFIX}/system", tags=["系统管理"])


@app.get("/api/v1/health")
def health():
    return {"code": 0, "message": "ok", "data": {"status": "running", "version": settings.APP_VERSION}}


@app.get("/")
def root():
    return {"code": 0, "message": settings.APP_NAME, "data": {"docs": "/docs"}}