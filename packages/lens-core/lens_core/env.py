"""Tiny .env loader (no dependency). Populates os.environ from a .env file for keys that are
not already set, so a single .env configures LLM keys (OPENROUTER_API_KEY, LENS_JUDGE_*) for
the API, the worker and the CLI alike.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | os.PathLike[str] = ".env") -> None:
    # never leak a developer .env into the test process
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
