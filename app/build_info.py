"""Build identity shared by the launcher and status API."""
from __future__ import annotations

import hashlib
from pathlib import Path


def frontend_version(resource_dir: Path) -> str:
    """Return a stable identifier for the frontend bundled with this process."""
    return hashlib.sha256((resource_dir / "web" / "app.js").read_bytes()).hexdigest()[:16]
