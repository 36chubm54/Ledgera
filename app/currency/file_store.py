from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol


class OsLike(Protocol):
    def unlink(self, path: str) -> None: ...

    def replace(self, src: str, dst: str | Path) -> None: ...


def cleanup_temp_file(
    temp_path: str | None,
    *,
    context: str,
    logger: logging.Logger,
    os_module: OsLike = os,
) -> None:
    if not temp_path:
        return
    try:
        os_module.unlink(temp_path)
    except FileNotFoundError:
        return
    except OSError:
        logger.exception("Failed to cleanup temporary %s: %s", context, temp_path)


def load_json_object_file(path: Path, *, context: str) -> dict[str, object]:
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise OSError(f"Failed to load {context}") from exc
    if not isinstance(payload, dict):
        raise OSError(f"Failed to load {context}")
    return dict(payload)


def write_config_file(
    payload: Mapping[str, object],
    target: Path,
    *,
    default_config: Mapping[str, object],
    normalize_secret: Callable[[object], str],
    api_key_source_field: str,
    api_key_persisted_field: str,
    persist_plaintext_api_key: bool,
    logger: logging.Logger,
    os_module: OsLike = os,
) -> None:
    normalized = dict(default_config)
    normalized.update(dict(payload))
    if persist_plaintext_api_key:
        normalized["exchange_rate_api_key"] = normalize_secret(
            normalized.get("exchange_rate_api_key", "")
        )
    else:
        normalized["exchange_rate_api_key"] = ""
    normalized.pop("_exchange_rate_api_key_source", None)
    normalized.pop("_exchange_rate_api_key_secure", None)
    normalized.pop("_exchange_rate_api_key_label", None)
    normalized.pop(api_key_source_field, None)
    normalized.pop(api_key_persisted_field, None)
    temp_path: str | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=".currency_config_",
            suffix=".json",
            dir=str(target.parent),
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(normalized, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os_module.replace(temp_path, target)
    except OSError:
        cleanup_temp_file(temp_path, context="currency config", logger=logger, os_module=os_module)
        raise


def load_cache_file(cache_file: Path) -> dict[str, float] | None:
    if not cache_file.exists():
        return None
    data = load_json_object_file(cache_file, context="cached currency rates")
    return {str(k): float(str(v)) for k, v in data.items()}


def save_cache_file(
    cache_file: Path,
    rates: dict[str, float],
    *,
    logger: logging.Logger,
    os_module: OsLike = os,
) -> None:
    temp_path: str | None = None
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=".currency_rates_",
            suffix=".json",
            dir=str(cache_file.parent),
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rates, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os_module.replace(temp_path, cache_file)
    except (OSError, TypeError, ValueError):
        cleanup_temp_file(temp_path, context="currency cache", logger=logger, os_module=os_module)
        logger.exception("Failed to save currency cache")
