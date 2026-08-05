"""
测试脚本: 验证数据接收流水线（模拟器→解析→入库→SSE 推送）

用法（在 backend 目录下执行）:
    python -X utf8 scripts/run_receiver_test.py

说明:
  1. 初始化数据库表
  2. 启动种子数据（确保有 satellite、channel、telemetry_params）
  3. 启动 ReceiverManager → 运行模拟器约 4 秒
  4. 查询 telemetry_data、telemetry_frames 表
  5. 断言数据行数 > 0（证明流水线正常入库）
  6. 停止 ReceiverManager 并输出结果
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app.config import settings

# ---- 种子数据（幂等） ----
from app import models
from app.security import hash_password


def seed_minimal() -> None:
    """确保至少存在一颗卫星、一个参数、各协议通道，避免模拟器无数据可生成。"""
    db = SessionLocal()
    try:
        # 卫星
        sat = db.query(models.Satellite).filter(
            models.Satellite.code == "TZ-TEST"
        ).first()
        if sat is None:
            sat = models.Satellite(
                name="测试卫星",
                code="TZ-TEST",
                orbit_type="LEO",
                status=1,
            )
            db.add(sat)
            db.commit()
            db.refresh(sat)
            print(f"  + 创建卫星: {sat.name} (id={sat.id})")

        # 通道（四种协议各一）
        ch_protos = {
            "CCSDS": ("CCSDS主通道", 9001, "CADU"),
            "1553B": ("1553B通道", 9011, "1553B"),
            "CAN": ("CAN通道", 9002, "CAN 2.0B"),
            "RS422": ("RS422通道", 9021, "RS-422"),
        }
        for proto, (name, port, fmt) in ch_protos.items():
            existing = db.query(models.Channel).filter(
                models.Channel.satellite_id == sat.id,
                models.Channel.protocol_type == proto,
            ).first()
            if existing is None:
                db.add(models.Channel(
                    satellite_id=sat.id,
                    name=name,
                    protocol_type=proto,
                    ip="127.0.0.1",
                    port=port,
                    frame_format=fmt,
                    running=1,
                ))
        db.commit()
        print(f"  + 确保 {len(ch_protos)} 个协议通道已就绪")

        # 遥测参数（至少 8 个，分配四个协议各 2 个）
        params_data = [
            ("P100", "测试姿态Q0", "姿态控制", "float", 16, 1.0, 0.0, None, None),
            ("P101", "测试姿态Q1", "姿态控制", "float", 16, 1.0, 0.0, None, None),
            ("P102", "测试角速度X", "姿态控制", "float", 16, 0.01, 0.0, -5.0, 5.0),
            ("P103", "测试角速度Y", "姿态控制", "float", 16, 0.01, 0.0, -5.0, 5.0),
            ("P104", "测试母线电压", "电源", "float", 16, 0.01, 0.0, 24.0, 32.0),
            ("P105", "测试母线电流", "电源", "float", 16, 0.01, 0.0, 0.0, 50.0),
            ("P106", "测试温度A", "热控", "float", 16, 0.1, -50.0, -10.0, 60.0),
            ("P107", "测试温度B", "热控", "float", 16, 0.1, -50.0, -10.0, 60.0),
        ]
        for i, (code, name, subsys, dtype, bits, scale, offset, tmin, tmax) in enumerate(params_data):
            existing = db.query(models.TelemetryParam).filter(
                models.TelemetryParam.satellite_id == sat.id,
                models.TelemetryParam.param_code == code,
            ).first()
            if existing is None:
                db.add(models.TelemetryParam(
                    satellite_id=sat.id,
                    param_code=code,
                    name=name,
                    subsystem=subsys,
                    data_type=dtype,
                    scale=scale,
                    offset=offset,
                    raw_bits=bits,
                    precision=2,
                    threshold_min=tmin,
                    threshold_max=tmax,
                    enabled=1,
                    order_no=i + 1,
                ))
        db.commit()
        print(f"  + 确保 {len(params_data)} 个遥测参数已就绪")

    finally:
        db.close()


# ---- 主流程 ----
def main() -> None:
    print("=" * 56)
    print("  数据接收流水线测试")
    print("=" * 56)

    # 1. 确保表存在（幂等）
    print("[1/5] 初始化数据库表 ...")
    from app.database import Base, engine as sa_engine
    import app.models  # noqa: F401  注册模型
    Base.metadata.create_all(bind=sa_engine)
    print("  表结构已就绪")

    # 2. 种子数据
    print("[2/5] 写入最小种子数据 ...")
    seed_minimal()

    # 3. 启动接收器
    print("[3/5] 启动数据接收流水线 ...")
    from app.receiver.manager import receiver_manager

    # 设置 SSE 事件循环（测试脚本无 asyncio 事件循环，SSE 发布静默丢弃消息）
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    receiver_manager.start()
    run_sec: int = 4
    print(f"  模拟器运行中，等待 {run_sec} 秒 ...")

    # 4. 等待
    print("[4/5] 收集数据中 ...")
    time.sleep(run_sec)

    # 5. 停止并验证
    receiver_manager.stop()

    print("[5/5] 查询数据库验证 ...")
    db = SessionLocal()
    try:
        td_count: int = db.query(models.TelemetryData).count()
        tf_count: int = db.query(models.TelemetryFrame).count()
        alarm_count: int = db.query(models.Alarm).count()

        print(f"  telemetry_data  行数: {td_count}")
        print(f"  telemetry_frames 行数: {tf_count}")
        print(f"  alarms           行数: {alarm_count}")

        # 展示几条样例数据（使用原生 SQL 规避 SAEnum 名称问题）
        samples = db.execute(
            models.TelemetryData.__table__.select()
            .order_by(models.TelemetryData.__table__.c.ts.desc())
            .limit(3)
        ).fetchall()
        for s in samples:
            print(f"    样本: ts={s.ts}, code={s.param_code}, value={float(s.value):.3f}, quality={s.quality}")

        frame_samples = db.execute(
            models.TelemetryFrame.__table__.select()
            .order_by(models.TelemetryFrame.__table__.c.ts.desc())
            .limit(3)
        ).fetchall()
        for f in frame_samples:
            print(f"    帧: ts={f.ts}, protocol={f.protocol_type}, hex_len={len(f.raw_hex)}")

        # 断言
        assert td_count > 0, f"FAIL: telemetry_data 无数据 (期望 > 0, 实际 {td_count})"
        assert tf_count > 0, f"FAIL: telemetry_frames 无数据 (期望 > 0, 实际 {tf_count})"

        print("-" * 56)
        print("  ✓ 测试通过：数据已成功入库")
        print("=" * 56)

    finally:
        db.close()


if __name__ == "__main__":
    main()
