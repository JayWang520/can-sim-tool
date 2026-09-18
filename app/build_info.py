"""Build identity shared by the launcher and status API."""
from __future__ import annotations

import hashlib
from pathlib import Path

APP_VERSION = "1.1.1"
VERSION_TUPLE = tuple(int(part) for part in APP_VERSION.split(".")) + (0,)


def frontend_version(resource_dir: Path) -> str:
    """Return a stable identifier for the frontend bundled with this process."""
    digest = hashlib.sha256(APP_VERSION.encode("ascii"))
    for name in ("app.js", "index.html", "style.css", "i18n.js", "analysis.js", "icon.svg"):
        digest.update(name.encode("ascii"))
        digest.update((resource_dir / "web" / name).read_bytes())
    return digest.hexdigest()[:16]
