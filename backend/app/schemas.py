"""
Pydantic v2 数据模型（Schema）
============================
定义全部 API 的请求/响应数据结构，是前后端联调的契约基准。
所有响应统一包装为 { code, message, data }。
"""
from datetime import datetime, date
from typing import Any, Generic, TypeVar, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 统一响应结构
# ---------------------------------------------------------------------------
class ApiResponse(BaseModel, Generic[T]):
    """统一响应格式 { code, message, data }"""
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


class PageResult(BaseModel, Generic[T]):
    """分页结果"""
    total: int
    page: int
    page_size: int
    items: list[T]


# ---------------------------------------------------------------------------
# 帧解析详情（数据接收与解析模块）
# ---------------------------------------------------------------------------
class ParseFrameRequest(BaseModel):
    """帧解析请求：协议类型 + 十六进制帧"""
    protocol_type: str = Field(..., description="协议类型: CCSDS/1553B/CAN/RS422")
    hex_data: str = Field(..., description="帧十六进制字符串（可含空格/换行）")


def ok(data: Any = None, message: str = "ok", code: int = 0) -> ApiResponse:
    return ApiResponse(code=code, message=message, data=data)


# ---------------------------------------------------------------------------
# 用户 / 认证
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str
    role: str = Field(default="observer", pattern="^(admin|operator|observer)$")
    email: Optional[str] = None
    remark: Optional[str] = None

    @field_validator("confirm_password")
    @classmethod
    def _pw_match(cls, v: str, info) -> str:
        if v != info.data.get("password"):
            raise ValueError("两次输入的密码不一致")
        return v


class UserLogin(BaseModel):
    username: str
    password: str
    remember: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
    status: int
    email: Optional[str] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class UserUpdate(BaseModel):
    role: Optional[str] = Field(default=None, pattern="^(admin|operator|observer)$")
    status: Optional[int] = Field(default=None, ge=0, le=1)
    email: Optional[str] = None
    remark: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


# ---------------------------------------------------------------------------
# 卫星配置
# ---------------------------------------------------------------------------
# 状态语义：前端使用业务字符串三态，数据库存储整型。
SATELLITE_STATUS_STR_TO_INT = {"active": 1, "standby": 2, "retired": 3}
SATELLITE_STATUS_INT_TO_STR = {1: "active", 2: "standby", 3: "retired"}


def _sat_status_to_int(v: Any) -> int:
    """把前端字符串状态映射为数据库整型（兼容已有整型直接透传）"""
    if isinstance(v, bool) or isinstance(v, int):
        return int(v)
    if isinstance(v, str):
        mapped = SATELLITE_STATUS_STR_TO_INT.get(v.strip())
        if mapped is None:
            raise ValueError(f"非法卫星状态: {v}")
        return mapped
    return 1


def _sat_status_to_str(v: Any) -> str:
    """把数据库整型状态映射回前端字符串三态"""
    if isinstance(v, str):
        return v if v in SATELLITE_STATUS_STR_TO_INT else "active"
    return SATELLITE_STATUS_INT_TO_STR.get(v, "active")


class SatelliteBase(BaseModel):
    name: str = Field(max_length=128)
    code: str = Field(max_length=64)
    orbit_type: str = Field(default="LEO", max_length=64)
    launch_date: Optional[date] = None
    description: Optional[str] = None


class SatelliteCreate(SatelliteBase):
    status: int = 1

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: object) -> object:
        return _sat_status_to_int(v)


class SatelliteUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    code: Optional[str] = Field(default=None, max_length=64)
    orbit_type: Optional[str] = Field(default=None, max_length=64)
    launch_date: Optional[date] = None
    description: Optional[str] = None
    status: Optional[int] = Field(default=None, ge=0, le=3)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status_upd(cls, v: object) -> object:
        if v is None:
            return None
        return _sat_status_to_int(v)


class SatelliteOut(SatelliteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    created_at: Optional[datetime] = None
    param_count: int = 0

    @field_validator("status", mode="before")
    @classmethod
    def _out_status(cls, v: object) -> str:
        return _sat_status_to_str(v)


# ---------------------------------------------------------------------------
# 遥测参数
# ---------------------------------------------------------------------------
class TelemetryParamBase(BaseModel):
    satellite_id: int
    param_code: str = Field(max_length=32)
    name: str = Field(max_length=128)
    description: Optional[str] = Field(default=None, max_length=255)
    subsystem: str = Field(default="通用", max_length=64)
    data_type: str = Field(default="float", max_length=32)
    unit: str = Field(default="", max_length=32)
    formula: Optional[str] = Field(default=None, max_length=255)
    raw_bits: int = Field(default=16, ge=0, le=64)
    scale: float = 1.0
    offset: float = 0.0
    precision: int = Field(default=2, ge=0, le=8)
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    enabled: int = 1
    order_no: int = 0


class TelemetryParamCreate(TelemetryParamBase):
    pass


class TelemetryParamUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=255)
    subsystem: Optional[str] = Field(default=None, max_length=64)
    data_type: Optional[str] = Field(default=None, max_length=32)
    unit: Optional[str] = Field(default=None, max_length=32)
    formula: Optional[str] = Field(default=None, max_length=255)
    raw_bits: Optional[int] = Field(default=None, ge=0, le=32)
    scale: Optional[float] = None
    offset: Optional[float] = None
    precision: Optional[int] = Field(default=None, ge=0, le=8)
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    enabled: Optional[int] = None
    order_no: Optional[int] = None


class TelemetryParamOut(TelemetryParamBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    satellite_name: Optional[str] = None


class ParamImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str] = []


# ---------------------------------------------------------------------------
# 通道配置
# ---------------------------------------------------------------------------
class ChannelBase(BaseModel):
    satellite_id: int
    name: str = Field(max_length=128)
    protocol_type: str = Field(pattern="^(CCSDS|1553B|CAN|RS422)$")
    ip: str = Field(default="127.0.0.1", max_length=64)
    port: int = Field(default=9001, ge=0, le=65535)
    baud_rate: int = Field(default=460800, ge=0)
    frame_format: Optional[str] = Field(default=None, max_length=64)
    running: int = 0
    remark: Optional[str] = Field(default=None, max_length=255)


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    protocol_type: Optional[str] = Field(default=None, pattern="^(CCSDS|1553B|CAN|RS422)$")
    ip: Optional[str] = Field(default=None, max_length=64)
    port: Optional[int] = Field(default=None, ge=0, le=65535)
    baud_rate: Optional[int] = Field(default=None, ge=0)
    frame_format: Optional[str] = Field(default=None, max_length=64)
    running: Optional[int] = Field(default=None, ge=0, le=1)
    remark: Optional[str] = Field(default=None, max_length=255)


class ChannelOut(ChannelBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    satellite_name: Optional[str] = None


# ---------------------------------------------------------------------------
# 遥测数据 / 实时
# ---------------------------------------------------------------------------
class TelemetryPoint(BaseModel):
    ts: datetime
    param_code: str
    raw_value: int
    value: float
    quality: str


class TelemetryQuery(BaseModel):
    satellite_id: Optional[int] = None
    param_codes: list[str] = []
    channel_ids: list[int] = []
    start: datetime
    end: datetime
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=1000)
    sampling: Optional[str] = Field(default=None, pattern="^(full|auto)$")
    max_points: int = Field(default=1000, ge=100, le=50000)


class RealtimePoint(BaseModel):
    ts: datetime
    param_code: str
    value: float
    raw_value: int
    unit: str = ""
    quality: str = "GOOD"


class FrameOut(BaseModel):
    id: int
    ts: datetime
    satellite_id: int
    channel_id: int
    protocol_type: str
    apid: int
    raw_hex: str
    frame_size: int


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
class BasicStats(BaseModel):
    param_code: str
    count: int
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    variance: Optional[float] = None
    std: Optional[float] = None
    diff: Optional[float] = None


class TrendResult(BaseModel):
    param_code: str
    slope: float
    trend: str
    last_value: float
    first_value: float
    change_percent: float


class Anomaly(BaseModel):
    ts: datetime
    param_code: str
    value: float
    type: str
    threshold: float


class PeriodCompare(BaseModel):
    param_code: str
    period_name: str
    mean: Optional[float] = None
    max: Optional[float] = None
    min: Optional[float] = None
    std: Optional[float] = None


class CompareResult(BaseModel):
    param_code: str
    periods: list[PeriodCompare] = []
    delta_mean: Optional[float] = None


class StatisticsQuery(BaseModel):
    """POST /statistics/* 通用请求体"""
    param_code: str
    satellite_id: Optional[int] = None
    start: Optional[str] = None
    end: Optional[str] = None
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None


class CompareQuery(BaseModel):
    """POST /statistics/compare 请求体"""
    param_code: str
    satellite_id: Optional[int] = None
    period1_start: Optional[str] = None
    period1_end: Optional[str] = None
    period2_start: Optional[str] = None
    period2_end: Optional[str] = None


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
class ExportRequest(BaseModel):
    """POST /export/* 通用请求体"""
    start: str
    end: str
    param_codes: list[str]
    channel_ids: Optional[list[int]] = None


# ---------------------------------------------------------------------------
# 告警
# ---------------------------------------------------------------------------
class AlarmCreate(BaseModel):
    param_id: int
    alarm_type: str = Field(default="threshold", max_length=32)
    threshold: Optional[float] = None
    actual_value: float
    level: str = Field(default="WARN", max_length=16)
    message: Optional[str] = Field(default=None, max_length=255)


class AlarmHandle(BaseModel):
    status: int = Field(default=1, ge=0, le=1)
    note: Optional[str] = Field(default=None, max_length=255)


class AlarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    param_id: int
    alarm_type: str
    threshold: Optional[float] = None
    actual_value: float
    level: str
    status: int
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    handled_by: Optional[int] = None
    handle_note: Optional[str] = None
    handled_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 系统管理
# ---------------------------------------------------------------------------
class RoleOut(BaseModel):
    name: str
    label: str
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    permissions: Optional[list[str]] = None


class OperationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    target: Optional[str] = None
    detail: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None
