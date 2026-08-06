"""
种子数据初始化脚本
===================
幂等运行：建表、创建默认用户、示例卫星/参数/通道。
用法: python scripts/seed.py（在 backend 目录下执行）
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal, Base, engine
from app import models
from app.security import hash_password
from sqlalchemy import text


def seed_users(db: SessionLocal) -> None:
    """创建管理员、操作员、观察员账号（不存在才创建）"""
    users_data = [
        {
            "username": "admin",
            "password": "admin123",
            "role": "admin",
            "email": "admin@stms.local",
            "remark": "系统管理员",
        },
        {
            "username": "operator",
            "password": "operator123",
            "role": "operator",
            "email": "operator@stms.local",
            "remark": "操作员",
        },
        {
            "username": "observer",
            "password": "observer123",
            "role": "observer",
            "email": "observer@stms.local",
            "remark": "观察员",
        },
    ]
    for u in users_data:
        existing = db.query(models.User).filter(
            models.User.username == u["username"]
        ).first()
        if existing:
            continue
        user = models.User(
            username=u["username"],
            password_hash=hash_password(u["password"]),
            role=u["role"],
            email=u["email"],
            remark=u["remark"],
        )
        db.add(user)
    db.commit()
    print(f"  用户种子: 已检查 {len(users_data)} 个账号")


def seed_satellite(db: SessionLocal) -> None:
    """创建示例卫星、通道、遥测参数（按 code 判重）"""
    # --- 卫星 ---
    sat = db.query(models.Satellite).filter(
        models.Satellite.code == "TZ-1"
    ).first()
    if sat is None:
        sat = models.Satellite(
            name="天舟一号试验星",
            code="TZ-1",
            orbit_type="LEO",
            launch_date=None,
            description="天舟一号试验卫星，用于验证在轨通信与测控技术",
            status=1,
        )
        db.add(sat)
        db.commit()
        db.refresh(sat)
        print(f"  卫星: {sat.name} ({sat.code}) — 新建")
    else:
        print(f"  卫星: {sat.name} ({sat.code}) — 已存在，跳过")

    # --- 通道 ---
    channels_data = [
        {
            "name": "CCSDS主通道",
            "protocol_type": "CCSDS",
            "ip": "127.0.0.1",
            "port": 9001,
            "baud_rate": 460800,
            "frame_format": "CADU",
            "running": 1,
            "remark": "CCSDS协议TCP接收通道",
        },
        {
            "name": "CAN模拟通道",
            "protocol_type": "CAN",
            "ip": "127.0.0.1",
            "port": 9002,
            "baud_rate": 500000,
            "frame_format": "CAN 2.0B",
            "running": 0,
            "remark": "CAN总线模拟通道",
        },
    ]
    ch_count = 0
    for ch_data in channels_data:
        existing = db.query(models.Channel).filter(
            models.Channel.satellite_id == sat.id,
            models.Channel.name == ch_data["name"],
        ).first()
        if existing:
            continue
        ch_data["satellite_id"] = sat.id
        db.add(models.Channel(**ch_data))
        ch_count += 1
    db.commit()
    print(f"  通道: 新增 {ch_count} 条")

    # --- 遥测参数（至少 15 个，覆盖 4 个分系统） ---
    params_data = [
        # === 姿态控制 ===
        {"param_code": "P001", "name": "俯仰角", "subsystem": "姿态控制",
         "data_type": "float", "unit": "°", "scale": 0.01, "offset": -180.0,
         "raw_bits": 16, "threshold_min": -90.0, "threshold_max": 90.0,
         "description": "卫星俯仰姿态角"},
        {"param_code": "P002", "name": "偏航角", "subsystem": "姿态控制",
         "data_type": "float", "unit": "°", "scale": 0.01, "offset": -180.0,
         "raw_bits": 16, "threshold_min": -90.0, "threshold_max": 90.0,
         "description": "卫星偏航姿态角"},
        {"param_code": "P003", "name": "滚动角", "subsystem": "姿态控制",
         "data_type": "float", "unit": "°", "scale": 0.01, "offset": -180.0,
         "raw_bits": 16, "threshold_min": -90.0, "threshold_max": 90.0,
         "description": "卫星滚动姿态角"},
        {"param_code": "P004", "name": "角速度X", "subsystem": "姿态控制",
         "data_type": "float", "unit": "°/s", "scale": 0.001, "offset": 0.0,
         "raw_bits": 16, "threshold_min": -5.0, "threshold_max": 5.0,
         "description": "X轴角速度"},
        # === 电源 ===
        {"param_code": "P005", "name": "母线电压", "subsystem": "电源",
         "data_type": "float", "unit": "V", "scale": 0.01, "offset": 0.0,
         "raw_bits": 16, "threshold_min": 24.0, "threshold_max": 32.0,
         "description": "电源母线电压"},
        {"param_code": "P006", "name": "母线电流", "subsystem": "电源",
         "data_type": "float", "unit": "A", "scale": 0.01, "offset": 0.0,
         "raw_bits": 16, "threshold_min": 0.0, "threshold_max": 50.0,
         "description": "电源母线电流"},
        {"param_code": "P007", "name": "电池电压", "subsystem": "电源",
         "data_type": "float", "unit": "V", "scale": 0.01, "offset": 0.0,
         "raw_bits": 16, "threshold_min": 22.0, "threshold_max": 30.0,
         "description": "蓄电池组电压"},
        {"param_code": "P008", "name": "电池温度", "subsystem": "电源",
         "data_type": "float", "unit": "°C", "scale": 0.1, "offset": -50.0,
         "raw_bits": 16, "threshold_min": -20.0, "threshold_max": 60.0,
         "description": "蓄电池温度"},
        {"param_code": "P009", "name": "太阳能板功率", "subsystem": "电源",
         "data_type": "float", "unit": "W", "scale": 0.1, "offset": 0.0,
         "raw_bits": 16, "threshold_min": 0.0, "threshold_max": 2000.0,
         "description": "太阳能帆板输出功率"},
        # === 热控 ===
        {"param_code": "P010", "name": "舱内温度", "subsystem": "热控",
         "data_type": "float", "unit": "°C", "scale": 0.1, "offset": -50.0,
         "raw_bits": 16, "threshold_min": 15.0, "threshold_max": 40.0,
         "description": "密封舱内部温度"},
        {"param_code": "P011", "name": "散热板温度", "subsystem": "热控",
         "data_type": "float", "unit": "°C", "scale": 0.1, "offset": -50.0,
         "raw_bits": 16, "threshold_min": -40.0, "threshold_max": 80.0,
         "description": "散热板表面温度"},
        {"param_code": "P012", "name": "加热器状态", "subsystem": "热控",
         "data_type": "uint8", "unit": "", "scale": 1.0, "offset": 0.0,
         "raw_bits": 8, "threshold_min": 0.0, "threshold_max": 1.0,
         "description": "加热器开关状态(0=关 1=开)"},
        # === 载荷 ===
        {"param_code": "P013", "name": "载荷工作电流", "subsystem": "载荷",
         "data_type": "float", "unit": "A", "scale": 0.001, "offset": 0.0,
         "raw_bits": 16, "threshold_min": 0.0, "threshold_max": 5.0,
         "description": "有效载荷工作电流"},
        {"param_code": "P014", "name": "载荷温度", "subsystem": "载荷",
         "data_type": "float", "unit": "°C", "scale": 0.1, "offset": -50.0,
         "raw_bits": 16, "threshold_min": -20.0, "threshold_max": 50.0,
         "description": "有效载荷工作温度"},
        {"param_code": "P015", "name": "数据传输速率", "subsystem": "载荷",
         "data_type": "int16", "unit": "kbps", "scale": 1.0, "offset": 0.0,
         "raw_bits": 16, "threshold_min": 0.0, "threshold_max": 10240.0,
         "description": "载荷数据下行速率"},
        # === 额外参数 ===
        {"param_code": "P016", "name": "姿态控制模式", "subsystem": "姿态控制",
         "data_type": "uint8", "unit": "", "scale": 1.0, "offset": 0.0,
         "raw_bits": 8, "description": "0=惯性 1=对地 2=对日"},
        {"param_code": "P017", "name": "放电深度", "subsystem": "电源",
         "data_type": "float", "unit": "%", "scale": 0.1, "offset": 0.0,
         "raw_bits": 16, "threshold_min": 0.0, "threshold_max": 80.0,
         "description": "蓄电池放电深度百分比"},
        {"param_code": "P018", "name": "载荷开关状态", "subsystem": "载荷",
         "data_type": "uint8", "unit": "", "scale": 1.0, "offset": 0.0,
         "raw_bits": 8, "threshold_min": 0.0, "threshold_max": 1.0,
         "description": "载荷电源开关(0=关 1=开)"},
    ]
    param_count = 0
    for i, pd in enumerate(params_data):
        existing = db.query(models.TelemetryParam).filter(
            models.TelemetryParam.satellite_id == sat.id,
            models.TelemetryParam.param_code == pd["param_code"],
        ).first()
        if existing:
            continue
        pd["satellite_id"] = sat.id
        pd.setdefault("enabled", 1)
        pd.setdefault("order_no", i + 1)
        pd.setdefault("precision", 2)
        pd.setdefault("formula", None)
        pd.setdefault("threshold_min", None)
        pd.setdefault("threshold_max", None)
        db.add(models.TelemetryParam(**pd))
        param_count += 1
    db.commit()
    print(f"  遥测参数: 新增 {param_count} 条（覆盖 {len(params_data)} 个）")


def main() -> None:
    """主函数：建表并写入种子数据"""
    print("=" * 56)
    print("  STMS 种子数据初始化")
    print("=" * 56)
    print("重建数据库表 ...")
    # 确保 models 已注册到 Base.metadata
    import app.models as _  # noqa: F811
    # 禁用外键检查以避免旧遗留约束导致 drop 失败
    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.commit()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
    print("  表结构已就绪")
    db = SessionLocal()
    try:
        print("写入种子数据 ...")
        seed_users(db)
        seed_satellite(db)
        print("-" * 56)
        print("  种子数据初始化完成！")
    finally:
        db.close()


if __name__ == "__main__":
    main()
