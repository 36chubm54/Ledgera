from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def compute_checksum(data: dict[str, Any], *, invalid_payload_error: type[Exception]) -> str:
    if not isinstance(data, dict):
        raise invalid_payload_error("Checksum payload must be object")
    serialized = json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def now_utc_iso8601() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cleanup_temp_backup_file(temp_path: str) -> None:
    try:
        os.unlink(temp_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning("Backup temp file cleanup failed: %s", temp_path, exc_info=exc)


def unwrap_backup_payload(
    payload: Any,
    *,
    force: bool,
    invalid_payload_error: type[Exception],
    integrity_error: type[Exception],
    readonly_error: type[Exception],
) -> dict[str, Any]:
    if isinstance(payload, list):
        return {"records": payload}
    if not isinstance(payload, dict):
        raise invalid_payload_error("Invalid backup JSON structure: root must be object")

    has_meta = "meta" in payload
    has_data = "data" in payload
    if not has_meta and not has_data:
        return payload
    if has_meta != has_data:
        raise invalid_payload_error("Snapshot backup must include both 'meta' and 'data'")

    meta = payload.get("meta")
    data = payload.get("data")
    if not isinstance(meta, dict):
        raise invalid_payload_error("Snapshot backup: 'meta' must be object")
    if not isinstance(data, dict):
        raise invalid_payload_error("Snapshot backup: 'data' must be object")

    checksum = meta.get("checksum")
    if not isinstance(checksum, str) or not checksum.strip():
        raise invalid_payload_error("Snapshot backup: missing meta.checksum")
    actual_checksum = compute_checksum(data, invalid_payload_error=invalid_payload_error)
    if checksum != actual_checksum:
        raise integrity_error("Snapshot checksum mismatch")

    readonly = bool(meta.get("readonly", False))
    if readonly and not force:
        raise readonly_error("Readonly snapshot cannot be imported without force=True")

    return data


def write_json_atomically(filepath: str, payload: dict[str, Any] | list[Any]) -> None:
    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix="backup-",
        suffix=".json",
        dir=directory or None,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp_path, filepath)
    except (OSError, TypeError, ValueError):
        _cleanup_temp_backup_file(temp_path)
        raise
