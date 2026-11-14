# SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team
"""JSON cache for NASA API answers, in data/cache/<key>.json (gitignored). Owner: A (data).

Contract:
    make_key(*parts) -> str          # sha1 of the request parts
    get(key) -> dict | None
    put(key, data) -> None
"""
from __future__ import annotations


def make_key(*parts) -> str:
    raise NotImplementedError("Step 1 (A)")


def get(key: str) -> dict | None:
    raise NotImplementedError("Step 1 (A)")


def put(key: str, data: dict) -> None:
    raise NotImplementedError("Step 1 (A)")
