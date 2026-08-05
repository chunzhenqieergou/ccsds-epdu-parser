"""
STMS 数据库 ORM 模型
====================
对应设计方案第四章「数据库设计」中的 MySQL 关系型数据表。

表清单：
  users               用户表（含角色）
  satellites          卫星表
  telemetry_params    遥测参数表（含转换公式、告警阈值）
  remote_commands     遥控指令表
  channels            数据接收通道表
  telemetry_data      遥测时序数据表（原方案用 TDengine/MongoDB，因环境限制统一存 MySQL）
  telemetry_frames    遥测原始帧表（整帧十六进制源码，用于「整帧显示」）
  alarms              告警记录表
  operation_logs      操作日志表
"""
from datetime import datetime, date

from sqlalchemy import (
String, Integer, BigInteger, Float, Boolean, Text, DateTime,
    Date, ForeignKey, Index, UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ---------------------------------------------------------------
# 角色与状态枚举常量
# ---------------------------------------------------------------
ROLE_ADMIN = "admin"        # 管理员
ROLE_OPERATOR = "operator"  # 操作员
ROLE_OBSERVER = "observer"  # 观察员
ALL_ROLES = [ROLE_ADMIN, ROLE_OPERATOR, ROLE_OBSERVER]

# 协议类型
PROTOCOL_CCSDS = "CCSDS"
PROTOCOL_1553B = "1553B"
PROTOCOL_CAN = "CAN"
PROTOCOL_RS422 = "RS422"
ALL_PROTOCOLS = [PROTOCOL_CCSDS, PROTOCOL_1553B, PROTOCOL_CAN, PROTOCOL_RS422]

# 数据质量标志
QUALITY_GOOD = "GOOD"
QUALITY_BAD = "BAD"
QUALITY_SUSPECT = "SUSPECT"
ALL_QUALITY = [QUALITY_GOOD, QUALITY_BAD, QUALITY_SUSPECT]


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(SAEnum(*ALL_ROLES), nullable=False, default=ROLE_OBSERVER)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 1=启用 0=禁用
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    operation_logs: Mapped[list["OperationLog"]] = relationship(back_populates="user")


class Satellite(Base):
    """卫星表"""
    __tablename__ = "satellites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="卫星名称")
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False, comment="卫星代号")
    orbit_type: Mapped[str] = mapped_column(String(64), nullable=False, default="LEO", comment="轨道类型")
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="发射日期")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="1=在轨/AIT 2=停用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    params: Mapped[list["TelemetryParam"]] = relationship(back_populates="satellite",
                                                          cascade="all, delete-orphan")
    channels: Mapped[list["Channel"]] = relationship(back_populates="satellite",
                                                     cascade="all, delete-orphan")
    commands: Mapped[list["RemoteCommand"]] = relationship(back_populates="satellite",
                                                           cascade="all, delete-orphan")


class TelemetryParam(Base):
    """遥测参数定义表"""
    __tablename__ = "telemetry_params"
    __table_args__ = (UniqueConstraint("satellite_id", "param_code", name="uk_sat_param"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    satellite_id: Mapped[int] = mapped_column(ForeignKey("satellites.id"), index=True, nullable=False)
    param_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="参数代号")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="参数名称")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subsystem: Mapped[str] = mapped_column(String(64), nullable=False, default="通用",
                                            comment="所属分系统，用于参数树：姿态控制/电源/热控等")
    data_type: Mapped[str] = mapped_column(String(32), nullable=False, default="float",
                                 comment="数据类型: uint8/int16/float/string/enum")
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="工程单位")
    formula: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="转换公式(源码→工程值)")
    raw_bits: Mapped[int] = mapped_column(Integer, nullable=False, default=16, comment="源码位宽")
    scale: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, comment="线性系数")
    offset: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="线性偏移")
    precision: Mapped[int] = mapped_column(Integer, nullable=False, default=2, comment="工程值小数位")
    threshold_min: Mapped[float | None] = mapped_column(Float, nullable=True, comment="告警下限")
    threshold_max: Mapped[float | None] = mapped_column(Float, nullable=True, comment="告警上限")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="1=启用 0=停用")
    order_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="显示排序")

    satellite: Mapped["Satellite"] = relationship(back_populates="params")


class Channel(Base):
    """数据接收通道表"""
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    satellite_id: Mapped[int] = mapped_column(ForeignKey("satellites.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="通道名称")
    protocol_type: Mapped[str] = mapped_column(SAEnum(*ALL_PROTOCOLS), nullable=False,
                                               default=PROTOCOL_CCSDS, comment="协议类型")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="127.0.0.1")
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=9001)
    baud_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=460800, comment="波特率(串口)")
    frame_format: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="帧格式描述")
    running: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="1=接收中 0=停止")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)

    satellite: Mapped["Satellite"] = relationship(back_populates="channels")


class RemoteCommand(Base):
    """遥控指令表"""
    __tablename__ = "remote_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    satellite_id: Mapped[int] = mapped_column(ForeignKey("satellites.id"), index=True, nullable=False)
    cmd_code: Mapped[str] = mapped_column(String(32), nullable=False, comment="指令代号")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="指令名称")
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="参数模板(JSON)")
    forbidden: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="1=禁止发送(危险指令)")
    permission_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                        comment="所需权限等级 0=观察员 1=操作员 2=管理员")

    satellite: Mapped["Satellite"] = relationship(back_populates="commands")


class TelemetryData(Base):
    """遥测时序数据表（原方案 TDengine/MongoDB，统一用 MySQL 存储）"""
    __tablename__ = "telemetry_data"
    # ts + param_code 复合索引，支持按参数+时间高效查询
    __table_args__ = (
        Index("idx_ts_param", "ts", "param_code"),
        Index("idx_param_ts", "param_code", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment="时间戳")
    satellite_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False, comment="冗余卫星ID，便于按库聚合")
    channel_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="接收通道ID")
    param_code: Mapped[str] = mapped_column(String(32), nullable=False, comment="参数代号")
    raw_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="源码整型值")
    value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="工程值")
    quality: Mapped[str] = mapped_column(SAEnum(*ALL_QUALITY), nullable=False, default=QUALITY_GOOD)


class TelemetryFrame(Base):
    """遥测原始帧表：保存整帧十六进制源码，供「整帧显示」功能"""
    __tablename__ = "telemetry_frames"
    __table_args__ = (Index("idx_frame_ts", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    satellite_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    protocol_type: Mapped[str] = mapped_column(String(32), nullable=False)
    apid: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="CCSDS APID，其它协议为0")
    raw_hex: Mapped[str] = mapped_column(Text, nullable=False, comment="整帧十六进制字符串")

    @property
    def frame_size(self) -> int:
        return len(self.raw_hex.replace(" ", "")) // 2 if self.raw_hex else 0


class Alarm(Base):
    """告警记录表"""
    __tablename__ = "alarms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    param_id: Mapped[int] = mapped_column(ForeignKey("telemetry_params.id"), index=True, nullable=False)
    alarm_type: Mapped[str] = mapped_column(String(32), nullable=False, default="threshold", comment="告警类型")
    threshold: Mapped[float] = mapped_column(Float, nullable=True, comment="触发阈值")
    actual_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="实际值")
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="WARN",
                             comment="级别: INFO/WARN/CRITICAL")
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="0=未处理 1=已处理")
    message: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="告警说明")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, comment="处理人ID")
    handle_note: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="处理备注")
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OperationLog(Base):
    """操作日志表"""
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="冗余用户名")
    action: Mapped[str] = mapped_column(String(64), nullable=False, comment="操作动作")
    target: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="操作对象")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="详情(JSON)")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    user: Mapped["User"] = relationship(back_populates="operation_logs")