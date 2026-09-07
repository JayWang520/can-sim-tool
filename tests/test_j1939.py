"""J1939 编解码单元测试。"""
import pytest

from app import j1939
from app.j1939 import DTC, decode_id, dm1_frames, encode_id, encode_lamps


def test_id_roundtrip_pdu2():
    cid = encode_id(6, j1939.PGN_DM1, 0x00)
    assert cid == 0x18FECA00
    info = decode_id(cid)
    assert info["priority"] == 6
    assert info["pgn"] == 65226
    assert info["sa"] == 0
    assert info["da"] is None
    assert not info["is_pdu1"]


def test_id_pdu1_with_destination():
    cid = encode_id(7, j1939.PGN_TP_CM, 0xF9, da=0xFF)
    info = decode_id(cid)
    assert info["is_pdu1"]
    assert info["da"] == 0xFF
    assert info["pgn"] == j1939.PGN_TP_CM  # 0xEC00 = 60416


def test_id_priority_bounds():
    with pytest.raises(ValueError):
        encode_id(8, 65226, 0)


def test_dtc_roundtrip():
    for spn, fmi, oc, cm in [(110, 0, 1, 0), (524287, 31, 127, 1), (1, 1, 1, 0), (4126, 18, 9, 0)]:
        d = DTC(spn=spn, fmi=fmi, oc=oc, cm=cm)
        assert len(d.encode()) == 4
        assert DTC.decode(d.encode()) == d


def test_dtc_invalid_spn():
    with pytest.raises(ValueError):
        DTC(spn=524288, fmi=0, oc=1)
    with pytest.raises(ValueError):
        DTC(spn=110, fmi=32, oc=1)


def test_lamps_encode():
    lamps = encode_lamps(mil=1, red=2, amber=1, protect=3)
    assert lamps == bytes([0x67, 0xFF])  # 01 10 01 11


def test_dm1_single_packet():
    frames = dm1_frames([DTC(spn=110, fmi=0, oc=1)], encode_lamps(red=1, protect=1))
    assert len(frames) == 1
    f = frames[0]
    assert f.arbitration_id == 0x18FECA00
    assert f.is_extended_id
    assert len(f.data) == 8  # 默认补齐 8 字节
    assert (f.data[0] >> 4) & 3 == 1  # red
    assert f.data[0] & 3 == 1  # protect
    assert DTC.decode(bytes(f.data[2:6])) == DTC(spn=110, fmi=0, oc=1)


def test_dm1_bam_multi_packet():
    dtcs = [DTC(spn=110, fmi=0, oc=1), DTC(spn=100, fmi=1, oc=2), DTC(spn=175, fmi=0, oc=1)]
    frames = dm1_frames(dtcs, encode_lamps(amber=1))
    payload = encode_lamps(amber=1) + b"".join(d.encode() for d in dtcs)
    assert len(payload) == 14
    assert len(frames) == 3  # CM_BAM + 2 个数据包

    cm = frames[0]
    assert cm.arbitration_id == encode_id(6, j1939.PGN_TP_CM, 0x00, da=0xFF)
    assert cm.data[0] == 0x20  # BAM
    assert cm.data[1] == 14  # 总字节数
    assert cm.data[3] == 2  # 包数
    assert cm.data[5:8] == bytes([0xCA, 0xFE, 0x00])  # PGN 65226 小端

    d1, d2 = frames[1], frames[2]
    # 标准 TP：CM=PGN EC00(18ECFFxx)、DT=PGN ED00(18EDFFxx)，以数据首字节区分
    assert frames[0].arbitration_id == encode_id(6, j1939.PGN_TP_CM, 0x00, da=0xFF)
    assert d1.arbitration_id == encode_id(6, j1939.PGN_TP_DT, 0x00, da=0xFF)
    assert d1.data[0] == 1 and d2.data[0] == 2
    assert bytes(d1.data[1:8]) == payload[0:7]
    assert bytes(d2.data[1:8]) == payload[7:14]  # 14 字节载荷恰好 2 包，无补齐


def test_dm1_bam_custom_transport_nodes():
    """多包的两个传输帧完整 ID 可分别自定义。"""
    dtcs = [DTC(spn=110, fmi=0, oc=1), DTC(spn=100, fmi=1, oc=1), DTC(spn=175, fmi=0, oc=1)]
    frames = dm1_frames(dtcs, cm_id=0x18EBFF00, dt_id=0x18ECFF00)
    assert frames[0].arbitration_id == 0x18EBFF00  # CM 通告帧
    assert frames[1].arbitration_id == 0x18ECFF00  # DT 数据帧
    assert frames[2].arbitration_id == 0x18ECFF00
    assert frames[1].data[0] == 1  # 内容不受自定义 ID 影响
    # 只自定义 CM，DT 仍跟随节点
    frames = dm1_frames(dtcs, cm_id=0x18EBFF00)
    assert frames[0].arbitration_id == 0x18EBFF00
    assert frames[1].arbitration_id == encode_id(6, j1939.PGN_TP_DT, 0x00, da=0xFF)


def test_dm1_frames_custom_pgn_and_da():
    # 私有 PDU1 格式 PGN（PF=0xEF）+ 指定目标地址 → 单帧 ID 携带 DA
    frames = dm1_frames(
        [DTC(spn=110, fmi=0, oc=1)], encode_lamps(red=1),
        sa=0x00, priority=6, pgn=0xEF00, da=0x17,
    )
    cid = frames[0].arbitration_id
    assert cid == encode_id(6, 0xEF00, 0x00, da=0x17)
    info = decode_id(cid)
    assert info["da"] == 0x17
    assert info["pgn"] == 0xEF00
    assert info["is_pdu1"]

    # PDU2 格式 PGN：DA 被忽略（无目标地址）
    frames = dm1_frames([DTC(spn=110, fmi=0, oc=1)], pgn=65226, da=0x17)
    assert decode_id(frames[0].arbitration_id)["da"] is None


def test_parse_dm1_payload():
    raw = encode_lamps(red=1) + DTC(spn=110, fmi=0, oc=1).encode() + b"\xff\xff"
    r = j1939.parse_dm1_payload(raw)
    assert r["lamps"]["red"] == 1
    assert r["dtcs"] == [{"spn": 110, "fmi": 0, "oc": 1, "cm": 0}]


def test_bam_reassembler_reassembles_dm1_and_rejects_wrong_sequence():
    frames = dm1_frames(
        [DTC(spn=110, fmi=0), DTC(spn=100, fmi=1), DTC(spn=175, fmi=0)],
        encode_lamps(red=1),
    )
    reassembler = j1939.BamReassembler()
    assert reassembler.feed(frames[0].arbitration_id, bytes(frames[0].data)) is None
    assert reassembler.feed(frames[2].arbitration_id, bytes(frames[2].data)) is None
    assert reassembler.feed(frames[0].arbitration_id, bytes(frames[0].data)) is None
    assert reassembler.feed(frames[1].arbitration_id, bytes(frames[1].data)) is None
    result = reassembler.feed(frames[2].arbitration_id, bytes(frames[2].data))
    assert result is not None
    assert result["pgn"] == j1939.PGN_DM1
    assert len(result["data"]) == 14
    assert j1939.parse_dm1_payload(result["data"])["dtcs"][2]["spn"] == 175
