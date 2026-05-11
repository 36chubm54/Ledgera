from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.repository import RecordRepository
from app.repository_protocols import SchemaMetaRepository
from app.services import CurrencyService


@dataclass(frozen=True)
class OnlineStatusSnapshot:
    is_online: bool
    last_fetched_at: datetime | None


class UIPreferencesService:
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

    def get_online_status_snapshot(self) -> OnlineStatusSnapshot:
        return OnlineStatusSnapshot(
            is_online=self._currency.is_online,
            last_fetched_at=self._currency.last_fetched_at,
        )
