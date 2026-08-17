"""Start the existing render worker against the local evaluation stack."""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("VIEWER_URL", "http://localhost:3000")
os.environ.setdefault("RENDER_SESSION_ID", "worker")
os.environ.setdefault("RENDER_BRIDGE_URL", "http://127.0.0.1:8765")
os.environ.setdefault("AGENT_API_URL", "http://127.0.0.1:8000")

from backend.render_worker.main import main  # noqa: E402


if __name__ == "__main__":
    main()
