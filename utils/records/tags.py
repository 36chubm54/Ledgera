from __future__ import annotations

import re
from collections.abc import Sequence

MAX_TAGS_PER_RECORD = 3
TAG_COLOR_PALETTE = (
    "#5B8DEF",
    "#34A853",
    "#F2994A",
    "#EB5757",
    "#9B51E0",
    "#00A3A3",
)

_TAG_TOKEN_RE = re.compile(r"[^0-9A-Za-zА-Яа-я]+")


def normalize_tag_name(value: object) -> str:
    text = str(value or "").strip().replace("#", "")
    text = _TAG_TOKEN_RE.sub("", text)
    text = text.lower()
    if not text or text.isdigit():
        return ""
    return text


def normalize_tag_names(values: Sequence[object]) -> tuple[str, ...]:
    normalized_map: dict[str, str] = {}
    for value in values:
        name = normalize_tag_name(value)
        if not name:
            continue
        normalized_map.setdefault(name, name)
        if len(normalized_map) >= MAX_TAGS_PER_RECORD:
            break
    return tuple(normalized_map.values())


def parse_tag_string(raw: str) -> tuple[str, ...]:
    if not str(raw or "").strip():
        return ()
    parts = re.split(r"[,\n;]+", str(raw))
    return normalize_tag_names([part for part in parts])


def find_numeric_only_tags(raw: str | Sequence[object]) -> tuple[str, ...]:
    if isinstance(raw, str):
        values = re.split(r"[,\n;]+", raw)
    else:
        values = list(raw)
    found: dict[str, str] = {}
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        cleaned = _TAG_TOKEN_RE.sub("", text.replace("#", ""))
        if cleaned and cleaned.isdigit():
            found.setdefault(cleaned, cleaned)
    return tuple(found.values())


def format_tags_inline(tags: tuple[str, ...] | list[str]) -> str:
    return " ".join(f"#{tag}" for tag in normalize_tag_names(tuple(tags)))


def display_tag_name(tag: str) -> str:
    normalized = normalize_tag_name(tag)
    return f"#{normalized}" if normalized else ""


def color_for_tag(name: str) -> str:
    normalized = normalize_tag_name(name)
    if not normalized:
        return TAG_COLOR_PALETTE[0]
    checksum = sum(ord(char) for char in normalized)
    return TAG_COLOR_PALETTE[checksum % len(TAG_COLOR_PALETTE)]
