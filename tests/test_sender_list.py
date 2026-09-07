"""List generation through the public service and actual virtual CAN output."""
import asyncio
import uuid

import can
import pytest

from app.bus import BusService
from app.senders import Senders


def test_list_sequence_stop_restart_and_copy():
    async def run():
        bus = BusService()
        channel = uuid.uuid4().hex
        bus.connect("virtual", channel)
        peer = can.Bus(interface="virtual", channel=channel)
        senders = Senders(bus)
        output = []
        bus.listeners.append(lambda msg, direction: output.append(bytes(msg.data))
                             if direction == "tx" else None)
        try:
            task = senders.create("list", 0x123, "", 5, False, False,
                                  mode="list", data_list=["12 34", "AB", ""])
            sid = task["id"]
            copy = senders.duplicate(sid)
            assert copy["data_list"] == ["1234", "AB", ""]
            assert not copy["running"]
            senders.start(sid)
            async with asyncio.timeout(2):
                while len(output) < 7:
                    await asyncio.sleep(.005)
            senders.stop(sid)
            assert output[:7] == [b"\x12\x34", b"\xAB", b"", b"\x12\x34", b"\xAB", b"", b"\x12\x34"]
            received = [peer.recv(timeout=.5) for _ in range(7)]
            assert all(msg is not None and msg.arbitration_id == 0x123
                       and not msg.is_extended_id for msg in received)
            assert [bytes(msg.data) for msg in received] == output[:7]
            count = len(output)
            await asyncio.sleep(.03)
            assert len(output) == count
            output.clear()
            senders.start(sid)
            async with asyncio.timeout(2):
                while not output:
                    await asyncio.sleep(.005)
            senders.stop(sid)
            assert output[0] == b"\x12\x34"
        finally:
            senders.stop_all()
            bus.disconnect()
            peer.shutdown()
    asyncio.run(run())


@pytest.mark.parametrize("invalid", [[], None, "1234", [12], ["G0"], ["1"], ["00" * 9]])
def test_invalid_list_does_not_replace_valid_task(invalid):
    senders = Senders(BusService())
    task = senders.create("list", 0x123, "", 10, auto_start=False,
                          mode="list", data_list=["12", "34"])
    with pytest.raises(ValueError):
        senders.update(task["id"], data_list=invalid)
    assert senders.list()[0] == task


def test_list_api_copy_and_preset_round_trip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main

    # Isolate preset destinations and task state from the user's configuration.
    monkeypatch.setattr(main, "senders", Senders(BusService()))
    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "PRESET_DIR", tmp_path)
        response = client.post("/api/senders", json={
            "name": "sequence", "id": "123", "extended": False,
            "period_ms": 10, "auto_start": False, "mode": "list",
            "data_list": ["12 34", "ab", ""],
        })
        assert response.status_code == 200
        task = response.json()
        sid = task["id"]
        assert task["data_list"] == ["1234", "AB", ""]
        assert task["is_extended_id"] is False
        invalid = client.put(f"/api/senders/{sid}", json={"data_list": []})
        assert invalid.status_code == 400
        assert client.get("/api/senders").json() == [task]
        copy = client.post(f"/api/senders/{sid}/duplicate").json()
        assert copy["data_list"] == task["data_list"]
        assert not copy["running"]
        saved = client.post("/api/presets", json={"name": "sequence"}).json()
        restored = client.post(f"/api/presets/{saved['file']}/load")
        assert restored.status_code == 200
        tasks = client.get("/api/senders").json()
        assert len(tasks) == 2
        assert all(t["mode"] == "list" and t["data_list"] == ["1234", "AB", ""]
                   and not t["running"] for t in tasks)
