from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tag:
    id: int
    name: str
    color: str = ""
    usage_count: int = 0
    last_used_at: str = ""
