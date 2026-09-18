"""接收过滤与触发规则。纯逻辑模块，便于测试。"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from typing import Optional

import can


_CMP_OPS = {"==", "!=", ">", "<", ">=", "<="}


def _cmp(a: int, op: str, b: int) -> bool:
    return {
        "==": a == b, "!=": a != b, ">": a > b, "<": a < b,
        ">=": a >= b, "<=": a <= b,
    }.get(op, a == b)


def _check_cond(cond: dict, data: bytes) -> bool:
    """数据条件求值。bit 序号 0-63（字节×8 + 位，位从低位起）；多字节区间按小端。"""
    t = cond.get("type")
    try:
        if t == "byte":
            i = int(cond["index"])
            return i < len(data) and _cmp(data[i], cond.get("op", "=="), int(cond["value"]))
        if t == "bytes":
            s, e = int(cond["start"]), int(cond["end"])
            return e < len(data) and _cmp(
                int.from_bytes(data[s : e + 1], "little"), cond.get("op", "=="), int(cond["value"])
            )
        if t == "bit":
            i = int(cond.get("index", cond.get("bit", -1)))
            return i // 8 < len(data) and ((data[i // 8] >> (i % 8)) & 1) == int(cond["value"])
        if t == "bits":
            b = int(cond["byte"])
            s, e = int(cond["start"]), int(cond["end"])
            if b >= len(data):
                return False
            mask = (1 << (e - s + 1)) - 1
            return ((data[b] >> s) & mask) == int(cond["value"])
    except (KeyError, ValueError, TypeError):
        return False
    return False


@dataclass
class Rule:
    name: str
    match_id: Optional[str] = None  # hex，如 "18FECA00"；留空表示不按 ID 匹配
    match_pgn: Optional[int] = None  # 按 PGN 十进制匹配（与 match_id 取或）
    data_contains: Optional[str] = None  # 数据包含该 hex 串
    data_cond: list = field(default_factory=list)
    data_cond_mode: str = "and"  # 字节/位条件之间的关系；旧规则默认 AND
    action: str = "highlight"  # highlight | count | send
    send_id: Optional[str] = None
    send_data: Optional[str] = None
    send_extended: bool = True
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    hits: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "match_id": self.match_id, "match_pgn": self.match_pgn,
            "data_contains": self.data_contains, "data_cond": self.data_cond,
            "data_cond_mode": self.data_cond_mode,
            "action": self.action,
            "send_id": self.send_id, "send_data": self.send_data,
            "send_extended": self.send_extended,
            "enabled": self.enabled, "hits": self.hits,
        }


_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


class TriggerService:
    def __init__(self) -> None:
        self.rules: list[Rule] = []

    def add(self, **kw) -> dict:
        rule = Rule(**kw)
        self._validate(rule)
        self.rules.append(rule)
        return rule.to_dict()

    def update(self, rid: str, **kw) -> dict:
        rule = self._get(rid)
        candidate = replace(rule)
        for k, v in kw.items():
            if k in Rule.__dataclass_fields__ and k not in {"id", "hits"}:
                setattr(candidate, k, v)
        self._validate(candidate)
        self.rules[self.rules.index(rule)] = candidate
        return candidate.to_dict()

    def remove(self, rid: str) -> None:
        self.rules = [r for r in self.rules if r.id != rid]

    def reset_hits(self) -> None:
        for rule in self.rules:
            rule.hits = 0

    def set_enabled(self, enabled: bool) -> None:
        for rule in self.rules:
            rule.enabled = enabled

    def replace(self, rules: list[dict]) -> int:
        """用规则列表整体替换当前规则（跳过非法项），返回成功数量。"""
        self.rules = []
        n = 0
        for r in rules:
            try:
                self.add(**r)
                n += 1
            except (ValueError, TypeError):
                continue
        return n

    def list(self) -> list[dict]:
        return [r.to_dict() for r in self.rules]

    @staticmethod
    def _validate(rule: Rule) -> None:
        if rule.data_cond_mode not in ("and", "or"):
            raise ValueError("data_cond_mode 须为 and 或 or")
        if rule.match_id:
            if not _HEX_RE.match(rule.match_id):
                raise ValueError("match_id 必须是 hex 字符串")
            int(rule.match_id, 16)
        if rule.data_contains:
            if not _HEX_RE.match(rule.data_contains) or len(rule.data_contains) % 2:
                raise ValueError("data_contains 必须是偶数长 hex")
        if rule.action == "send":
            if not (rule.send_id and _HEX_RE.match(rule.send_id) and rule.send_data is not None):
                raise ValueError("send 动作需要 send_id 与 send_data")
            send_id = int(rule.send_id, 16)
            max_id = 0x1FFFFFFF if rule.send_extended else 0x7FF
            if not 0 <= send_id <= max_id:
                frame_type = "扩展帧" if rule.send_extended else "标准帧"
                raise ValueError(f"{frame_type}回应 ID 超出范围")
            try:
                data = bytes.fromhex(rule.send_data)
            except ValueError as e:
                raise ValueError("send_data 必须是偶数位 hex") from e
            if len(data) > 8:
                raise ValueError("CAN 数据长度不能超过 8 字节")
        for c in rule.data_cond or []:
            t = c.get("type")
            if t == "byte":
                if not 0 <= int(c.get("index", -1)) <= 7:
                    raise ValueError("字节序号须为 0-7")
                if not 0 <= int(c.get("value", -1)) <= 255:
                    raise ValueError("字节值须为 0-255")
                if c.get("op", "==") not in _CMP_OPS:
                    raise ValueError(f"运算符须为 {_CMP_OPS}")
            elif t == "bytes":
                s, e = int(c.get("start", -1)), int(c.get("end", -1))
                if not 0 <= s <= e <= 7:
                    raise ValueError("字节区间须满足 0 <= 起 <= 止 <= 7")
                if not 0 <= int(c.get("value", -1)) < (1 << (8 * (e - s + 1))):
                    raise ValueError("区间值超出宽度")
                if c.get("op", "==") not in _CMP_OPS:
                    raise ValueError(f"运算符须为 {_CMP_OPS}")
            elif t == "bit":
                if not 0 <= int(c.get("index", c.get("bit", -1))) <= 63:
                    raise ValueError("bit 序号须为 0-63")
                if int(c.get("value", -1)) not in (0, 1):
                    raise ValueError("bit 值须为 0/1")
            elif t == "bits":
                b = int(c.get("byte", -1))
                s, e = int(c.get("start", -1)), int(c.get("end", -1))
                if not 0 <= b <= 7 or not 0 <= s <= e <= 7:
                    raise ValueError("位段：字节 0-7 且 0 <= 位起 <= 位止 <= 7")
                if not 0 <= int(c.get("value", -1)) < (1 << (e - s + 1)):
                    raise ValueError("位段值超出宽度")
            else:
                raise ValueError(f"未知条件类型: {t}（byte/bytes/bit/bits）")

    def _get(self, rid: str) -> Rule:
        for r in self.rules:
            if r.id == rid:
                return r
        raise KeyError(f"规则不存在: {rid}")

    def process(self, msg: can.Message) -> list[dict]:
        """返回触发的动作列表；send 类动作由调用方执行发送。"""
        results = []
        cid = msg.arbitration_id
        data = bytes(msg.data)
        data_hex = data.hex()
        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.match_id and cid != int(rule.match_id, 16):
                continue
            if rule.match_pgn is not None:
                pgn = (cid >> 8) & 0x3FFFF
                if pgn != rule.match_pgn:
                    continue
            if rule.data_contains and rule.data_contains.lower() not in data_hex:
                continue
            combine = any if rule.data_cond_mode == "or" else all
            if rule.data_cond and not combine(_check_cond(c, data) for c in rule.data_cond):
                continue
            rule.hits += 1
            item = {"rule_id": rule.id, "name": rule.name, "action": rule.action}
            if rule.action == "send":
                item["send"] = {
                    "arbitration_id": int(rule.send_id, 16),
                    "data": bytes.fromhex(rule.send_data),
                    "is_extended_id": rule.send_extended,
                }
            results.append(item)
        return results
