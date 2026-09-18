import can
from fastapi.testclient import TestClient

from app import main
from app.triggers import TriggerService


def test_edit_existing_rule_changes_response_and_clears_filters(monkeypatch):
    service = TriggerService()
    monkeypatch.setattr(main, "triggers", service)
    with TestClient(main.app) as client:
        rule = client.post('/api/triggers', json={
            'name': 'old', 'match_id': '123', 'match_pgn': 1,
            'data_contains': 'AA', 'data_cond': [{'type': 'byte', 'index': 0, 'value': 170}],
            'action': 'send', 'send_id': '456', 'send_data': '1122',
            'send_extended': True,
        }).json()
        rid = rule['id']
        service.process(can.Message(arbitration_id=0x123, data=b'\xAA', is_extended_id=False))
        response = client.put(f'/api/triggers/{rid}', json={
            'name': 'edited', 'match_id': '124', 'match_pgn': None,
            'data_contains': None, 'data_cond': [],
            'action': 'send', 'send_id': '457', 'send_data': '1234', 'send_extended': 'false',
        })
        assert response.status_code == 200
        updated = response.json()
        assert updated['id'] == rid and updated['hits'] == 1
        assert len(client.get('/api/triggers').json()) == 1
        assert service.process(can.Message(arbitration_id=0x123, data=b'\xAA', is_extended_id=False)) == []
        result = service.process(can.Message(arbitration_id=0x124, data=b'', is_extended_id=False))
        assert result[0]['send']['arbitration_id'] == 0x457
        assert result[0]['send']['data'] == bytes.fromhex('1234')
        assert result[0]['send']['is_extended_id'] is False
        before = client.get('/api/triggers').json()
        invalid = client.put(f'/api/triggers/{rid}', json={'name': 'bad', 'send_data': 'GG'})
        assert invalid.status_code == 400
        assert client.get('/api/triggers').json() == before


def test_edit_disabled_rule_preserves_disabled_state():
    service = TriggerService()
    rule = service.add(name='disabled', enabled=False, action='count', match_id='123')
    updated = service.update(rule['id'], name='edited', match_id=None)
    assert updated['enabled'] is False
    assert service.process(can.Message(arbitration_id=0x123, data=b'')) == []
