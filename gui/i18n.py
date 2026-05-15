from __future__ import annotations

from pathlib import Path

from app_paths import get_locales_dir

DEFAULT_LANGUAGE = "ru"
LOCALES_DIR = get_locales_dir()

_catalogs: dict[str, dict[str, str]] = {}
_current_language = DEFAULT_LANGUAGE


def parse_language_file(path: str | Path) -> dict[str, str]:
    file_path = Path(path)
    catalog: dict[str, str] = {}
    for line_no, raw_line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid locale line {line_no} in {file_path.name}: missing '='")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid locale line {line_no} in {file_path.name}: empty key")
        if key in catalog:
            raise ValueError(f"Duplicate locale key '{key}' in {file_path.name}")
        raw_value = value.strip()
        unescaped = (
            raw_value.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\\r", "\r")
            .replace("\\\\", "\\")
        )
        catalog[key] = unescaped
    return catalog


def load_language(code: str) -> dict[str, str]:
    normalized = str(code or "").strip().lower() or DEFAULT_LANGUAGE
    if normalized not in _catalogs:
        path = LOCALES_DIR / f"{normalized}.txt"
        if not path.exists():
            raise ValueError(f"Unsupported language: {normalized}")
        _catalogs[normalized] = parse_language_file(path)
    return _catalogs[normalized]


def get_available_languages() -> list[str]:
    return sorted(path.stem.lower() for path in LOCALES_DIR.glob("*.txt"))


def set_language(code: str) -> dict[str, str]:
    global _current_language
    normalized = str(code or "").strip().lower() or DEFAULT_LANGUAGE
    catalog = load_language(normalized)
    load_language(DEFAULT_LANGUAGE)
    _current_language = normalized
    return catalog


def get_language() -> str:
    return _current_language


def tr(key: str, default: str | None = None, **fmt: object) -> str:
    current = load_language(_current_language)
    fallback = load_language(DEFAULT_LANGUAGE)
    template = current.get(key) or fallback.get(key) or default or key
    if fmt:
        try:
            return template.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return template
    return template
