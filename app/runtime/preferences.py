from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.data.protocols import SchemaMetaRepository
from app.data.repository import RecordRepository
from app.services import CurrencyService
from domain.update import PendingUpdateCleanupState, PendingUpdateInstallState


@dataclass(frozen=True)
class OnlineStatusSnapshot:
    is_online: bool
    last_fetched_at: datetime | None


class UIPreferencesService:
    _PENDING_UPDATE_INSTALL_KEY = "pending_update_install"
    _PENDING_UPDATE_CLEANUP_KEY = "pending_update_cleanup"

    def __init__(self, repository: RecordRepository, currency_service: CurrencyService) -> None:
        self._repository = repository
        self._currency = currency_service

    def set_online_mode(self, enabled: bool) -> None:
        self._currency.set_online(enabled)
        if isinstance(self._repository, SchemaMetaRepository):
            self._repository.set_schema_meta("online_mode", "1" if enabled else "0")

    def load_online_mode_preference(self) -> bool:
        if not isinstance(self._repository, SchemaMetaRepository):
            return False
        value = self._repository.get_schema_meta("online_mode")
        return value == "1"

    def save_language_preference(self, code: str) -> None:
        if isinstance(self._repository, SchemaMetaRepository):
            self._repository.set_schema_meta("app_language", str(code or "").strip().lower())

    def load_language_preference(self) -> str | None:
        if not isinstance(self._repository, SchemaMetaRepository):
            return None
        value = self._repository.get_schema_meta("app_language")
        return str(value).strip().lower() if value else None

    def save_theme_preference(self, name: str) -> None:
        if isinstance(self._repository, SchemaMetaRepository):
            self._repository.set_schema_meta("app_theme", str(name or "").strip().lower())

    def load_theme_preference(self) -> str | None:
        if not isinstance(self._repository, SchemaMetaRepository):
            return None
        value = self._repository.get_schema_meta("app_theme")
        return str(value).strip().lower() if value else None

    def save_linux_terminal_preference(self, executable_path: str) -> None:
        if isinstance(self._repository, SchemaMetaRepository):
            self._repository.set_schema_meta(
                "linux_terminal_path",
                str(executable_path or "").strip(),
            )

    def load_linux_terminal_preference(self) -> str | None:
        if not isinstance(self._repository, SchemaMetaRepository):
            return None
        value = self._repository.get_schema_meta("linux_terminal_path")
        normalized = str(value or "").strip()
        return normalized or None

    def save_pending_update_install_state(self, state: PendingUpdateInstallState) -> None:
        if isinstance(self._repository, SchemaMetaRepository):
            payload = {
                "version": state.version,
                "asset_kind": state.asset_kind,
                "artifact_path": str(state.artifact_path),
                "release_url": state.release_url,
            }
            self._repository.set_schema_meta(
                self._PENDING_UPDATE_INSTALL_KEY,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )

    def load_pending_update_install_state(self) -> PendingUpdateInstallState | None:
        raw = self._load_schema_meta_json(self._PENDING_UPDATE_INSTALL_KEY)
        if raw is None:
            return None
        version = str(raw.get("version") or "").strip()
        asset_kind = str(raw.get("asset_kind") or "").strip()
        artifact_path = str(raw.get("artifact_path") or "").strip()
        release_url = str(raw.get("release_url") or "").strip()
        if not version or not asset_kind or not artifact_path:
            return None
        return PendingUpdateInstallState(
            version=version,
            asset_kind=asset_kind,
            artifact_path=Path(artifact_path),
            release_url=release_url,
        )

    def clear_pending_update_install_state(self) -> None:
        if isinstance(self._repository, SchemaMetaRepository):
            self._repository.set_schema_meta(self._PENDING_UPDATE_INSTALL_KEY, "")

    def save_pending_update_cleanup_state(self, state: PendingUpdateCleanupState) -> None:
        if isinstance(self._repository, SchemaMetaRepository):
            payload = {
                "artifact_path": str(state.artifact_path),
                "target_version": state.target_version,
            }
            self._repository.set_schema_meta(
                self._PENDING_UPDATE_CLEANUP_KEY,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )

    def load_pending_update_cleanup_state(self) -> PendingUpdateCleanupState | None:
        raw = self._load_schema_meta_json(self._PENDING_UPDATE_CLEANUP_KEY)
        if raw is None:
            return None
        artifact_path = str(raw.get("artifact_path") or "").strip()
        target_version = str(raw.get("target_version") or "").strip()
        if not artifact_path or not target_version:
            return None
        return PendingUpdateCleanupState(
            artifact_path=Path(artifact_path),
            target_version=target_version,
        )

    def clear_pending_update_cleanup_state(self) -> None:
        if isinstance(self._repository, SchemaMetaRepository):
            self._repository.set_schema_meta(self._PENDING_UPDATE_CLEANUP_KEY, "")

    def get_online_status_snapshot(self) -> OnlineStatusSnapshot:
        return OnlineStatusSnapshot(
            is_online=self._currency.is_online,
            last_fetched_at=self._currency.last_fetched_at,
        )

    def _load_schema_meta_json(self, key: str) -> dict[str, object] | None:
        if not isinstance(self._repository, SchemaMetaRepository):
            return None
        raw_value = str(self._repository.get_schema_meta(key) or "").strip()
        if not raw_value:
            return None
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            self._repository.set_schema_meta(key, "")
            return None
        return payload if isinstance(payload, dict) else None
