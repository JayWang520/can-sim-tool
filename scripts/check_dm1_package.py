"""Launch an isolated EXE, verify actual virtual-bus frames, then stop only that process.

Usage: python scripts/check_dm1_package.py path/to/CanSimTool.exe [--check-run-bat]
No physical CAN connection; no saved settings are changed.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen

from websockets.sync.client import connect


def main():
    exe = Path(sys.argv[1]).resolve()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'

    def api(path, method='GET', body=None):
        raw = None if body is None else json.dumps(body).encode()
        req = Request(base + path, data=raw, method=method,
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=5) as response:
            return json.load(response)

    env = dict(os.environ, CAN_TOOL_NO_BROWSER='1')
    proc = subprocess.Popen([str(exe), str(port)], cwd=exe.parent, env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if proc.poll() is not None:
                raise RuntimeError(f'EXE exited: {proc.returncode}')
            try:
                version = api('/api/version')
                break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError('EXE did not start')
        assert version['version'] == '1.1.3', version
        print('PASS actual EXE starts, version 1.1.3', flush=True)
        if '--check-run-bat' in sys.argv:
            root = Path(__file__).resolve().parents[1]
            subprocess.run([os.environ['COMSPEC'], '/c', str(root / 'run.bat'), str(port)],
                           cwd=root, env=env, check=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            print('PASS run.bat resolves to current packaged build', flush=True)
        api('/api/connect', 'POST', {'interface': 'virtual', 'channel': 'j1939-package-audit'})
        faults = [{'spn': 4126, 'fmi': 18, 'oc': 9}, {'spn': 74565, 'fmi': 5, 'oc': 126}]
        for dtcs, expected in [
            ([], ['00FF00000000FFFF']),
            (faults[:1], ['00FF1E101209FFFF']),
            (faults, ['200A0002FFCAFE00', '0100FF1E10120945', '0223257EFFFFFFFF']),
        ]:
            api('/api/dm1', 'PUT', {'dtcs': dtcs, 'lamps': {}, 'oc_auto_inc': False})
            with connect(f'ws://127.0.0.1:{port}/ws', proxy=None) as ws:
                sent = api('/api/dm1/send_once', 'POST')
                assert sent['sent'] == len(expected)
                received = []
                while len(received) < len(expected):
                    frame = json.loads(ws.recv(timeout=3))
                    if frame.get('dir') == 'rx':
                        received.append(frame)
                assert [f['data'] for f in received] == expected, received
                assert all(f['ext'] for f in received)
                assert received[-1]['dm1']['dtcs'] == [dict(d, cm=0) for d in dtcs]
                if len(received) > 1:
                    gaps = [round((b['ts']-a['ts'])*1000, 1) for a,b in zip(received, received[1:])]
                    print('BAM receive intervals (ms):', gaps, flush=True)
            print(f'PASS EXE virtual CAN: {len(dtcs)} DTC(s), {expected}', flush=True)
        api('/api/dm1', 'PUT', {'extended': False, 'arb_id': 0x123, 'dtcs': faults[:1]})
        with connect(f'ws://127.0.0.1:{port}/ws', proxy=None) as ws:
            api('/api/dm1/send_once', 'POST')
            for _ in range(6):
                frame = json.loads(ws.recv(timeout=3))
                if frame.get('dir') == 'rx':
                    break
            assert frame['id'] == '123' and frame['ext'] is False, frame
            assert frame['data'] == '00FF1E101209FFFF', frame
            assert frame['pgn'] is None and 'dm1' not in frame
        print('PASS EXE standard CAN frame: ID=123, ext=false, data=00FF1E101209FFFF', flush=True)
        api('/api/disconnect', 'POST')
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == '__main__':
    main()
