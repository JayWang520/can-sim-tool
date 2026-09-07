"""服务层测试：virtual 总线上的回环收发、周期发送、DM1 模拟、日志回放、DBC、触发。"""
import asyncio
import time

import can as pycan
import pytest

from app import j1939
from app.bus import BusService
from app.decoder import DbcService
from app.dm1_sim import Dm1Sim
from app.j1939 import DTC
from app.logger import CanLogger, Replayer
from app.senders import Senders
from app.triggers import TriggerService

DBC_PATH = str(
    __import__("pathlib").Path(__file__).resolve().parent.parent / "dbcs" / "demo_engine.dbc"
)


def test_bus_virtual_loopback():
    svc = BusService()
    got: list = []
    svc.connect("virtual", "loop-test")
    svc.listeners.append(lambda m, d: got.append((m, d)))
    try:
        svc.send(0x18FECA00, b"\xff\xff\x01\x00\x00\x00\xff\xff")
        time.sleep(0.3)  # 等 rx 线程
        dirs = [d for _, d in got]
        assert "tx" in dirs  # 发送即回播
        assert "rx" in dirs  # virtual 回环可见
        assert svc.info()["stats"]["sent"] == 1
        assert svc.info()["stats"]["received"] >= 1
    finally:
        svc.disconnect()


def test_bus_reject_unknown_interface():
    import pytest

    svc = BusService()
    with pytest.raises(ValueError):
        svc.connect("nope", "x")
    with pytest.raises(ValueError, match="波特率"):
        svc.connect("virtual", "invalid-bitrate", 0)
    assert not svc.connected


def test_senders_periodic():
    async def main():
        svc = BusService()
        svc.connect("virtual", "senders-test")
        got: list = []
        svc.listeners.append(lambda m, d: got.append(d))
        s = Senders(svc)
        try:
            s.create("task", 0x0CF00400, "00" * 8, 20)
            await asyncio.sleep(0.15)
            s.stop_all()
            assert len(got) >= 4
        finally:
            s.stop_all()
            svc.disconnect()

    asyncio.run(main())


def test_dm1_sim_single_packet():
    async def main():
        svc = BusService()
        svc.connect("virtual", "dm1-single")
        rx = []
        svc.listeners.append(lambda m, d: rx.append(m) if d == "rx" else None)
        sim = Dm1Sim(svc)
        try:
            sim.update({"dtcs": [{"spn": 110, "fmi": 0, "oc": 1}], "period_ms": 30})
            sim.start()
            await asyncio.sleep(0.12)
            sim.stop()
            assert len(rx) >= 2
            assert all(m.arbitration_id == 0x18FECA00 for m in rx)
            assert sim.sent_frames >= 2
        finally:
            sim.stop()
            svc.disconnect()

    asyncio.run(main())


def test_dm1_sim_bam():
    async def main():
        svc = BusService()
        svc.connect("virtual", "dm1-bam")
        rx = []
        svc.listeners.append(lambda m, d: rx.append(m) if d == "rx" else None)
        sim = Dm1Sim(svc)
        try:
            sim.update(
                {
                    "dtcs": [
                        {"spn": 110, "fmi": 0, "oc": 1},
                        {"spn": 100, "fmi": 1, "oc": 1},
                        {"spn": 175, "fmi": 0, "oc": 1},
                    ],
                    "period_ms": 60,
                }
            )
            sim.start()
            await asyncio.sleep(0.2)
            sim.stop()
            # 标准 TP：CM=18ECFFxx、DT=18EDFFxx（各一个 ID），以数据首字节区分
            assert len(rx) >= 6  # ≥2 个周期 × 3 帧
            assert {m.arbitration_id for m in rx} == {0x18ECFF00, 0x18EDFF00}
            cm_frames = [m for m in rx if m.arbitration_id == 0x18ECFF00]
            dt_frames = [m for m in rx if m.arbitration_id == 0x18EDFF00]
            assert {m.data[0] for m in cm_frames} == {0x20}  # BAM 控制字节
            assert {m.data[0] for m in dt_frames} == {1, 2}  # 数据包序号
            assert j1939.PGN_DM1 not in {j1939.pgn_of(m.arbitration_id) for m in rx}
        finally:
            sim.stop()
            svc.disconnect()

    asyncio.run(main())


def test_triggers():
    svc = TriggerService()
    rule = svc.add(name="dm1 高亮", match_pgn=65226, action="highlight")
    svc.add(name="指定数据计数", match_id="18FECA00", data_contains="FF FF".replace(" ", ""),
            action="count")
    assert len(svc.list()) == 2

    dm1_msg = pycan.Message(
        arbitration_id=0x18FECA00, is_extended_id=True, data=b"\xff\xff\x01\x00\x00\x00\xff\xff"
    )
    hits = svc.process(dm1_msg)
    actions = {h["name"] for h in hits}
    assert actions == {"dm1 高亮", "指定数据计数"}

    other = pycan.Message(arbitration_id=0x0CF00400, is_extended_id=True, data=b"\x00" * 8)
    assert svc.process(other) == []

    # send 动作
    svc.add(name="自动回帧", match_pgn=61444, action="send",
            send_id="18EBFF00", send_data="20 0E 00 02 FF CA FE 00".replace(" ", ""))
    hits = svc.process(other)
    assert hits[0]["send"]["arbitration_id"] == 0x18EBFF00
    assert svc.list()[2]["hits"] == 1
    svc.reset_hits()
    assert all(rule.hits == 0 for rule in svc.rules)

    svc.add(name="标准帧回应", match_id="123", action="send",
            send_id="456", send_data="1122", send_extended=False)
    std_hits = svc.process(
        pycan.Message(arbitration_id=0x123, is_extended_id=False, data=b"")
    )
    assert std_hits[-1]["send"]["is_extended_id"] is False

    # 数据条件：字节区间（小端）比较
    svc.add(name="转速>2000", match_pgn=61444, action="count",
            data_cond=[{"type": "bytes", "start": 1, "end": 2, "op": ">", "value": 2000}])
    hi = pycan.Message(arbitration_id=0x0CF00400, is_extended_id=True,
                       data=bytes([0, 0xDC, 0x07, 0, 0, 0, 0, 0]))  # 0x07DC=2012
    lo = pycan.Message(arbitration_id=0x0CF00400, is_extended_id=True,
                       data=bytes([0, 0xF4, 0x01, 0, 0, 0, 0, 0]))  # 0x01F4=500
    assert "转速>2000" in [h["name"] for h in svc.process(hi)]
    assert "转速>2000" not in [h["name"] for h in svc.process(lo)]

    # 单 bit：全帧 bit13（字节1 bit5）
    svc.add(name="bit13=1", match_pgn=61444, action="count",
            data_cond=[{"type": "bit", "index": 13, "value": 1}])
    on = pycan.Message(arbitration_id=0x0CF00400, is_extended_id=True,
                       data=bytes([0, 0x20, 0, 0, 0, 0, 0, 0]))     # 0x20 → bit5=1
    off = pycan.Message(arbitration_id=0x0CF00400, is_extended_id=True,
                        data=bytes([0, 0x04, 0, 0, 0, 0, 0, 0]))    # bit5=0
    assert "bit13=1" in [h["name"] for h in svc.process(on)]
    assert "bit13=1" not in [h["name"] for h in svc.process(off)]

    # 位段：字节0 的 bit2~5
    svc.add(name="位段9", match_id="00000123", action="count",
            data_cond=[{"type": "bits", "byte": 0, "start": 2, "end": 5, "value": 9}])
    m9 = pycan.Message(arbitration_id=0x123, is_extended_id=False, data=bytes([0x24]))  # 0b10_0100 → bit2-5=1001b=9
    m5 = pycan.Message(arbitration_id=0x123, is_extended_id=False, data=bytes([0x14]))  # bit2-5=0101b=5
    assert "位段9" in [h["name"] for h in svc.process(m9)]
    assert "位段9" not in [h["name"] for h in svc.process(m5)]

    # 单字节条件 + 多条件 AND
    svc.add(name="组合", match_pgn=61444, action="count",
            data_cond=[{"type": "byte", "index": 0, "op": "==", "value": 0},
                       {"type": "bytes", "start": 1, "end": 2, "op": "<=", "value": 2012}])
    assert "组合" in [h["name"] for h in svc.process(hi)]
    assert "组合" in [h["name"] for h in svc.process(lo)]


def test_triggers_cond_validation():
    import pytest

    svc = TriggerService()
    with pytest.raises(ValueError):
        svc.add(name="bad-bit", action="count",
                data_cond=[{"type": "bit", "index": 70, "value": 1}])
    with pytest.raises(ValueError):
        svc.add(name="bad-byte", action="count",
                data_cond=[{"type": "byte", "index": 9, "value": 0}])
    with pytest.raises(ValueError):
        svc.add(name="bad-op", action="count",
                data_cond=[{"type": "byte", "index": 0, "op": "~", "value": 0}])
    with pytest.raises(ValueError):
        svc.add(name="bad-range", action="count",
                data_cond=[{"type": "bytes", "start": 3, "end": 1, "value": 0}])


def test_triggers_validation():
    import pytest

    svc = TriggerService()
    with pytest.raises(ValueError):
        svc.add(name="bad", match_id="XYZ", action="highlight")
    with pytest.raises(ValueError):
        svc.add(name="bad", action="send")  # 缺 send_id/send_data
    with pytest.raises(ValueError):
        svc.add(name="bad standard id", action="send", send_id="1234",
                send_data="00", send_extended=False)
    with pytest.raises(ValueError):
        svc.add(name="bad data", action="send", send_id="123",
                send_data="00" * 9)


def test_senders_increment_and_live_update():
    async def main():
        svc = BusService()
        svc.connect("virtual", "inc-test")
        rx: list = []
        svc.listeners.append(lambda m, d: rx.append(bytes(m.data)) if d == "rx" else None)
        s = Senders(svc)
        try:
            # 递增模式：字节 1 每周期 +5
            sid = s.create("cnt", 0x0CF00400, "00 00 00 00 00 00 00 00", 20,
                           mode="increment", inc_byte=1, inc_step=5)["id"]
            await asyncio.sleep(0.12)
            s.stop_all()
            assert len(rx) >= 3
            assert len(set(rx)) >= 3  # 每帧数据都不同
            assert rx[1][1] == (rx[0][1] + 5) & 0xFF
            # 运行中在线修改数据立即生效（rx 里可能混有一帧停止前在途旧数据，过滤）
            rx.clear()
            s.update(sid, data_hex="AA00000000000000", period_ms=20)
            s.start(sid)
            await asyncio.sleep(0.1)
            s.stop_all()
            aa = [x for x in rx if x[0] == 0xAA]
            assert len(aa) >= 2
            assert aa[1][1] == (aa[0][1] + 5) & 0xFF  # 递增模式继续生效
        finally:
            s.stop_all()
            svc.disconnect()

    asyncio.run(main())


def test_senders_multi_byte_increment():
    async def main():
        svc = BusService()
        svc.connect("virtual", "inc16")
        rx: list = []
        svc.listeners.append(lambda m, d: rx.append(bytes(m.data)) if d == "rx" else None)
        s = Senders(svc)
        try:
            # 字节 1~2 按小端拼成 16 位整体递增，步长 0x101
            s.create("cnt16", 0x0CF00400, "0000000000000000", 20,
                     mode="increment", inc_byte=1, inc_end=2, inc_step=0x101)
            await asyncio.sleep(0.12)
            s.stop_all()
            vals = [int.from_bytes(x[1:3], "little") for x in rx]
            assert len(vals) >= 3
            assert all(b - a == 0x101 for a, b in zip(vals, vals[1:]))
            assert all(x[0] == 0 and x[3:] == b"\x00" * 5 for x in rx)  # 区间外字节不动
        finally:
            s.stop_all()
            svc.disconnect()

    asyncio.run(main())


def test_senders_multi_byte_wrap():
    async def main():
        svc = BusService()
        svc.connect("virtual", "wrap16")
        rx: list = []
        svc.listeners.append(lambda m, d: rx.append(bytes(m.data)) if d == "rx" else None)
        s = Senders(svc)
        try:
            s.create("w", 0x123, "00FFFF0000000000", 20,
                     mode="increment", inc_byte=1, inc_end=2, inc_step=1)
            await asyncio.sleep(0.08)
            s.stop_all()
            vals = [int.from_bytes(x[1:3], "little") for x in rx]
            assert vals[0] == 0xFFFF
            assert vals[1] == 0  # 16 位上限回绕
        finally:
            s.stop_all()
            svc.disconnect()

    asyncio.run(main())


def test_senders_validation():
    import pytest

    svc = BusService()
    s = Senders(svc)
    with pytest.raises(ValueError):
        s.create("bad", 0x123, "GG", 100)  # 非 hex
    entry = s.create("ok", 0x123, "0011", 100, auto_start=False)
    copy = s.duplicate(entry["id"])
    assert copy["name"] == "ok_副本" and copy["running"] is False
    with pytest.raises(ValueError):
        s.update(entry["id"], mode="increment", inc_byte=9)  # 字节下标越界
    with pytest.raises(ValueError):
        s.update(entry["id"], mode="increment", inc_byte=3, inc_end=1)  # 起>止
    with pytest.raises(ValueError):
        s.update(entry["id"], period_ms=0)


def test_dm1_oc_auto_increment():
    async def main():
        svc = BusService()
        svc.connect("virtual", "oc-inc")
        rx = []
        svc.listeners.append(lambda m, d: rx.append(bytes(m.data)) if d == "rx" else None)
        sim = Dm1Sim(svc)
        try:
            sim.update({"dtcs": [{"spn": 110, "fmi": 0, "oc": 1}],
                        "period_ms": 30, "oc_auto_inc": True})
            sim.start()
            await asyncio.sleep(0.12)
            sim.stop()
            assert len(rx) >= 2
            assert rx[1][5] == rx[0][5] + 1  # OC 字节（第 6 字节）逐周期递增
        finally:
            sim.stop()
            svc.disconnect()

    asyncio.run(main())


def test_frame_json_standard_vs_extended():
    from app.main import FrameHub

    async def t():
        std = FrameHub.frame_json(
            pycan.Message(arbitration_id=0x123, is_extended_id=False, data=b"\x01\x02"), "rx"
        )
        assert std["ext"] is False
        assert std["id"] == "123"  # 标准帧 3 位 hex
        assert std["pgn"] is None and std["sa"] is None and std["prio"] is None

        ext = FrameHub.frame_json(
            pycan.Message(arbitration_id=0x18FECA00, is_extended_id=True,
                          data=b"\xff\xff\x6e\x00\x00\x01\xff\xff"), "tx"
        )
        assert ext["ext"] is True
        assert ext["id"] == "18FECA00"
        assert ext["pgn"] == 65226 and ext["sa"] == 0

    asyncio.run(t())


def test_dm1_no_dtc_sends_all_ff():
    async def main():
        svc = BusService()
        svc.connect("virtual", "dm1-nofault")
        rx = []
        svc.listeners.append(lambda m, d: rx.append(m) if d == "rx" else None)
        sim = Dm1Sim(svc)
        try:
            sim.update({"dtcs": []})
            frames = sim._build_frames()
            assert len(frames) == 1
            assert bytes(frames[0].data).startswith(b"\xff\xff")
            assert sim.preview()["mode"] == "single"
        finally:
            svc.disconnect()

    asyncio.run(main())


def test_dbc_decode():
    dbc = DbcService()
    dbc.load(DBC_PATH)
    # EEC1: 扭矩字节=100 → -25%；转速字节 0x1ED0=7888 → 986 rpm
    msg = pycan.Message(
        arbitration_id=0x0CF00400, is_extended_id=True,
        data=bytes([100, 0xD0, 0x1E, 0, 0, 0, 0, 0]),
    )
    r = dbc.decode(msg)
    assert r["message"] == "EEC1"
    assert r["signals"]["ActualEnginePercentTorque"] == -25
    assert r["signals"]["EngineSpeed"] == 986

    # 不同 SA 也能按 PGN 兜底匹配
    msg2 = pycan.Message(
        arbitration_id=0x0CF00409, is_extended_id=True,
        data=bytes([100, 0xD0, 0x1E, 0, 0, 0, 0, 0]),
    )
    assert dbc.decode(msg2)["message"] == "EEC1"

    encoded = dbc.encode("ET1", {"EngineCoolantTemperature": 90})
    assert encoded[0] == 130  # (90+40)=0x82，cantools 默认补齐到 8 字节


def test_logger_and_replay(tmp_path, monkeypatch):
    import app.logger as logger_mod

    monkeypatch.setattr(logger_mod, "LOG_DIR", tmp_path)

    async def main():
        svc = BusService()
        svc.connect("virtual", "replay-test")
        sent = []
        svc.listeners.append(lambda m, d: sent.append(m))
        lg = CanLogger(svc)
        lg.start("csv")
        for i in range(3):
            lg.record(
                pycan.Message(arbitration_id=0x18FECA00, is_extended_id=True,
                              data=b"\xff\xff" + bytes([i]) + b"\x00\x00\xff\xff"),
                "rx",
            )
            await asyncio.sleep(0.05)
        info = lg.stop()
        assert info["frames"] == 3

        rp = Replayer(svc)
        n_before = len(sent)
        started = rp.start(info["file"], speed=10)
        assert started["frames"] == 3
        assert rp.status()["total"] == 3
        await asyncio.sleep(0.6)
        assert len([m for m in sent]) - n_before >= 3  # 回放补齐全部帧
        assert rp.status()["current"] == 3
        rp.stop()
        with pytest.raises(ValueError, match="正数"):
            rp.start(info["file"], speed=0)
        svc.disconnect()


    asyncio.run(main())


def test_logger_does_not_overwrite_same_second(tmp_path, monkeypatch):
    import app.logger as logger_mod
    monkeypatch.setattr(logger_mod, "LOG_DIR", tmp_path)
    svc = BusService()
    lg = CanLogger(svc)
    try:
        first = lg.start("csv")
        lg.stop()
        second = lg.start("csv")
        assert first["file"] != second["file"]
        assert len(list(tmp_path.glob("*.csv"))) == 2
    finally:
        lg.stop()


def test_read_asc_log(tmp_path):
    from app.main import _read_log_asc
    path = tmp_path / "capture.asc"
    path.write_text(
        "date Tue Aug 29 12:00:00 2026\n"
        "base hex timestamps absolute\n"
        "    0.100000 1  123   RX   d 2 1122\n"
        "    0.200000 1  18FECA00x   TX   d 8 FFFF00000000FFFF\n",
        encoding="utf-8",
    )
    result = _read_log_asc(path)
    assert result["count"] == 2
    assert result["frames"][0]["id"] == "123"
    assert result["frames"][0]["ext"] is False
    assert result["frames"][1]["id"] == "18FECA00"
    assert result["frames"][1]["ext"] is True
