import pytest

from run import DEFAULT_PORT, app_url, is_current_app, parse_start_port


def test_parse_start_port_defaults_and_validates():
    assert parse_start_port([]) == DEFAULT_PORT
    assert parse_start_port(["8765"]) == 8765
    with pytest.raises(ValueError, match="必须是数字"):
        parse_start_port(["abc"])
    with pytest.raises(ValueError, match="1～65535"):
        parse_start_port(["70000"])


def test_app_url_forces_browser_to_open_current_frontend():
    assert app_url(8000, "abc123") == "http://127.0.0.1:8000/?v=abc123"


def test_only_reuses_instance_with_matching_frontend(monkeypatch):
    class Response:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, *_args):
            return self.payload

    monkeypatch.setattr(
        "run.urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(b'{"frontend_version":"new"}'),
    )
    assert is_current_app(8000, "new") is True
    assert is_current_app(8000, "old") is False
