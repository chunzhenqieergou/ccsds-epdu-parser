# -*- coding: utf-8 -*-
"""
STMS 项目功能自动验收脚本
========================
一键验证项目核心功能是否真实可用，逐项输出 [PASS]/[FAIL] 清单，
可作为向评审/导师演示的自动化证明。

前置条件：
  1. MySQL 已启动（stms 库已初始化）
  2. MongoDB 已启动（127.0.0.1:27017）
  3. 后端已启动（127.0.0.1:8010，即 uvicorn app.main:app --port 8010）

用法:
  cd backend
  ../venv/Scripts/python.exe scripts/verify_project.py
"""
import json
import socket
import struct
import sys
import time
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8010/api/v1"
MONGODB_URI = "mongodb://127.0.0.1:27017"
results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ""))


def http(method: str, path: str, token: str | None = None, body: dict | None = None,
         raw: bool = False):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=10)
    content = resp.read()
    return content if raw else json.loads(content)


def tcp_send(port: int, frame: bytes) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(("127.0.0.1", port))
    s.sendall(frame)
    s.close()


def udp_send(port: int, frame: bytes) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(frame, ("127.0.0.1", port))
    s.close()


def main() -> None:
    print("=" * 60)
    print("STMS 卫星遥测数据综合管理系统 — 功能验收")
    print("=" * 60)

    # ------------------------------------------------------------
    # 0. 基础设施
    # ------------------------------------------------------------
    print("\n[0] 基础设施")
    try:
        d = http("GET", "/health")
        check("后端服务运行中 (8010)", d.get("code") == 0)
    except Exception as e:
        check("后端服务运行中 (8010)", False, str(e))
        print("\n后端未启动，无法继续验收。请先启动后端。")
        return

    from pymongo import MongoClient
    try:
        mc = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
        mc.admin.command("ping")
        check("MongoDB 连接 (27017)", True)
        db = mc["stms"]
        idxs = [i["name"] for i in db["telemetry_data"].list_indexes()]
        check("MongoDB 时序索引", "idx_param_ts" in idxs and any("ttl" in i for i in idxs),
              ",".join(idxs[:4]))
        total = db["telemetry_data"].count_documents({})
        check("MongoDB 遥测数据量 > 0", total > 0, f"{total} 条")
    except Exception as e:
        check("MongoDB 连接 (27017)", False, str(e))

    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    try:
        check("MySQL 遥测参数表有数据",
              db.query(models.TelemetryParam).count() > 0)
        check("MySQL 原始帧表有数据",
              db.query(models.TelemetryFrame).count() > 0)
    finally:
        db.close()

    # ------------------------------------------------------------
    # 1. 认证与权限
    # ------------------------------------------------------------
    print("\n[1] 用户认证 (RBAC)")
    try:
        d = http("POST", "/auth/login", body={"username": "admin", "password": "admin123"})
        token = d.get("data", {}).get("access_token")
        check("登录获取 JWT Token", bool(token))
        check("JWT 含 refresh_token", bool(d.get("data", {}).get("refresh_token")))
        d2 = http("GET", "/system/users", token=token)
        check("带 Token 访问受保护接口", d2.get("code") == 0)
        try:
            http("GET", "/system/users")  # 无 token 应 401
            check("无 Token 被拒绝 (401)", False, "意外放行")
        except urllib.error.HTTPError as e:
            check("无 Token 被拒绝 (401)", e.code == 401, f"HTTP {e.code}")
    except Exception as e:
        check("用户认证", False, str(e))
        return

    # ------------------------------------------------------------
    # 2. 配置管理 CRUD
    # ------------------------------------------------------------
    print("\n[2] 配置管理 (卫星/参数/通道)")
    for name, path in [
        ("卫星型号列表", "/satellites/"),
        ("遥测参数列表", "/params/"),
        ("通道列表", "/channels/"),
    ]:
        try:
            d = http("GET", path, token=token)
            check(name, d.get("code") == 0)
        except Exception as e:
            check(name, False, str(e))

    # 参数 JSON 模板导出（方案 3.2）
    try:
        d = http("GET", "/params/export", token=token)
        check("参数模板 JSON 导出", d.get("code") == 0)
    except Exception as e:
        check("参数模板 JSON 导出", False, str(e))

    # ------------------------------------------------------------
    # 3. 时序数据库 (MongoDB)
    # ------------------------------------------------------------
    print("\n[3] 时序数据库 (方案 4.2 MongoDB)")
    from app.tsdb import get_tsdb_store
    store = get_tsdb_store()
    check("时序存储后端 = MongoDB", store.backend == "mongodb", store.backend)
    try:
        mc = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
        n1 = mc["stms"]["telemetry_data"].count_documents({})
        time.sleep(6)
        n2 = mc["stms"]["telemetry_data"].count_documents({})
        check("遥测数据持续写入 (6s 增量)", n2 > n1, f"{n1} → {n2} (+{n2 - n1})")
    except Exception as e:
        check("遥测数据持续写入", False, str(e))

    try:
        d = http("GET", "/statistics/basic?param_code=P001", token=token)
        s = d.get("data", {})
        check("统计聚合 (MongoDB 聚合管道)", s.get("count", 0) > 0,
              f"count={s.get('count')} mean={round(s.get('mean') or 0, 2)}")
    except Exception as e:
        check("统计聚合", False, str(e))

    # ------------------------------------------------------------
    # 4. 遥测查询 / 统计 / 告警 / 导出
    # ------------------------------------------------------------
    print("\n[4] 业务功能 (查询/统计/告警/导出)")
    try:
        d = http("GET", "/telemetry/latest", token=token)
        check("最新值查询 (/telemetry/latest)",
              len(d.get("data", [])) > 0, f"{len(d.get('data', []))} 个参数")
        d = http("GET", "/telemetry/query?page=1&page_size=5", token=token)
        check("历史数据分页查询", d.get("data", {}).get("total", 0) > 0,
              f"total={d.get('data', {}).get('total')}")
        d = http("GET", "/telemetry/frames?page_size=5", token=token)
        check("原始帧列表", len(d.get("data", {}).get("items", [])) > 0)
    except Exception as e:
        check("遥测查询", False, str(e))

    for name, path in [
        ("趋势分析", "/statistics/trend?param_code=P001"),
        ("异常检测", "/statistics/anomalies?param_code=P001"),
    ]:
        try:
            d = http("GET", path, token=token)
            check(name, d.get("code") == 0)
        except Exception as e:
            check(name, False, str(e))

    try:
        d = http("GET", "/alarms/?page_size=5", token=token)
        items = d.get("data", {}).get("items", [])
        check("告警记录列表", d.get("code") == 0, f"{len(items)} 条")
    except Exception as e:
        check("告警记录列表", False, str(e))

    now = datetime.now()
    export_body = {
        "start": (now - timedelta(minutes=10)).isoformat(),
        "end": now.isoformat(),
        "param_codes": ["P001", "P002"],
        "channel_ids": None,
    }
    for fmt in ("json", "csv"):
        try:
            raw = http("POST", f"/export/{fmt}", token=token, body=export_body, raw=True)
            check(f"{fmt.upper()} 数据导出", len(raw) > 0, f"{len(raw)} 字节")
        except Exception as e:
            check(f"{fmt.upper()} 数据导出", False, str(e))

    # ------------------------------------------------------------
    # 5. 真实数据接收 (TCP/UDP)
    # ------------------------------------------------------------
    print("\n[5] 真实数据接收 (方案 3.3 Socket)")
    from app.receiver.simulator import (
        _build_ccsds_frame, _build_m1553b_frame, _build_can_frame, _build_rs422_frame,
    )
    from app.receiver.manager import parse_real_frame, _protocol_param_groups

    # 5.1 离线协议解析
    db = SessionLocal()
    params = db.query(models.TelemetryParam).filter(
        models.TelemetryParam.enabled == 1).order_by(models.TelemetryParam.id).all()
    db.close()
    groups = _protocol_param_groups(params)
    ok_proto = True
    for proto, builder in [("CCSDS", _build_ccsds_frame), ("1553B", _build_m1553b_frame),
                           ("CAN", _build_can_frame), ("RS422", _build_rs422_frame)]:
        fr = builder(0, [])
        pts, _info = parse_real_frame(proto, fr["frame_bytes"], groups)
        if not pts:
            ok_proto = False
    check("四协议帧解析 (CCSDS/1553B/CAN/RS422)", ok_proto)

    # 5.2 TCP/UDP 真实接收端到端（用大 tick 避免与模拟器帧碰撞）
    def recent_count(raw_hex: str, seconds: int = 5) -> int:
        db = SessionLocal()
        try:
            since = datetime.now() - timedelta(seconds=seconds)
            return db.query(models.TelemetryFrame).filter(
                models.TelemetryFrame.raw_hex == raw_hex,
                models.TelemetryFrame.ts >= since,
            ).count()
        finally:
            db.close()

    big = int(time.time()) % 100000 + 900000
    try:
        tcp_send(9001, _build_ccsds_frame(big, [])["frame_bytes"])
        time.sleep(0.8)
        ok = recent_count(_build_ccsds_frame(big, [])["raw_hex"]) >= 1
        check("TCP 真实接收 CCSDS → 入库", ok)
    except Exception as e:
        check("TCP 真实接收 CCSDS → 入库", False, str(e))

    try:
        udp_send(9002, _build_m1553b_frame(big + 1, [])["frame_bytes"])
        udp_send(9002, _build_can_frame(big + 2, [])["frame_bytes"])
        udp_send(9002, _build_rs422_frame(big + 3, [])["frame_bytes"])
        time.sleep(0.8)
        n = sum([
            recent_count(_build_m1553b_frame(big + 1, [])["raw_hex"]),
            recent_count(_build_can_frame(big + 2, [])["raw_hex"]),
            recent_count(_build_rs422_frame(big + 3, [])["raw_hex"]),
        ])
        check("UDP 真实接收 1553B/CAN/RS422 → 入库", n >= 3, f"{n}/3 类")
    except Exception as e:
        check("UDP 真实接收 1553B/CAN/RS422 → 入库", False, str(e))

    # 5.3 通道启停真实控制接收
    try:
        chs = http("GET", "/channels/?page_size=50", token=token)["data"]
        items = chs.get("items") or chs
        can = next(c for c in items if c["protocol_type"] == "CAN")
        # 停止 → 发帧 → 应被丢弃
        http("POST", f"/channels/{can['id']}/stop", token=token)
        time.sleep(0.4)
        fr = _build_can_frame(big + 10, [])
        udp_send(9002, fr["frame_bytes"])
        time.sleep(0.8)
        stopped = recent_count(fr["raw_hex"]) == 0
        # 恢复 → 发帧 → 应入库
        http("POST", f"/channels/{can['id']}/start", token=token)
        time.sleep(0.4)
        fr2 = _build_can_frame(big + 11, [])
        udp_send(9002, fr2["frame_bytes"])
        time.sleep(0.8)
        restored = recent_count(fr2["raw_hex"]) >= 1
        check("通道启停真实控制数据流", stopped and restored,
              f"停止={stopped} 恢复={restored}")
    except Exception as e:
        check("通道启停真实控制数据流", False, str(e))

    # ------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"验收结果: {passed}/{total} 项通过")
    if passed == total:
        print("全部通过 — 核心功能完整可用")
    else:
        print("存在未通过项，请查看上方 FAIL 明细")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
