import can
import pytest
from fastapi.testclient import TestClient
from app import main
from app.triggers import TriggerService


CONDS = [dict(type='byte', index=0, value=0x12), dict(type='byte', index=1, value=0x34)]


@pytest.mark.parametrize('mode,data,expected', [
    ('and', '1234', True), ('and', '1200', False), ('and', '0034', False),
    ('or', '1234', True), ('or', '1200', True), ('or', '0034', True),
    ('or', '0000', False), ('or', '', False), ('or', '12', True), ('and', '12', False),
])
def test_condition_combination(mode, data, expected):
    service = TriggerService()
    service.add(name='test', match_id='123', data_cond=CONDS, data_cond_mode=mode)
    assert bool(service.process(can.Message(arbitration_id=0x123, data=bytes.fromhex(data)))) is expected
    assert not service.process(can.Message(arbitration_id=0x124, data=bytes.fromhex(data)))


def test_default_empty_and_invalid():
    service = TriggerService()
    rule = service.add(name='old', data_cond=CONDS)
    assert rule['data_cond_mode'] == 'and'
    with pytest.raises(ValueError):
        service.update(rule['id'], data_cond_mode='xor')
    assert service.list()[0]['data_cond_mode'] == 'and'
    service.update(rule['id'], data_cond=[], data_cond_mode='or')
    assert service.process(can.Message(arbitration_id=0x123, data=b''))


def test_update_and_file_roundtrip(tmp_path, monkeypatch):
    service = TriggerService()
    monkeypatch.setattr(main, 'triggers', service)
    with TestClient(main.app) as client:
        rule = client.post('/api/triggers', json=dict(name='rule', data_cond=CONDS)).json()
        rid = rule['id']
        updated = client.put(f'/api/triggers/{rid}', json=dict(data_cond_mode='or', data_cond=[dict(CONDS[0], value=0x56), CONDS[1]]))
        assert updated.status_code == 200
        assert updated.json()['id'] == rid
        assert len(service.list()) == 1
        path = str(tmp_path / 'rules.json')
        assert client.post('/api/triggers/save_to', json={'path':path}).status_code == 200
        service.rules = []
        assert client.post('/api/triggers/load_from', json={'path':path}).status_code == 200
        assert service.list()[0]['data_cond_mode'] == 'or'
        assert service.list()[0]['data_cond'][0]['value'] == 0x56
        assert service.process(can.Message(arbitration_id=0x123, data=b'\x56\x00'))
