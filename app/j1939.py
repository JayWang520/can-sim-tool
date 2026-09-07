"""J1939 轻量编解码：29bit ID / PGN / DTC / DM1 单包与多包(TP.BAM)。

实现本工具需要的部分（组包发送 + 基本解析 + TP.BAM 接收重组）。
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional

import can

# 常用 PGN
PGN_TP_CM = 60416  # 0xEC00 标准传输协议-连接管理 TP.CM (J1939-21, PDU1)
PGN_TP_DT = 60672  # 0xED00 标准传输协议-数据传送 TP.DT (J1939-21, PDU1)
PGN_ETP_CM = 60160  # 0xEB00 扩展传输协议-连接管理 (J1939-22, 仅参考)
PGN_ETP_DT = 60161  # 0xEB01 扩展传输协议-数据传送 (J1939-22, 仅参考)
PGN_DM1 = 65226  # 0xFECA 当前故障码
PGN_DM2 = 65227  # 0xFECB 历史故障码

PDU1_PF_MAX = 239  # PF <= 239 为 PDU1(点对点)，PF >= 240 为 PDU2(广播)


class BamReassembler:
    """按发送源和目标 PGN 维护 J1939 TP.BAM 接收会话。"""

    def __init__(self, timeout: float = 2.0) -> None:
        self._sessions: dict[tuple[int, int], dict] = {}
        self.timeout = timeout

    def feed(self, cid: int, data: bytes) -> Optional[dict]:
        now = time.monotonic()
        self._sessions = {
            key: session for key, session in self._sessions.items()
            if now - session["updated"] <= self.timeout
        }
        info = decode_id(cid)
        if info["pgn"] == PGN_TP_CM and len(data) >= 8 and data[0] == 0x20:
            length = data[1] | (data[2] << 8)
            packets = data[3]
            pgn = data[5] | (data[6] << 8) | (data[7] << 16)
            if 0 < length <= 1785 and packets == (length + 6) // 7:
                self._sessions[(info["sa"], pgn)] = {
                    "length": length, "packets": packets, "next": 1,
                    "data": bytearray(), "updated": now,
                }
            return None
        if info["pgn"] != PGN_TP_DT or len(data) < 2:
            return None
        seq = data[0]
        for (sa, pgn), session in list(self._sessions.items()):
            if sa != info["sa"]:
                continue
            if seq != session["next"]:
                del self._sessions[(sa, pgn)]
                return None
            session["data"].extend(data[1:8])
            session["next"] += 1
            session["updated"] = now
            if seq == session["packets"]:
                payload = bytes(session["data"][: session["length"]])
                del self._sessions[(sa, pgn)]
                return {"pgn": pgn, "sa": sa, "data": payload}
            return None
        return None

    def clear(self) -> None:
        self._sessions.clear()

# 故障灯状态值（每种灯 2bit）：0=灭 1=亮 2=闪烁 3=不可用
LAMP_OFF, LAMP_ON, LAMP_BLINK, LAMP_NA = 0, 1, 2, 3


# --------------------------------------------------------------------- ID
def encode_id(priority: int, pgn: int, sa: int, da: Optional[int] = None) -> int:
    """组 29bit ID。PDU2 忽略 da；PDU1 的 da 默认广播 0xFF。"""
    if not 0 <= priority <= 7:
        raise ValueError(f"优先级 0-7: {priority}")
    pf = (pgn >> 8) & 0xFF
    if pf <= PDU1_PF_MAX:  # PDU1: PS = 目标地址
        ps = 0xFF if da is None else da
    else:  # PDU2: PS = 组扩展（PGN 低 8 位）
        ps = pgn & 0xFF
    return (priority << 26) | ((pgn & 0x3FF00) << 8) | (ps << 8) | sa


def decode_id(cid: int) -> dict:
    priority = (cid >> 26) & 0x07
    reserved = (cid >> 25) & 0x01
    data_page = (cid >> 24) & 0x01
    pf = (cid >> 16) & 0xFF
    ps = (cid >> 8) & 0xFF
    sa = cid & 0xFF
    is_pdu1 = pf <= PDU1_PF_MAX
    pgn = (reserved << 17) | (data_page << 16) | (pf << 8) | (0 if is_pdu1 else ps)
    return {
        "priority": priority,
        "pgn": pgn,
        "pf": pf,
        "ps": ps,
        "sa": sa,
        "da": ps if is_pdu1 else None,  # PDU2 无目标地址
        "is_pdu1": is_pdu1,
    }


def pgn_of(cid: int) -> int:
    return decode_id(cid)["pgn"]


# -------------------------------------------------------------------- DTC
@dataclass
class DTC:
    spn: int  # 可疑参数编号 19bit
    fmi: int  # 故障模式标识符 5bit
    oc: int = 1  # 发生次数 7bit
    cm: int = 0  # 转换方式 1bit: 0=OBDII 1=SAE

    def __post_init__(self) -> None:
        self.encode()  # 触发字段范围校验

    def encode(self) -> bytes:
        if not 0 <= self.spn <= 0x7FFFF:
            raise ValueError(f"SPN 超出 19bit: {self.spn}")
        if not 0 <= self.fmi <= 0x1F:
            raise ValueError(f"FMI 超出 5bit: {self.fmi}")
        b0 = self.spn & 0xFF
        b1 = (self.spn >> 8) & 0xFF
        b2 = ((self.spn >> 16) & 0x07) | ((self.fmi & 0x1F) << 3)
        b3 = (self.oc & 0x7F) | ((self.cm & 0x01) << 7)
        return bytes([b0, b1, b2, b3])

    @classmethod
    def decode(cls, raw: bytes) -> "DTC":
        spn = raw[0] | (raw[1] << 8) | ((raw[2] & 0x07) << 16)
        fmi = (raw[2] >> 3) & 0x1F
        oc = raw[3] & 0x7F
        cm = (raw[3] >> 7) & 0x01
        return cls(spn=spn, fmi=fmi, oc=oc, cm=cm)


def encode_lamps(mil: int = 0, red: int = 0, amber: int = 0, protect: int = 0) -> bytes:
    """故障灯状态 2 字节。byte0 各灯 2bit，byte1 保留为 0xFF。"""
    b0 = (mil << 6) | (red << 4) | (amber << 2) | protect
    return bytes([b0 & 0xFF, 0xFF])


def parse_dm1_payload(data: bytes) -> dict:
    """解析 DM1 载荷（单包或重组后）：灯状态 + DTC 列表。"""
    lamps = data[0]
    dtcs = [DTC.decode(data[i : i + 4]) for i in range(2, len(data) - 3, 4)]
    return {
        "lamps": {
            "mil": (lamps >> 6) & 0x3,
            "red": (lamps >> 4) & 0x3,
            "amber": (lamps >> 2) & 0x3,
            "protect": lamps & 0x3,
        },
        "dtcs": [{"spn": d.spn, "fmi": d.fmi, "oc": d.oc, "cm": d.cm} for d in dtcs],
    }


# ------------------------------------------------------------------- DM1
def build_dm1_payload(dtcs: list[DTC], lamps: bytes) -> bytes:
    return bytes(lamps) + b"".join(d.encode() for d in dtcs)


def dm1_frames(
    dtcs: list[DTC],
    lamps: bytes = b"\xff\xff",
    sa: int = 0x00,
    priority: int = 6,
    pgn: int = PGN_DM1,
    da: Optional[int] = None,
    pad_to_eight: bool = True,
    cm_id: Optional[int] = None,
    dt_id: Optional[int] = None,
) -> list[can.Message]:
    """生成故障报文（默认模拟发动机 ECU：SA=0x00、DM1、优先级 6）。

    - 无 DTC 或 1 个 DTC（载荷 <= 8 字节）：单帧直发
      PDU1 格式的 PGN（PF <= 0xEF）可指定 da 点对点发送；PDU2 忽略 da
    - 载荷 > 8 字节：TP.BAM 广播序列（CM_BAM + 数据包；BAM 无 EndOfMsg 响应）
      传输帧默认按标准 TP 生成（CM=PGN EC00、DT=PGN ED00，带主节点的优先级和 SA）；
      给 cm_id/dt_id 传入完整 29bit ID 可分别完全自定义两个传输帧
    """
    payload = build_dm1_payload(dtcs, lamps)
    cid = encode_id(priority, pgn, sa, da=da)
    if len(payload) <= 8:
        if pad_to_eight:
            payload = payload + b"\xff" * (8 - len(payload))
        return [can.Message(arbitration_id=cid, is_extended_id=True, data=payload)]

    # ---- 多包：TP.BAM
    n_packets = (len(payload) + 6) // 7
    cm_data = bytes(
        [
            0x20,  # BAM 控制字节
            len(payload) & 0xFF,
            (len(payload) >> 8) & 0xFF,
            n_packets,
            0xFF,
            pgn & 0xFF,
            (pgn >> 8) & 0xFF,
            (pgn >> 16) & 0xFF,
        ]
    )
    cm_cid = cm_id if cm_id is not None else encode_id(priority, PGN_TP_CM, sa, da=0xFF)
    dt_cid = dt_id if dt_id is not None else encode_id(priority, PGN_TP_DT, sa, da=0xFF)
    frames = [
        can.Message(arbitration_id=cm_cid, is_extended_id=True, data=cm_data)
    ]
    for seq in range(1, n_packets + 1):
        chunk = payload[(seq - 1) * 7 : seq * 7]
        chunk = chunk + b"\xff" * (7 - len(chunk))
        frames.append(
            can.Message(
                arbitration_id=dt_cid,
                is_extended_id=True,
                data=bytes([seq]) + chunk,
            )
        )
    return frames
