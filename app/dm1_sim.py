"""发动机故障(DM1)模拟引擎。

按配置周期广播 DM1：DTC 数量决定单包（<=1 个 DTC，载荷 <= 8 字节）
或多包 TP.BAM（>=2 个 DTC）。SA 默认 0x00（模拟发动机 ECU）。
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from time import perf_counter
from typing import Optional

import can

from . import j1939
from .bus import BusService

LAMP_STATES = {"off": j1939.LAMP_OFF, "on": j1939.LAMP_ON, "blink": j1939.LAMP_ON, "na": j1939.LAMP_NA}


def lamps_from_config(cfg: dict) -> bytes:
    flash = 0xFF
    for name, shift in (("mil", 6), ("red", 4), ("amber", 2), ("protect", 0)):
        state = cfg.get(name, "off")
        if state not in LAMP_STATES:
            raise ValueError(f"未知灯状态: {state}")
        if state == "blink":
            flash &= ~(3 << shift)  # 慢闪 1Hz；状态字节仍为亮
    return j1939.encode_lamps(
        mil=LAMP_STATES.get(cfg.get("mil", "off"), 0),
        red=LAMP_STATES.get(cfg.get("red", "off"), 0),
        amber=LAMP_STATES.get(cfg.get("amber", "off"), 0),
        protect=LAMP_STATES.get(cfg.get("protect", "off"), 0),
        flash=flash,
    )


class Dm1Sim:
    def __init__(self, bus: BusService) -> None:
        self._bus = bus
        self._task: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()
        self._oc_history: dict[tuple[int, int, int], int] = {}
        self.config: dict = {
            "dtcs": [],  # [{spn, fmi, oc}]
            "lamps": {"mil": "off", "red": "off", "amber": "off", "protect": "off"},
            "sa": 0x00,
            "extended": True,
            "standard_id": 0x123,  # 标准帧为自定义载荷，不是 J1939
            "da": None,  # 目标地址：None=广播(PDU1 默认 FF)；仅 PDU1 格式 PGN 生效
            "priority": 6,
            "period_ms": 1000,  # SAE 推荐 DM1 1s 周期
            "pgn": j1939.PGN_DM1,  # 可自定义：DM2(65227)、私有 PGN 等
            "tp_cm_id": None,  # 多包通告帧完整 ID：None=跟随节点自动(标准 TP EC + 优先级 + SA)
            "tp_dt_id": None,  # 多包数据帧完整 ID：None=跟随节点自动(标准 TP ED + 优先级 + SA)
            "oc_auto_inc": False,  # 删除后重新添加同一故障时 +1，126 饱和，127 不可用
        }
        self.sent_frames = 0
        self.last_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def update(self, cfg: dict) -> dict:
        """合并配置；运行中修改下一周期生效。

        支持直接给完整 29bit ID（arb_id），内部自动拆解为优先级/PGN/DA/SA。
        """
        previous = self.config
        self.config = deepcopy(previous)
        try:
            self._update_config(cfg)
            active = {(previous['sa'], d['spn'], d['fmi']) for d in previous['dtcs']}
            for d in self.config['dtcs']:
                key = (self.config['sa'], d['spn'], d['fmi'])
                if self.config['oc_auto_inc'] and key not in active and key in self._oc_history:
                    old = self._oc_history[key]
                    d['oc'] = min(old + 1, 126) if old != 127 else 127
            result = self.status()  # 包括长度校验；失败不提交配置或计数
        except Exception:
            self.config = previous
            raise
        for d in self.config['dtcs']:
            self._oc_history[(self.config['sa'], d['spn'], d['fmi'])] = d.get('oc', 1)
        return result

    def _update_config(self, cfg: dict) -> None:
        cfg = deepcopy(cfg)
        extended = cfg.get('extended', self.config['extended'])
        if not isinstance(extended, bool):
            raise ValueError("extended 必须为布尔值")
        if not extended and cfg.get('arb_id') is not None:
            cfg['standard_id'] = cfg.pop('arb_id')
        if cfg.get("arb_id") is not None:
            aid = int(cfg["arb_id"])
            if not 0 <= aid <= 0x1FFFFFFF:
                raise ValueError(f"ID 超出 29bit 范围: {hex(aid)}")
            info = j1939.decode_id(aid)
            self.config["priority"] = info["priority"]
            self.config["pgn"] = info["pgn"]
            self.config["sa"] = info["sa"]
            self.config["da"] = info["da"] if info["is_pdu1"] else None
            cfg.pop("arb_id")
        for key in ("dtcs", "lamps", "sa", "da", "priority", "period_ms", "pgn",
                    "tp_cm_id", "tp_dt_id", "oc_auto_inc", "extended", "standard_id"):
            if key in cfg:
                self.config[key] = cfg[key]
        if not isinstance(self.config['standard_id'], int) or not 0 <= self.config['standard_id'] <= 0x7FF:
            raise ValueError("标准帧 ID 须为 000-7FF (hex)")
        if not 0 <= self.config["sa"] <= 255:
            raise ValueError(f"源地址 SA 须为 0-255，当前: {self.config['sa']}")
        if self.config["da"] is not None and not 0 <= self.config["da"] <= 255:
            raise ValueError(f"目标地址 DA 须为 0-255 或留空，当前: {self.config['da']}")
        for pk in ("pgn",):
            if not 0 <= self.config[pk] <= 0x3FFFF:
                raise ValueError(f"PGN 须为 0-0x3FFFF（{pk}），当前: {self.config[pk]}")
        for tk in ("tp_cm_id", "tp_dt_id"):
            if self.config[tk] is not None and not 0 <= self.config[tk] <= 0x1FFFFFFF:
                raise ValueError(f"ID 须为 0-0x1FFFFFFF（{tk}），当前: {hex(self.config[tk])}")
        if not 0 <= self.config["priority"] <= 7:
            raise ValueError(f"优先级须为 0-7，当前: {self.config['priority']}")
        if self.config["period_ms"] < 10:
            raise ValueError("周期最小 10ms")
        # 校验 DTC 字段
        for d in self.config["dtcs"]:
            j1939.DTC(**d)
        lamps_from_config(self.config['lamps'])

    def _effective_lamps(self) -> bytes:
        return lamps_from_config(self.config["lamps"])

    def _build_frames(self) -> list[can.Message]:
        dtcs = [j1939.DTC(**d) for d in self.config["dtcs"]]
        if not self.config['extended']:
            payload = j1939.build_dm1_payload(dtcs, self._effective_lamps())
            if len(payload) > 8:
                raise ValueError("标准帧仅支持 0 或 1 个 DTC（最多 8 字节）；多故障请使用扩展帧")
            return [can.Message(arbitration_id=self.config['standard_id'],
                                is_extended_id=False, data=payload.ljust(8, b'\xff'))]
        return j1939.dm1_frames(
            dtcs, self._effective_lamps(),
            sa=self.config["sa"], priority=self.config["priority"],
            pgn=self.config["pgn"], da=self.config.get("da"),
            cm_id=self.config.get("tp_cm_id"),
            dt_id=self.config.get("tp_dt_id"),
        )

    def preview(self) -> dict:
        """预览 J1939 打包结果：模式 + 每一帧的 ID/数据/说明。"""
        payload = j1939.build_dm1_payload(
            [j1939.DTC(**d) for d in self.config["dtcs"]], self._effective_lamps()
        )
        frames = self._build_frames()
        if len(frames) == 1:
            descs = ["故障报文单帧"]
        else:
            descs = ["TP.CM BAM 通告"] + [f"TP.DT 数据包 #{i}" for i in range(1, len(frames))]
        return {
            "mode": "single" if len(frames) == 1 else "bam",
            "frame_count": len(frames),
            "payload_len": len(payload),
            "frames": [
                {
                    "id": f"{f.arbitration_id:08X}" if f.is_extended_id else f"{f.arbitration_id:03X}",
                    "extended": f.is_extended_id,
                    "data": bytes(f.data).hex().upper(),
                    "desc": desc,
                }
                for f, desc in zip(frames, descs)
            ],
        }

    async def send_once(self) -> dict:
        """立即按当前配置打包并发送一组 DM1（不启动周期）。"""
        async with self._send_lock:
            frames = self._build_frames()
            preview = self.preview()
            try:
                for i, f in enumerate(frames):
                    if i:
                        deadline = perf_counter() + 0.05
                        while (remaining := deadline - perf_counter()) > 0:
                            await asyncio.sleep(remaining)  # 防止 Windows 定时器提前唤醒
                    self._bus.send(f.arbitration_id, bytes(f.data), f.is_extended_id)
                    self.sent_frames += 1
            except RuntimeError as e:
                self.last_error = str(e)
                raise
            return {"sent": len(frames), "preview": preview}

    def start(self) -> dict:
        if self.running:
            return self.status()
        self.last_error = None
        self._task = asyncio.get_running_loop().create_task(self._run())
        return self.status()

    def stop(self) -> dict:
        if self._task:
            self._task.cancel()
            self._task = None
        return self.status()

    async def _run(self) -> None:
        try:
            while True:
                started = asyncio.get_running_loop().time()
                try:
                    await self.send_once()
                except RuntimeError as e:
                    self.last_error = str(e)
                    break
                elapsed = asyncio.get_running_loop().time() - started
                await asyncio.sleep(max(0, self.config["period_ms"] / 1000 - elapsed))
        except asyncio.CancelledError:
            pass

    def status(self) -> dict:
        return {
            "running": self.running,
            "config": self.config,
            "preview": self.preview(),
            "sent_frames": self.sent_frames,
            "last_error": self.last_error,
        }
