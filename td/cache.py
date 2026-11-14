# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""JSON cache for NASA API answers, in data/cache/<key>.json (gitignored). Owner: A (data).

Every API answer is saved, so each request is made once and the demo never depends on a live API.
Set TD_CACHE_DIR to use another folder (the tests do).

Contract:
    make_key(*parts) -> str          # sha1 of the request parts
    get(key) -> dict | None
    put(key, data) -> None
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def cache_dir() -> Path:
    d = Path(os.environ.get("TD_CACHE_DIR") or DEFAULT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_key(*parts) -> str:
    """sha1 of the request parts, e.g. make_key("power", lat, lon, 1981, 2025)."""
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def get(key: str) -> dict | None:
    """The cached answer, or None when it is missing or unreadable."""
    path = cache_dir() / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def put(key: str, data: dict) -> None:
    """Write atomically, so a crash never leaves a half-written file."""
    path = cache_dir() / f"{key}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)
