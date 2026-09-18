import tkinter
from tkinter import filedialog

from fastapi.testclient import TestClient
from app.main import app


def test_native_picker_modes_and_cancel(monkeypatch):
    calls = []
    class Root:
        def withdraw(self): pass
        def attributes(self, *args): pass
        def destroy(self): calls.append('destroy')
    monkeypatch.setattr(tkinter, 'Tk', Root)
    def directory(**kwargs):
        assert kwargs['mustexist'] is True
        return 'D:/chosen'
    def save(**kwargs):
        assert kwargs['confirmoverwrite'] is True
        assert kwargs['defaultextension'] == '.json'
        return ''
    monkeypatch.setattr(filedialog, 'askdirectory', directory)
    monkeypatch.setattr(filedialog, 'asksaveasfilename', save)
    with TestClient(app) as client:
        assert client.get('/api/filepicker?mode=directory').json()['path'] == 'D:/chosen'
        assert client.get('/api/filepicker?mode=save').json()['path'] is None
        assert client.get('/api/filepicker?mode=bad').status_code == 400
    assert len(calls) == 2
