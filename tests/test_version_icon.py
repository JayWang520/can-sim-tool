from pathlib import Path
import struct

from fastapi.testclient import TestClient
from app.main import app
from app.build_info import APP_VERSION, VERSION_TUPLE, frontend_version

ROOT = Path(__file__).parents[1]


def test_version_api_and_metadata():
    with TestClient(app) as client:
        assert client.get('/api/version').json()['version'] == APP_VERSION
        assert client.get('/api/status').json()['version'] == APP_VERSION
        assert client.get('/openapi.json').json()['info']['version'] == APP_VERSION
        html = client.get('/').text
        assert 'id="app-version"' in html
        assert 'href="icon.svg"' in html
        assert client.get('/icon.svg').status_code == 200
        assert client.get('/icon.ico').status_code == 200
    assert VERSION_TUPLE == tuple(map(int, APP_VERSION.split('.'))) + (0,)


def test_icon_resolutions():
    content = (ROOT / 'web/icon.ico').read_bytes()
    assert struct.unpack_from('<HHH', content) == (0, 1, 8)
    sizes = []
    for i in range(8):
        width, height, _, _, planes, depth, length, offset = struct.unpack_from('<BBBBHHII', content, 6 + i * 16)
        width, height = width or 256, height or 256
        assert width == height and planes == 1 and depth == 32
        png = content[offset:offset + length]
        assert png[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack_from('>II', png, 16) == (width, height)
        sizes.append(width)
    assert sizes == [16, 20, 24, 32, 48, 64, 128, 256]


def test_asset_changes_invalidate_build_identity(tmp_path):
    folder = tmp_path / 'web'; folder.mkdir()
    names = ('app.js', 'index.html', 'style.css', 'i18n.js', 'analysis.js', 'icon.svg')
    for name in names:
        (folder / name).write_text('initial', encoding='utf-8')
    before = frontend_version(tmp_path)
    (folder / 'icon.svg').write_text('updated', encoding='utf-8')
    assert frontend_version(tmp_path) != before
