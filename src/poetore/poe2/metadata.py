from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path


IDENTITY_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "poetore" / "poe2" / "identity_index.json"
)


@lru_cache(maxsize=1)
def identity_index() -> dict[str, dict]:
    payload = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    index = {}
    for entry in payload.get("entries", ()):
        for name in entry.get("names", {}).values():
            index[str(name).casefold()] = entry
    return index


def resolve_identity(name: str) -> dict | None:
    return identity_index().get(name.strip().casefold())
