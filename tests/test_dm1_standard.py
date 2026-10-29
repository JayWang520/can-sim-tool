"""Independent J1939 CM=0 vectors; expectations never call our encoder."""
import asyncio
import time

import pytest

from app.j1939 import DTC, parse_dm1_payload
from app.dm1_sim import Dm1Sim, lamps_from_config


class RecordingBus:
    def __init__(self):
        self.frames = []

    def send(self, cid, data, extended):
        self.frames.append((time.perf_counter(), cid, data, extended))


@pytest.mark.parametrize('spn,fmi,oc,hex_data', [
    (4126, 18, 9, '1E101209'),
    (0x12345, 5, 126, '4523257E'),
    (0x7FFFF, 31, 127, 'FFFFFF7F'),
    (110, 3, 0, '6E000300'),
])
def test_standard_vectors(spn, fmi, oc, hex_data):
    raw = bytes.fromhex(hex_data)
    assert DTC(spn, fmi, oc).encode() == raw
    assert DTC.decode(raw) == DTC(spn, fmi, oc)


def test_no_fault_and_flash():
    sim = Dm1Sim(RecordingBus())
    assert sim.preview()['frames'][0]['data'] == '00FF00000000FFFF'
    assert parse_dm1_payload(bytes.fromhex('00FF00000000FFFF'))['dtcs'] == []
    assert lamps_from_config({'red': 'blink'}) == bytes.fromhex('10CF')
    assert parse_dm1_payload(bytes.fromhex('10CF1E101209FFFF'))['flash']['red'] == 0


@pytest.mark.parametrize('kw', [{'oc': -1}, {'oc': 128}, {'cm': 1}, {'cm': 2}])
def test_invalid_or_unsupported_dtc(kw):
    with pytest.raises(ValueError):
        DTC(110, 3, **kw)


def test_invalid_update_keeps_previous_config():
    sim = Dm1Sim(RecordingBus())
    old = sim.preview()
    with pytest.raises(ValueError):
        sim.update({'dtcs': [{'spn': 4126, 'fmi': 18, 'oc': 128}]})
    assert sim.preview() == old


def test_oc_counts_reactivation_not_broadcasts():
    async def run():
        bus = RecordingBus()
        sim = Dm1Sim(bus)
        fault = {'spn': 4126, 'fmi': 18, 'oc': 9}
        sim.update({'dtcs': [fault], 'oc_auto_inc': True})
        await sim.send_once()
        await sim.send_once()
        assert sim.config['dtcs'][0]['oc'] == 9
        sim.update({'dtcs': []})
        sim.update({'dtcs': [fault]})
        assert sim.config['dtcs'][0]['oc'] == 10
        sim.update({'dtcs': [{'spn': 4126, 'fmi': 18, 'oc': 126}]})
        sim.update({'dtcs': []})
        sim.update({'dtcs': [fault]})
        assert sim.config['dtcs'][0]['oc'] == 126
    asyncio.run(run())


def test_bam_pacing_and_concurrent_groups():
    async def run():
        bus = RecordingBus()
        sim = Dm1Sim(bus)
        sim.update({'dtcs': [{'spn': 4126, 'fmi': 18, 'oc': 9},
                             {'spn': 0x12345, 'fmi': 5, 'oc': 126}]})
        await asyncio.gather(sim.send_once(), sim.send_once())
        expected = ['200A0002FFCAFE00', '0100FF1E10120945', '0223257EFFFFFFFF']
        assert [f[2].hex().upper() for f in bus.frames] == expected * 2
        for start in (0, 3):
            for i in (start + 1, start + 2):
                assert .05 <= bus.frames[i][0] - bus.frames[i-1][0] < .2
        assert all(f[3] for f in bus.frames)
    asyncio.run(run())


def test_payload_limit_and_lamp_positions():
    from app.j1939 import dm1_frames
    for name, expected in [('mil', '403F'), ('red', '10CF'),
                           ('amber', '04F3'), ('protect', '01FC')]:
        assert lamps_from_config({name: 'blink'}).hex().upper() == expected
    assert len(dm1_frames([DTC(110, 3)] * 445)) == 256
    with pytest.raises(ValueError):
        dm1_frames([DTC(110, 3)] * 446)


def test_bam_snapshot_and_stop():
    async def run():
        bus = RecordingBus()
        sim = Dm1Sim(bus)
        faults = [{'spn': 4126, 'fmi': 18, 'oc': 9}, {'spn': 110, 'fmi': 3, 'oc': 0}]
        sim.update({'dtcs': faults})
        sending = asyncio.create_task(sim.send_once())
        await asyncio.sleep(.02)
        sim.update({'dtcs': []})
        result = await sending
        assert result['preview']['frames'][1]['data'] == '0100FF1E1012096E'
        assert bus.frames[2][2].hex().upper() == '02000300FFFFFFFF'
        sim.update({'dtcs': faults})
        sim.start()
        await asyncio.sleep(.02)
        sim.stop()
        count = len(bus.frames)
        await asyncio.sleep(.15)
        assert len(bus.frames) == count
        assert not sim.running
    asyncio.run(run())


def test_standard_fault_frame_and_id_limits():
    async def run():
        bus = RecordingBus()
        sim = Dm1Sim(bus)
        st = sim.update({'extended': False, 'arb_id': 0x123,
                         'dtcs': [{'spn': 4126, 'fmi': 18, 'oc': 9}]})
        assert st['preview']['frames'][0]['id'] == '123'
        assert st['preview']['frames'][0]['extended'] is False
        await sim.send_once()
        assert bus.frames[-1][1:] == (0x123, bytes.fromhex('00FF1E101209FFFF'), False)
        for cid in (0, 0x7FF):
            sim.update({'arb_id': cid})
            await sim.send_once()
            assert bus.frames[-1][1] == cid and bus.frames[-1][3] is False
        before = sim.preview()
        for cfg in ({'arb_id': 0x800}, {'arb_id': -1},
                    {'dtcs': [{'spn': 1, 'fmi': 1}, {'spn': 2, 'fmi': 2}]}):
            with pytest.raises(ValueError):
                sim.update(cfg)
            assert sim.preview() == before
        sim.update({'extended': True, 'arb_id': 0x18FECA00})
        await sim.send_once()
        assert bus.frames[-1][1] == 0x18FECA00 and bus.frames[-1][3] is True
    asyncio.run(run())
