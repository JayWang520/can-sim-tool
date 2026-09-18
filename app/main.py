"""CAN 模拟收发工具后端入口：uvicorn app.main:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

import asyncio
import csv
import json
import re
import sys
import time
import uuid
from pathlib import Path

import can as pycan

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Form
from starlette.concurrency import run_in_threadpool
from .file_analysis import analyze_file, MAX_BYTES
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import j1939
from . import logger as _logger_mod
from .bus import INTERFACES, BusService
from .build_info import APP_VERSION, frontend_version
from .decoder import DbcService
from .dm1_sim import Dm1Sim
from .logger import CanLogger, Replayer
from .senders import Senders
from .triggers import TriggerService

# 打包（PyInstaller）后：exe 所在目录是可写数据目录，_MEIPASS/_internal 是只读资源目录
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", ROOT))
else:
    ROOT = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = ROOT

SCENARIO_DIR = RESOURCE_DIR / "scenarios"
DBC_UPLOAD_DIR = ROOT / "dbcs" / "uploads"
DEFAULT_LOGS_DIR = ROOT / "logs"
DEFAULT_PRESET_DIR = ROOT / "presets"
SETTINGS_FILE = ROOT / "settings.json"
FRONTEND_VERSION = frontend_version(RESOURCE_DIR)

app = FastAPI(title="CAN Sim Tool", version=APP_VERSION)


@app.get("/api/version")
async def get_version():
    return {"version": APP_VERSION, "frontend_version": FRONTEND_VERSION}


@app.middleware("http")
async def disable_frontend_cache(request, call_next):
    """Always serve the current byte-editor code after an application update."""
    response = await call_next(request)
    path = request.url.path.lower()
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


def _parse_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "1", "yes", "on"}:
            return True
        if value in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def _validate_can_id(cid: int, is_extended: bool) -> None:
    max_id = 0x1FFFFFFF if is_extended else 0x7FF
    if not 0 <= cid <= max_id:
        frame_type = "扩展帧" if is_extended else "标准帧"
        raise ValueError(f"{frame_type} ID 须为 0-{max_id:#x}，当前: {cid:#x}")

bus = BusService()
dbc = DbcService()
senders = Senders(bus)
dm1 = Dm1Sim(bus)
logger = CanLogger(bus)
replayer = Replayer(bus)
triggers = TriggerService()

# 可自定义目录（日志 / 配置现场），保存在 settings.json，重启仍生效
PRESET_DIR = DEFAULT_PRESET_DIR


def _read_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _apply_dirs(logs_dir: str, presets_dir: str) -> None:
    global PRESET_DIR
    _logger_mod.LOG_DIR = Path(logs_dir)
    PRESET_DIR = Path(presets_dir)


@app.on_event("startup")
async def _startup() -> None:
    hub.loop = asyncio.get_running_loop()
    # 恢复自定义路径（目录不可用时回退默认）
    saved = _read_settings()
    if saved.get("logs_dir") or saved.get("presets_dir"):
        try:
            _apply_dirs(saved.get("logs_dir", DEFAULT_LOGS_DIR), saved.get("presets_dir", DEFAULT_PRESET_DIR))
        except Exception:
            _apply_dirs(DEFAULT_LOGS_DIR, DEFAULT_PRESET_DIR)


@app.on_event("shutdown")
async def _shutdown() -> None:
    dm1.stop()
    senders.stop_all()
    replayer.stop()
    if logger.recording:
        logger.stop()
    bus.disconnect()


@app.get("/api/settings")
async def get_settings():
    return {
        "logs_dir": str(_logger_mod.LOG_DIR),
        "presets_dir": str(PRESET_DIR),
        "default_logs_dir": str(DEFAULT_LOGS_DIR),
        "default_presets_dir": str(DEFAULT_PRESET_DIR),
    }


@app.put("/api/settings")
async def update_settings(body: dict):
    """自定义日志/配置保存目录（相对路径按项目根解析），立即生效并持久化。"""
    cur = await get_settings()
    applied = {}
    for key, default in (("logs_dir", cur["logs_dir"]), ("presets_dir", cur["presets_dir"])):
        val = str(body.get(key) or default).strip()
        p = Path(val)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise HTTPException(400, f"无法创建目录 {val}: {e}")
        if not p.is_dir():
            raise HTTPException(400, f"路径不是目录: {val}")
        applied[key] = str(p)
    _apply_dirs(applied["logs_dir"], applied["presets_dir"])
    SETTINGS_FILE.write_text(json.dumps(applied, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, **applied}


def frame_payload(ts: float, cid: int, ext: bool, direction: str, data: bytes) -> dict:
    """统一帧 JSON：实时 WS 推流与日志回看共用同一结构。"""
    frame = {
        "type": "frame",
        "ts": ts,
        "dir": direction,
        "ext": bool(ext),
        "id": f"{cid:08X}" if ext else f"{cid:03X}",
        "dlc": len(data),
        "data": bytes(data).hex().upper(),
    }
    if ext:  # J1939 29bit 解析仅对扩展帧有意义
        info = j1939.decode_id(cid)
        frame.update(
            prio=info["priority"],
            pgn=info["pgn"],
            sa=info["sa"],
            da=info["da"],
            pdu="PDU1" if info["is_pdu1"] else "PDU2",
        )
    else:
        frame.update(prio=None, pgn=None, sa=None, da=None, pdu=None)
    if dbc.loaded:
        frame["decoded"] = dbc.decode(
            pycan.Message(arbitration_id=cid, is_extended_id=bool(ext), data=bytes(data))
        )
    # 单包 DM1/DM2 直接解析 DTC；TP.BAM 完成帧在 FrameHub 中解析
    if frame.get("pgn") in (j1939.PGN_DM1, j1939.PGN_DM2) and len(data) in (6, 8):
        try:
            frame["dm1" if frame["pgn"] == j1939.PGN_DM1 else "dm2"] = j1939.parse_dm1_payload(bytes(data))
        except Exception:
            pass
    return frame


# --------------------------------------------------------------- 帧分发枢纽
class FrameHub:
    """rx 线程 → asyncio → 触发器/日志/WS 广播。"""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.bam = j1939.BamReassembler()

    def on_bus_frame(self, msg, direction: str) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._handle(msg, direction))
            )

    async def _handle(self, msg, direction: str) -> None:
        frame = self.frame_json(msg, direction)
        if direction == "rx" and msg.is_extended_id:
            completed = self.bam.feed(msg.arbitration_id, bytes(msg.data))
            if completed:
                frame["tp"] = {"complete": True, "pgn": completed["pgn"], "length": len(completed["data"])}
                if completed["pgn"] in (j1939.PGN_DM1, j1939.PGN_DM2):
                    try:
                        frame["dm1" if completed["pgn"] == j1939.PGN_DM1 else "dm2"] = j1939.parse_dm1_payload(completed["data"])
                    except (IndexError, ValueError):
                        pass
        if direction == "rx":  # 触发只针对接收帧，避免回环放大
            for hit in triggers.process(msg):
                if hit["action"] == "highlight":
                    frame.setdefault("highlight", []).append(hit["name"])
                elif hit["action"] == "send":
                    s = hit["send"]
                    try:
                        bus.send(s["arbitration_id"], s["data"], s["is_extended_id"])
                    except RuntimeError:
                        pass
        if logger.recording:
            logger.record(msg, direction)
        if self.clients:
            data = json.dumps(frame, ensure_ascii=False)
            dead = []
            for ws in self.clients:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)

    @staticmethod
    def frame_json(msg, direction: str) -> dict:
        frame = frame_payload(
            round(asyncio.get_running_loop().time(), 6),
            msg.arbitration_id,
            msg.is_extended_id,
            direction,
            bytes(msg.data),
        )
        if msg.is_error_frame:
            frame["error"] = True
        return frame


hub = FrameHub()
bus.listeners.append(hub.on_bus_frame)


# ------------------------------------------------------------------ 总线
@app.get("/api/interfaces")
async def list_interfaces():
    return INTERFACES


@app.post("/api/connect")
async def connect(body: dict):
    try:
        hub.bam.clear()
        return bus.connect(
            body.get("interface", "virtual"),
            body.get("channel", "test"),
            int(body.get("bitrate", 250000)),
        )
    except (RuntimeError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/disconnect")
async def disconnect():
    dm1.stop()
    senders.stop_all()
    replayer.stop()
    hub.bam.clear()
    await asyncio.sleep(0)
    return bus.disconnect()


@app.get("/api/status")
async def status():
    return {
        **bus.info(),
        "frontend_version": FRONTEND_VERSION,
        "version": APP_VERSION,
        "dm1": dm1.status(),
        "replay": replayer.status(),
        "recording": logger.recording,
        "dbc_loaded": dbc.loaded,
    }


@app.get("/api/stats/frames")
async def frame_statistics():
    return bus.frame_statistics()


@app.post("/api/send")
async def send_frame(body: dict):
    try:
        cid = int(body.get("id", ""), 16)
        data = bytes.fromhex(body.get("data", ""))
        is_extended = _parse_bool(body.get("extended"), True)
        _validate_can_id(cid, is_extended)
        bus.send(cid, data, is_extended)
        return {"ok": True}
    except (ValueError, RuntimeError, pycan.CanError) as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- 发送任务
@app.get("/api/senders")
async def list_senders():
    return senders.list()


@app.post("/api/senders")
async def create_sender(body: dict):
    try:
        return senders.create(
            body.get("name", "task"),
            int(body.get("id", ""), 16),
            body.get("data", ""),
            int(body.get("period_ms", 100)),
            _parse_bool(body.get("extended"), True),
            body.get("auto_start", True),
            body.get("mode", "fixed"),
            int(body.get("inc_byte", 0)),
            int(body.get("inc_step", 1)),
            int(body["inc_end"]) if body.get("inc_end") is not None else None,
            data_list=body.get("data_list"),
            random_seed=body.get("random_seed", 0), random_mask=body.get("random_mask", ""),
            ramp_min=body.get("ramp_min", 0), ramp_max=body.get("ramp_max", 255),
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


@app.put("/api/senders/{sid}")
async def update_sender(sid: str, body: dict):
    """在线修改周期任务（数据/周期/模式/递增参数），运行中下一周期生效。"""
    try:
        return senders.update(sid, **body)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/senders/{sid}/start")
async def start_sender(sid: str):
    try:
        return senders.start(sid)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/senders/{sid}/duplicate")
async def duplicate_sender(sid: str):
    try:
        return senders.duplicate(sid)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/api/senders/{sid}/stop")
async def stop_sender(sid: str):
    try:
        return senders.stop(sid)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/senders/{sid}")
async def remove_sender(sid: str):
    senders.remove(sid)
    return {"ok": True}


# -------------------------------------------------------------------- DBC
@app.post("/api/dbc")
async def upload_dbc(file: UploadFile):
    DBC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    path = DBC_UPLOAD_DIR / Path(file.filename or "upload.dbc").name
    path.write_bytes(content)
    try:
        return dbc.load(str(path))
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"DBC 解析失败: {e}")


@app.get("/api/dbc/messages")
async def dbc_messages():
    return dbc.messages()


@app.delete("/api/dbc")
async def unload_dbc():
    dbc.db = None
    return {"ok": True}


@app.post("/api/dbc/encode")
async def dbc_encode(body: dict):
    try:
        data = dbc.encode(body["message"], body.get("signals", {}))
        return {"data": data.hex().upper()}
    except Exception as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- DM1 模拟
@app.get("/api/dm1")
async def dm1_status():
    return dm1.status()


@app.put("/api/dm1")
async def dm1_update(body: dict):
    try:
        return dm1.update(body)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/dm1/start")
async def dm1_start():
    try:
        return dm1.start()
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/api/dm1/send_once")
async def dm1_send_once():
    """立即按当前配置打包并发送一组 DM1（不启动周期广播）。"""
    try:
        return dm1.send_once()
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/api/dm1/stop")
async def dm1_stop():
    return dm1.stop()


@app.get("/api/scenarios")
async def list_scenarios():
    out = []
    if SCENARIO_DIR.exists():
        for p in sorted(SCENARIO_DIR.glob("*.json")):
            cfg = json.loads(p.read_text(encoding="utf-8"))
            out.append({"file": p.name, "name": cfg.get("name", p.stem), "config": cfg})
    return out


@app.post("/api/scenarios/{file}/apply")
async def apply_scenario(file: str):
    path = SCENARIO_DIR / Path(file).name
    if not path.exists():
        raise HTTPException(404, "场景不存在")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return dm1.update(cfg)


# ---------------------------------------------------------------- 日志回放
@app.post("/api/log/start")
async def log_start(body: dict):
    try:
        return logger.start(body.get("format", "csv"))
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.post("/api/log/stop")
async def log_stop():
    return logger.stop()


@app.get("/api/log/files")
async def log_files():
    return logger.files()


@app.delete("/api/log/{name}")
async def log_delete(name: str):
    """删除日志目录中的日志文件，不接受目录或路径穿越。"""
    path = _logger_mod.LOG_DIR / Path(name).name
    if path.suffix not in (".csv", ".asc") or not path.is_file():
        raise HTTPException(404, "日志文件不存在")
    current = Path(getattr(logger._file, "name", "")).resolve() if logger.recording else None
    if current and path.resolve() == current:
        raise HTTPException(409, "正在记录的日志不能删除，请先停止记录")
    path.unlink()
    return {"ok": True, "file": path.name}


@app.get("/api/log/download/{name}")
async def log_download(name: str):
    path = _logger_mod.LOG_DIR / Path(name).name
    if not path.is_file() or path.suffix not in (".csv", ".asc"):
        raise HTTPException(404, "日志文件不存在")
    return FileResponse(path, filename=path.name)


def _read_log_csv(path: Path, limit: int = 1000) -> dict:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    total = len(rows)
    if limit > 0:
        rows = rows[-limit:]
    frames = [
        frame_payload(float(r["ts"]), int(r["id"], 16), bool(int(r["extended"])),
                      r["dir"], bytes.fromhex(r["data"]))
        for r in rows
    ]
    return {"file": path.name, "count": len(frames), "total": total, "frames": frames}


def _read_log_asc(path: Path, limit: int = 1000) -> dict:
    pattern = re.compile(
        r"^\s*(?P<ts>\S+)\s+\S+\s+(?P<id>[0-9A-Fa-f]+)(?P<ext>x)?\s+"
        r"(?P<dir>RX|TX)\s+d\s+(?P<dlc>\d+)\s+(?P<data>[0-9A-Fa-f]*)\s*$",
        re.IGNORECASE,
    )
    frames = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        data = bytes.fromhex(match["data"])
        frames.append(frame_payload(float(match["ts"]), int(match["id"], 16),
                                    bool(match["ext"]), match["dir"].lower(), data))
    total = len(frames)
    if limit > 0:
        frames = frames[-limit:]
    return {"file": path.name, "count": len(frames), "total": total, "frames": frames}


@app.get("/api/log/read/{name}")
async def log_read(name: str, limit: int = 1000):
    """读取日志回看：返回与实时 WS 同构的帧列表（含 J1939/DBC 解析）。"""
    path = _logger_mod.LOG_DIR / Path(name).name
    if not path.exists() or path.suffix not in (".csv", ".asc"):
        raise HTTPException(404, "日志文件不存在")
    return _read_log_csv(path, limit) if path.suffix == ".csv" else _read_log_asc(path, limit)


@app.post("/api/log/read_file")
async def log_read_file(body: dict):
    """从任意自定义路径读取日志回看（打开文件）。"""
    raw = str(body.get("path", "")).strip()
    path = Path(raw)
    if not raw or not path.is_absolute():
        raise HTTPException(400, "需要绝对路径")
    if not path.exists() or path.suffix.lower() != ".csv":
        raise HTTPException(404, f"文件不存在或不是 CSV: {raw}")
    return _read_log_csv(path, int(body.get("limit", 1000)))


@app.post("/api/log/replay")
async def log_replay(body: dict):
    try:
        return replayer.start(body.get("file", ""), float(body.get("speed", 1.0)))
    except (RuntimeError, FileNotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/log/replay/stop")
async def log_replay_stop():
    return replayer.stop()


@app.get("/api/log/replay/status")
async def log_replay_status():
    return replayer.status()


# ------------------------------------------------------------------ 触发
@app.get("/api/triggers")
async def list_triggers():
    return triggers.list()


@app.post("/api/triggers")
async def add_trigger(body: dict):
    try:
        if "send_extended" in body:
            body = {**body, "send_extended": _parse_bool(body["send_extended"])}
        return triggers.add(**body)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))


@app.put("/api/triggers/{rid}")
async def update_trigger(rid: str, body: dict):
    try:
        if "send_extended" in body:
            body = {**body, "send_extended": _parse_bool(body["send_extended"])}
        return triggers.update(rid, **body)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e))


@app.delete("/api/triggers/{rid}")
async def remove_trigger(rid: str):
    triggers.remove(rid)
    return {"ok": True}


@app.post("/api/triggers/reset_hits")
async def reset_trigger_hits():
    triggers.reset_hits()
    return {"ok": True}


@app.post("/api/triggers/set_enabled")
async def set_triggers_enabled(body: dict):
    if "enabled" not in body:
        raise HTTPException(400, "enabled 参数必填")
    enabled = _parse_bool(body["enabled"])
    triggers.set_enabled(enabled)
    return {"ok": True, "enabled": enabled, "count": len(triggers.rules)}


# ------------------------------------------------------------- 配置保存/读取
_SENDER_KEYS = ("name", "arbitration_id", "data_hex", "period_ms", "is_extended_id",
                "mode", "inc_byte", "inc_end", "inc_step", "data_list", "running",
                "random_seed", "random_mask", "ramp_min", "ramp_max")


def _preset_payload(name: str) -> dict:
    tasks = [{k: t[k] for k in _SENDER_KEYS if k in t} for t in senders.list()]
    return {
        "name": name,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "senders": tasks,
        "dm1": dict(dm1.config),
        "triggers": triggers.list(),
    }


def _apply_preset(data: dict) -> int:
    """按配置现场重建：清空现有任务并恢复（含运行状态），同时恢复 DM1 配置与触发规则。"""
    for t in senders.list():
        senders.remove(t["id"])
    created = 0
    for t in data.get("senders", []):
        try:
            senders.create(
                t.get("name", "task"), t["arbitration_id"], t["data_hex"],
                t["period_ms"], t.get("is_extended_id", True), bool(t.get("running")),
                t.get("mode", "fixed"), t.get("inc_byte", 0),
                t.get("inc_step", 1), t.get("inc_end"),
                data_list=t.get("data_list"),
                random_seed=t.get("random_seed", 0), random_mask=t.get("random_mask", ""),
                ramp_min=t.get("ramp_min", 0), ramp_max=t.get("ramp_max", 255),
            )
            created += 1
        except (KeyError, ValueError):
            continue  # 跳过坏任务，其余照常恢复
    if "dm1" in data:
        dm1.update(data["dm1"])
    if "triggers" in data:
        triggers.replace(data["triggers"])
    return created


@app.get("/api/presets")
async def list_presets():
    out = []
    PRESET_DIR.mkdir(exist_ok=True)
    for p in sorted(PRESET_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if "triggers" in data and "senders" not in data:
                continue  # 纯触发规则文件，不在场景列表显示
            out.append({
                "file": p.name,
                "name": data.get("name", p.stem),
                "saved_at": data.get("saved_at", ""),
                "tasks": len(data.get("senders", [])),
            })
        except Exception:
            continue
    return out


@app.post("/api/presets")
async def save_preset(body: dict):
    """把当前全部周期任务 + DM1 配置保存到配置目录。"""
    name = str(body.get("name", "")).strip() or time.strftime("%m%d_%H%M%S")
    if len(name) > 50:
        raise HTTPException(400, "配置名过长（≤50 字符）")
    PRESET_DIR.mkdir(exist_ok=True)
    # 文件名用 ASCII（避免路径编码问题），中文显示名保存在 JSON 内
    file = f"preset_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.json"
    data = _preset_payload(name)
    (PRESET_DIR / file).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "file": file, "name": name, "tasks": len(data["senders"])}


@app.post("/api/presets/{file}/load")
async def load_preset(file: str):
    """从配置目录读取现场。"""
    path = PRESET_DIR / Path(file).name
    if not path.exists():
        raise HTTPException(404, "配置不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    created = _apply_preset(data)
    return {"ok": True, "tasks": created, "dm1": dm1.status()}


@app.post("/api/presets/save_to")
async def save_preset_to(body: dict):
    """保存到任意自定义路径（另存为）。"""
    raw = str(body.get("path", "")).strip()
    if not raw:
        raise HTTPException(400, "请提供完整文件路径")
    path = Path(raw)
    if not path.is_absolute():
        raise HTTPException(400, "需要绝对路径")
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(400, f"目录不可用: {e}")
    name = body.get("name") or path.stem
    data = _preset_payload(str(name))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path), "name": name, "tasks": len(data["senders"])}


@app.post("/api/presets/load_from")
async def load_preset_from(body: dict):
    """从任意自定义路径读取现场（打开文件）。"""
    raw = str(body.get("path", "")).strip()
    path = Path(raw)
    if not raw or not path.is_absolute():
        raise HTTPException(400, "需要绝对路径")
    if not path.exists() or path.suffix.lower() != ".json":
        raise HTTPException(404, f"文件不存在或不是 JSON: {raw}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(400, f"JSON 解析失败: {e}")
    created = _apply_preset(data)
    return {"ok": True, "path": str(path), "tasks": created, "dm1": dm1.status()}


@app.get("/api/filepicker")
async def file_picker(mode: str = "open", ext: str = "json"):
    """弹出系统文件对话框（本机运行时可用），返回选择的完整路径。"""
    if mode not in {"open", "save", "directory"}:
        raise HTTPException(400, "无效的文件选择模式")
    types = {"json": [("JSON 文件", "*.json"), ("所有文件", "*.*")],
             "csv": [("CSV 日志", "*.csv"), ("所有文件", "*.*")],
             "dbc": [("DBC 文件", "*.dbc"), ("所有文件", "*.*")]}.get(ext, [("所有文件", "*.*")])

    def _pick() -> str:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            if mode == "directory":
                return filedialog.askdirectory(parent=root, title="选择保存文件夹", mustexist=True)
            if mode == "save":
                return filedialog.asksaveasfilename(
                    parent=root, defaultextension=f".{ext}", filetypes=types, title="保存文件", confirmoverwrite=True)
            return filedialog.askopenfilename(parent=root, filetypes=types, title="选择文件")
        finally:
            root.destroy()

    try:
        path = await asyncio.get_running_loop().run_in_executor(None, _pick)
    except Exception as e:
        raise HTTPException(400, f"无法打开文件对话框（无 GUI 环境？）: {e}")
    return {"path": path or None}


# --------------------------------------------------------- 触发规则保存/读取
def _trig_payload(name: str) -> dict:
    return {
        "name": name,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "triggers": triggers.list(),
    }


def _trig_write(path: Path, name: str) -> dict:
    data = _trig_payload(name)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path), "name": name, "rules": len(data["triggers"])}


def _trig_load(data) -> int:
    rules = data["triggers"] if isinstance(data, dict) else data
    if not isinstance(rules, list):
        raise ValueError("文件中没有 triggers 规则列表")
    return triggers.replace(rules)


@app.get("/api/triggers/presets")
async def list_trig_presets():
    out = []
    PRESET_DIR.mkdir(exist_ok=True)
    for p in sorted(PRESET_DIR.glob("trig_*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "file": p.name,
                "name": data.get("name", p.stem),
                "saved_at": data.get("saved_at", ""),
                "rules": len(data.get("triggers", [])),
            })
        except Exception:
            continue
    return out


@app.post("/api/triggers/presets")
async def save_trig_preset(body: dict):
    name = str(body.get("name", "")).strip() or time.strftime("%m%d_%H%M%S")
    if len(name) > 50:
        raise HTTPException(400, "名称过长（≤50 字符）")
    PRESET_DIR.mkdir(exist_ok=True)
    file = f"trig_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.json"
    result = _trig_write(PRESET_DIR / file, name)
    result["file"] = file
    return result


@app.post("/api/triggers/presets/{file}/load")
async def load_trig_preset(file: str):
    path = PRESET_DIR / Path(file).name
    if not path.exists():
        raise HTTPException(404, "规则文件不存在")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        n = _trig_load(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "rules": n}


@app.delete("/api/triggers/presets/{file}")
async def delete_trig_preset(file: str):
    (PRESET_DIR / Path(file).name).unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/triggers/save_to")
async def save_trig_to(body: dict):
    """触发规则另存为任意路径。"""
    raw = str(body.get("path", "")).strip()
    if not raw:
        raise HTTPException(400, "请提供完整文件路径")
    path = Path(raw)
    if not path.is_absolute():
        raise HTTPException(400, "需要绝对路径")
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(400, f"目录不可用: {e}")
    return _trig_write(path, body.get("name") or path.stem)


@app.post("/api/triggers/load_from")
async def load_trig_from(body: dict):
    """从任意路径读取触发规则（整体替换当前规则）。"""
    raw = str(body.get("path", "")).strip()
    path = Path(raw)
    if not raw or not path.is_absolute():
        raise HTTPException(400, "需要绝对路径")
    if not path.exists() or path.suffix.lower() != ".json":
        raise HTTPException(404, f"文件不存在或不是 JSON: {raw}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        n = _trig_load(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"JSON 解析失败: {e}")
    return {"ok": True, "path": str(path), "rules": n}


@app.delete("/api/presets/{file}")
async def delete_preset(file: str):
    path = PRESET_DIR / Path(file).name
    path.unlink(missing_ok=True)
    return {"ok": True}


# ---------------------------------------------------------------- WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # 忽略客户端消息（心跳等）
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


# ------------------------------------------------------------------ 静态页
@app.post('/api/files/analyze')
async def analyze_upload(file: UploadFile, sheet: str = Form(''), id_base: int = Form(16), time_unit: str = Form('s')):
    try:
        content = await file.read(MAX_BYTES + 1)
        return await run_in_threadpool(analyze_file, file.filename or '', content, sheet, id_base, time_unit)
    except Exception as exc:
        raise HTTPException(400, f'无法分析文件：{exc}') from exc
    finally:
        await file.close()


app.mount("/", StaticFiles(directory=RESOURCE_DIR / "web", html=True), name="web")
