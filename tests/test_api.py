"""API 冒烟测试：TestClient 走完整 HTTP/WebSocket 流程（virtual 总线）。"""
from fastapi.testclient import TestClient

from app.main import app


def test_api_full_flow(tmp_path):
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert page.headers["cache-control"] == "no-store, no-cache, must-revalidate"
        assert "app.js?v=generators-1" in page.text

        # 接口元信息
        r = client.get("/api/interfaces")
        assert "virtual" in r.json()

        # 连接 virtual 总线
        r = client.post("/api/connect", json={"interface": "virtual", "channel": "api-test"})
        assert r.status_code == 200
        assert r.json()["connected"] is True

        r = client.get("/api/status")
        assert r.json()["connected"] is True

        # 手动发送
        r = client.post("/api/send", json={"id": "0CF00400", "data": "64D01E0000000000"})
        assert r.json()["ok"] is True

        # 周期发送任务
        r = client.post("/api/senders", json={
            "name": "eec1", "id": "0CF00400", "data": "64D01E0000000000", "period_ms": 50,
        })
        sid = r.json()["id"]
        r = client.post(f"/api/senders/{sid}/stop")
        assert r.json()["running"] is False
        # 在线修改数据 + 递增模式（字节区间 1~2）
        r = client.put(f"/api/senders/{sid}", json={
            "data": "6400000000000000", "mode": "increment",
            "inc_byte": 1, "inc_end": 2, "inc_step": 2,
        })
        assert r.json()["mode"] == "increment"
        assert r.json()["inc_end"] == 2
        assert r.json()["data_hex"] == "6400000000000000"
        r = client.put(f"/api/senders/{sid}", json={"mode": "increment", "inc_byte": 9})
        assert r.status_code == 400
        r = client.put(f"/api/senders/{sid}", json={"mode": "increment", "inc_byte": 3, "inc_end": 1})
        assert r.status_code == 400  # 起>止
        client.delete(f"/api/senders/{sid}")
        assert client.get("/api/senders").json() == []

        # DM1 配置与预览
        r = client.put("/api/dm1", json={
            "dtcs": [{"spn": 110, "fmi": 0, "oc": 1}], "lamps": {"red": "on"},
        })
        assert r.json()["preview"]["mode"] == "single"
        assert len(r.json()["preview"]["frames"]) == 1
        assert r.json()["preview"]["frames"][0]["id"] == "18FECA00"

        # 发送节点（SA）可修改：预览 ID 立即变化
        r = client.put("/api/dm1", json={"sa": 0x49})
        assert r.json()["preview"]["frames"][0]["id"] == "18FECA49"
        r = client.put("/api/dm1", json={"sa": 300})
        assert r.status_code == 400  # SA 超出 0-255 拒绝
        client.put("/api/dm1", json={"sa": 0})

        # 自定义 PGN：模拟 DM2 历史故障
        r = client.put("/api/dm1", json={"pgn": 65227})
        assert r.json()["preview"]["frames"][0]["id"] == "18FECB00"
        # PDU1 私有 PGN + 指定 DA
        r = client.put("/api/dm1", json={"pgn": 0xEF00, "da": 0x17})
        assert r.json()["preview"]["frames"][0]["id"] == "18EF1700"
        r = client.put("/api/dm1", json={"pgn": 0x40000})
        assert r.status_code == 400  # PGN 超出 18bit 拒绝
        client.put("/api/dm1", json={"pgn": 65226, "da": None})

        # 优先级决定 ID 前导（0x18 = 优先级 6 的编码）
        r = client.put("/api/dm1", json={"priority": 3})
        assert r.json()["preview"]["frames"][0]["id"] == "0CFECA00"
        r = client.put("/api/dm1", json={"priority": 7})
        assert r.json()["preview"]["frames"][0]["id"] == "1CFECA00"
        r = client.put("/api/dm1", json={"priority": 8})
        assert r.status_code == 400
        client.put("/api/dm1", json={"priority": 6})

        # 节点合并为一个完整 29bit ID 直接指定
        r = client.put("/api/dm1", json={"arb_id": 0x18FECB00})
        assert r.json()["preview"]["frames"][0]["id"] == "18FECB00"
        assert client.get("/api/dm1").json()["config"]["pgn"] == 65227
        r = client.put("/api/dm1", json={"arb_id": 0x20000000})
        assert r.status_code == 400  # 超出 29bit 拒绝
        client.put("/api/dm1", json={"arb_id": 0x18FECA00})

        # 多包的两个传输节点完整 ID 可分别自定义
        # 默认：跟随节点（1CFECA49 → CM=1CECFF49、DT=1CEDFF49）
        r = client.put("/api/dm1", json={
            "arb_id": 0x1CFECA49,
            "dtcs": [{"spn": 110, "fmi": 0}, {"spn": 100, "fmi": 1}, {"spn": 175, "fmi": 0}],
        })
        assert {f["id"] for f in r.json()["preview"]["frames"]} == {"1CECFF49", "1CEDFF49"}
        # 全自定义：CM=18EBFF00、DT=18ECFF00
        r = client.put("/api/dm1", json={"tp_cm_id": 0x18EBFF00, "tp_dt_id": 0x18ECFF00})
        frames = r.json()["preview"]["frames"]
        assert frames[0]["id"] == "18EBFF00"
        assert frames[1]["id"] == "18ECFF00" and frames[2]["id"] == "18ECFF00"
        r = client.put("/api/dm1", json={"tp_cm_id": 0x20000000})
        assert r.status_code == 400
        client.put("/api/dm1", json={
            "tp_cm_id": None, "tp_dt_id": None,
            "arb_id": 0x18FECA00, "dtcs": [{"spn": 110, "fmi": 0, "oc": 1}],
        })

        r = client.put("/api/dm1", json={
            "dtcs": [{"spn": 110, "fmi": 0}, {"spn": 100, "fmi": 1}, {"spn": 175, "fmi": 0}],
        })
        assert r.json()["preview"]["mode"] == "bam"
        assert len(r.json()["preview"]["frames"]) == 3
        assert "TP.CM" in r.json()["preview"]["frames"][0]["desc"]

        # 单次发送（当前 3 DTC → BAM 3 帧）
        r = client.post("/api/dm1/send_once")
        assert r.json()["sent"] == 3

        # 触发规则
        r = client.post("/api/triggers", json={
            "name": "dm1", "match_pgn": 65226, "action": "highlight",
        })
        assert r.json()["hits"] == 0
        # 带数据条件（字节区间比较）的规则
        r = client.post("/api/triggers", json={
            "name": "转速条件", "match_pgn": 61444, "action": "count",
            "data_cond": [{"type": "bytes", "start": 1, "end": 2, "op": ">", "value": 2000}],
        })
        assert r.json()["data_cond"][0]["value"] == 2000
        r = client.post("/api/triggers/set_enabled", json={"enabled": False})
        assert r.json()["count"] == 2
        assert all(not rule["enabled"] for rule in client.get("/api/triggers").json())
        r = client.post("/api/triggers/set_enabled", json={"enabled": True})
        assert r.json()["enabled"] is True
        assert all(rule["enabled"] for rule in client.get("/api/triggers").json())
        assert client.post("/api/triggers/set_enabled", json={}).status_code == 400
        r = client.post("/api/triggers", json={
            "name": "bad", "action": "count",
            "data_cond": [{"type": "bit", "index": 70, "value": 1}],
        })
        assert r.status_code == 400
        # 场景
        r = client.get("/api/scenarios")
        assert len(r.json()) >= 3
        r = client.post("/api/scenarios/overtemp.json/apply")
        assert r.json()["config"]["dtcs"][0]["spn"] == 110
        assert r.json()["preview"]["mode"] == "single"

        # 配置保存/读取：任务 + DM1 现场整体存取
        client.post("/api/senders", json={
            "name": "keep", "id": "0CF00400", "data": "6400000000000000",
            "period_ms": 50, "mode": "increment", "inc_byte": 1, "inc_end": 2, "inc_step": 3,
        })
        client.put("/api/dm1", json={"dtcs": [{"spn": 110, "fmi": 0, "oc": 2}], "oc_auto_inc": True})
        r = client.post("/api/presets", json={"name": "台架现场"})
        assert r.json()["tasks"] == 1
        file = r.json()["file"]
        for t in client.get("/api/senders").json():
            client.delete(f"/api/senders/{t['id']}")
        assert client.get("/api/senders").json() == []
        r = client.post(f"/api/presets/{file}/load")
        assert r.json()["tasks"] == 1
        tasks = client.get("/api/senders").json()
        assert tasks[0]["mode"] == "increment"
        assert tasks[0]["inc_end"] == 2 and tasks[0]["inc_step"] == 3
        dm1_cfg = client.get("/api/dm1").json()["config"]
        assert dm1_cfg["dtcs"][0]["oc"] == 2
        assert dm1_cfg["oc_auto_inc"] is True
        # 场景现场包含触发规则，一并恢复
        assert any(x["match_pgn"] == 65226 for x in client.get("/api/triggers").json())
        assert any(p["file"] == file for p in client.get("/api/presets").json())
        client.delete(f"/api/presets/{file}")
        assert all(p["file"] != file for p in client.get("/api/presets").json())

        # 触发规则保存/读取（目录 + 任意路径），逻辑与发送配置一致
        r = client.post("/api/triggers/presets", json={"name": "常用规则"})
        assert r.json()["rules"] >= 1
        trig_file = r.json()["file"]
        assert any(p["file"] == trig_file for p in client.get("/api/triggers/presets").json())
        # 纯触发规则文件不出现在场景配置列表里
        assert all(p["file"] != trig_file for p in client.get("/api/presets").json())
        for rule in client.get("/api/triggers").json():
            client.delete(f"/api/triggers/{rule['id']}")
        assert client.get("/api/triggers").json() == []
        r = client.post(f"/api/triggers/presets/{trig_file}/load")
        assert r.json()["rules"] >= 1
        assert any(x["match_pgn"] == 65226 for x in client.get("/api/triggers").json())
        trig_path = tmp_path / "rules.json"
        r = client.post("/api/triggers/save_to", json={"path": str(trig_path)})
        assert r.json()["rules"] >= 1 and trig_path.exists()
        for rule in client.get("/api/triggers").json():
            client.delete(f"/api/triggers/{rule['id']}")
        r = client.post("/api/triggers/load_from", json={"path": str(trig_path)})
        assert r.json()["rules"] >= 1
        client.delete(f"/api/triggers/presets/{trig_file}")

        # 保存/读取到任意自定义路径（另存为 / 打开文件）
        custom = tmp_path / "现场" / "台架.json"
        r = client.post("/api/presets/save_to", json={"path": str(custom)})
        assert r.json()["tasks"] >= 1
        assert custom.exists()
        for t in client.get("/api/senders").json():
            client.delete(f"/api/senders/{t['id']}")
        r = client.post("/api/presets/load_from", json={"path": str(custom)})
        assert r.json()["tasks"] >= 1
        r = client.post("/api/presets/save_to", json={"path": "relative.json"})
        assert r.status_code == 400
        r = client.post("/api/presets/load_from", json={"path": str(tmp_path / "nope.json")})
        assert r.status_code == 404

        # 任意路径日志回看
        import csv as _csv

        logcsv = tmp_path / "extlog.csv"
        with open(logcsv, "w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["ts", "id", "extended", "dir", "dlc", "data"])
            w.writerow(["0.1", "18FECA00", "1", "rx", "8", "FFFF00000000FFFF"])
            w.writerow(["0.2", "00000123", "0", "rx", "2", "1122"])
        r = client.post("/api/log/read_file", json={"path": str(logcsv)})
        data = r.json()
        assert data["count"] == 2
        assert data["frames"][0]["pgn"] == 65226
        assert data["frames"][1]["ext"] is False and data["frames"][1]["id"] == "123"

        # WebSocket 推流
        with client.websocket_connect("/ws") as ws:
            client.post("/api/send", json={"id": "18FECA00", "data": "FFFF00000000FFFF"})
            msg = ws.receive_json()
            assert msg["type"] == "frame"
            assert msg["ext"] is True
            assert msg["id"] == "18FECA00"
            assert msg["pgn"] == 65226
            client.post("/api/send", json={"id": "18FECB00", "data": "FFFF00000000FFFF"})
            dm2_msg = None
            for _ in range(6):
                candidate = ws.receive_json()
                if candidate.get("pgn") == 65227:
                    dm2_msg = candidate
                    break
            assert dm2_msg is not None
            assert dm2_msg["pgn"] == 65227 and "dm2" in dm2_msg
            # 标准帧：3 位 ID、无 J1939 字段（virtual 总线 tx/rx 各推一条，循环取）
            client.post("/api/send", json={"id": "123", "data": "1122", "extended": False})
            for _ in range(6):
                msg2 = ws.receive_json()
                if msg2["id"] == "123":
                    break
            assert msg2["ext"] is False
            assert msg2["id"] == "123"
            assert msg2["pgn"] is None
            stats = client.get("/api/stats/frames").json()
            stat_ids = {row["id"] for row in stats}
            assert "18FECA00" in stat_ids and "123" in stat_ids
            assert all(row["count"] >= 1 for row in stats)

        # 日志记录与回看读取
        import time as _time

        client.post("/api/log/start", json={"format": "csv"})
        client.post("/api/send", json={"id": "18FECA00", "data": "FFFF00000000FFFF"})
        client.post("/api/send", json={"id": "123", "data": "1122", "extended": False})
        # 非 JSON 调用方可能传字符串，"false" 仍必须发送标准帧。
        r = client.post("/api/send", json={"id": "123", "data": "1122", "extended": "false"})
        assert r.json()["ok"] is True
        r = client.post("/api/send", json={"id": "1234", "data": "1122", "extended": False})
        assert r.status_code == 400
        _time.sleep(0.3)  # 等异步记录落盘
        info = client.post("/api/log/stop").json()
        assert info["frames"] >= 4  # 每帧 tx + rx 各一条

        r = client.get(f"/api/log/read/{info['file']}")
        data = r.json()
        assert data["count"] >= 4
        ids = {f["id"] for f in data["frames"]}
        assert "18FECA00" in ids and "123" in ids
        ext = [f for f in data["frames"] if f["id"] == "18FECA00"][0]
        assert ext["ext"] is True and ext["pgn"] == 65226
        std = [f for f in data["frames"] if f["id"] == "123"][0]
        assert std["ext"] is False and std["pgn"] is None
        r = client.get("/api/log/read/不存在.csv")
        assert r.status_code == 404
        r = client.delete(f"/api/log/{info['file']}")
        assert r.json()["ok"] is True
        assert not any(f["name"] == info["file"] for f in client.get("/api/log/files").json())
        assert client.delete("/api/log/不存在.csv").status_code == 404

        # 自定义文件保存路径
        default = client.get("/api/settings").json()
        try:
            new_logs = str(tmp_path / "mylogs")
            new_presets = str(tmp_path / "mypresets")
            r = client.put("/api/settings", json={"logs_dir": new_logs, "presets_dir": new_presets})
            assert r.json()["logs_dir"] == new_logs.replace("/", "\\") or r.json()["logs_dir"].endswith("mylogs")
            # 配置保存到新目录
            r = client.post("/api/presets", json={"name": "路径测试"})
            assert (tmp_path / "mypresets").exists()
            # 日志记录到新目录
            client.post("/api/log/start", json={"format": "csv"})
            client.post("/api/send", json={"id": "0CF00400", "data": "0000000000000000"})
            import time as _t2

            _t2.sleep(0.2)
            client.post("/api/log/stop")
            assert any(p.suffix == ".csv" for p in (tmp_path / "mylogs").iterdir())
            r = client.put("/api/settings", json={"logs_dir": "Z:\\不可能<存在|的路径*"})
            assert r.status_code == 400
        finally:
            client.put("/api/settings", json={
                "logs_dir": default["default_logs_dir"],
                "presets_dir": default["default_presets_dir"],
            })

        client.post("/api/disconnect")
        assert client.get("/api/status").json()["connected"] is False
        assert client.get("/api/stats/frames").json() == []
