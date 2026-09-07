"""DBC 加载与报文编解码（cantools）。"""
from __future__ import annotations

from typing import Optional

import can
import cantools


class DbcService:
    def __init__(self) -> None:
        self.db: Optional[cantools.database.Database] = None
        self.file_name: Optional[str] = None

    @property
    def loaded(self) -> bool:
        return self.db is not None

    def load(self, path: str) -> dict:
        self.db = cantools.database.load_file(path)
        self.file_name = path
        return {"file": path.split("/")[-1].split("\\")[-1], "messages": self.messages()}

    def messages(self) -> list[dict]:
        if not self.loaded:
            return []
        out = []
        for m in self.db.messages:
            out.append(
                {
                    "name": m.name,
                    "frame_id": m.frame_id,
                    "id_hex": f"{m.frame_id:08X}",
                    "length": m.length,
                    "signals": [
                        {"name": s.name, "unit": s.unit or "", "comment": str(s.comment or "")}
                        for s in m.signals
                    ],
                }
            )
        return out

    def _find(self, cid: int):
        """J1939 DBC 的 ID 含 SA：先精确匹配，再用 PGN（去 SA）兜底。"""
        try:
            return self.db.get_message_by_frame_id(cid)
        except KeyError:
            pass
        for m in self.db.messages:
            if (m.frame_id >> 8) == (cid >> 8):
                return m
        return None

    def decode(self, msg: can.Message) -> Optional[dict]:
        if not self.loaded or not msg.data:
            return None
        m = self._find(msg.arbitration_id)
        if m is None or len(msg.data) < m.length:
            return None
        try:
            vals = m.decode(bytes(msg.data), decode_choices=False)
        except Exception:
            return None
        signals = {}
        for k, v in vals.items():
            if isinstance(v, float):
                v = round(v, 3)
            signals[k] = v
        return {"message": m.name, "signals": signals}

    def encode(self, message_name: str, signals: dict) -> bytes:
        if not self.loaded:
            raise RuntimeError("未加载 DBC")
        m = self.db.get_message_by_name(message_name)
        return m.encode(signals)
