"""Verify generated payloads via an independent virtual CAN receiver."""
import asyncio
import uuid

import can
import pytest

from app.bus import BusService
from app.senders import Senders


async def capture(data, count=8, **options):
    channel = uuid.uuid4().hex
    bus = BusService()
    bus.connect("virtual", channel)
    peer = can.Bus(interface="virtual", channel=channel)
    senders = Senders(bus)
    try:
        task = senders.create("generator", 0x123, data, 5, False, **options)
        messages = []
        for _ in range(count):
            msg = await asyncio.to_thread(peer.recv, 1)
            assert msg is not None
            assert msg.arbitration_id == 0x123 and not msg.is_extended_id
            messages.append(bytes(msg.data))
        stopped = senders.stop(task["id"])
        await asyncio.sleep(.03)
        assert senders.list()[0]["sent"] == stopped["sent"]
        return messages
    finally:
        senders.stop_all()
        bus.disconnect()
        peer.shutdown()


def test_seeded_random_repeats_and_preserves_unmasked_bits():
    async def run():
        first = await capture("AABBCCDD", mode="random", random_seed=42, random_mask="0F00FF80")
        second = await capture("AABBCCDD", mode="random", random_seed=42, random_mask="0F00FF80")
        other = await capture("AABBCCDD", mode="random", random_seed=43, random_mask="0F00FF80")
        assert first == second
        assert first != other
        assert len(set(first)) > 1
        assert all(len(data) == 4 and data[0] & 0xF0 == 0xA0
                   and data[1] == 0xBB and data[3] & 0x7F == 0x5D for data in first)
        fixed = await capture("1234", mode="random", random_mask="0000")
        assert fixed == [bytes.fromhex("1234")] * 8
        unmasked = await capture("00" * 8, mode="random")
        assert len(set(unmasked)) > 1 and all(len(data) == 8 for data in unmasked)
    asyncio.run(run())


@pytest.mark.parametrize("step,values", [(2, [254, 256, 258, 254, 256, 258, 254, 256]),
                                        (-2, [259, 257, 255, 259, 257, 255, 259, 257])])
def test_ramp_bounds_wrap_little_endian_and_unchanged_outer_bytes(step, values):
    output = asyncio.run(capture("AA0000BB", mode="ramp", inc_byte=1, inc_end=2,
                                 inc_step=step, ramp_min=254, ramp_max=259))
    assert [int.from_bytes(data[1:3], "little") for data in output] == values
    assert all(data[0] == 0xAA and data[3] == 0xBB for data in output)


@pytest.mark.parametrize("options", [
    {"mode": "random", "random_mask": "FF"},
    {"mode": "random", "random_mask": None},
    {"mode": "random", "random_mask": "GG"},
    {"mode": "random", "random_seed": 1.5},
    {"mode": "ramp", "ramp_min": 20, "ramp_max": 10},
    {"mode": "ramp", "ramp_max": 256},
    {"mode": "ramp", "ramp_min": -1},
    {"mode": "ramp", "inc_step": 0},
])
def test_invalid_generator_update_keeps_previous_config(options):
    senders = Senders(BusService())
    before = senders.create("fixed", 0x123, "1234", 10, auto_start=False)
    with pytest.raises(ValueError):
        senders.update(before["id"], **options)
    assert senders.list() == [before]


@pytest.mark.parametrize("options", [
    {"mode": "random", "random_seed": 123, "random_mask": "0FFF"},
    {"mode": "ramp", "inc_byte": 0, "inc_end": 1, "inc_step": -3,
     "ramp_min": 250, "ramp_max": 260},
])
def test_generator_api_copy_and_preset(options, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main

    monkeypatch.setattr(main, "senders", Senders(BusService()))
    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "PRESET_DIR", tmp_path)
        response = client.post("/api/senders", json={
            "name": "generator", "id": "123", "data": "1234",
            "auto_start": False, **options,
        })
        assert response.status_code == 200
        sid = response.json()["id"]
        duplicate = client.post(f"/api/senders/{sid}/duplicate")
        assert duplicate.status_code == 200
        file = client.post("/api/presets", json={"name": "generator"}).json()["file"]
        assert client.post(f"/api/presets/{file}/load").status_code == 200
        tasks = client.get("/api/senders").json()
        assert len(tasks) == 2
        for task in tasks:
            assert not task["running"]
            for key, value in options.items():
                assert task[key] == value
