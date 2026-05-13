from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

import pytest

import bootstrap as bootstrap_module
from app.services import CurrencyService
from bootstrap import bootstrap_repository
from gui.initial_setup import (
    InitialSetupSelection,
    _supported_provider_names,
    build_initial_currency_config,
    ensure_initial_setup,
    should_run_initial_setup,
    validate_initial_setup_selection,
)
from infrastructure.currency_providers import BaseRateProvider, CurrencyProviderRegistry
from infrastructure.sqlite_repository import SQLiteRecordRepository


def test_should_run_initial_setup_when_sqlite_is_missing(tmp_path: Path) -> None:
    assert should_run_initial_setup(tmp_path / "missing.db") is True


def test_should_run_initial_setup_quarantines_malformed_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "broken.db"
    db_path.write_text("not a sqlite database", encoding="utf-8")

    assert should_run_initial_setup(db_path) is True
    assert not db_path.exists()
    quarantine_candidates = list(tmp_path.glob("broken.db.corrupt_*"))
    assert len(quarantine_candidates) == 1
    assert quarantine_candidates[0].read_text(encoding="utf-8") == "not a sqlite database"


def test_validate_initial_setup_selection_rejects_same_primary_and_fallback() -> None:
    try:
        validate_initial_setup_selection(
            {
                "base_currency": "KZT",
                "display_currency": "USD",
                "provider_mode": "personal",
                "primary_provider": "nbk",
                "fallback_provider": "nbk",
                "exchange_rate_api_key": "",
                "auto_update": True,
                "update_interval_minutes": 15,
            }
        )
        raise AssertionError("Expected ValueError for duplicate providers")
    except ValueError as exc:
        assert "different" in str(exc)


def test_validate_initial_setup_selection_rejects_invalid_update_interval() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        validate_initial_setup_selection(
            {
                "base_currency": "KZT",
                "display_currency": "USD",
                "provider_mode": "personal",
                "primary_provider": "nbk",
                "fallback_provider": "exchange_rate",
                "exchange_rate_api_key": "",
                "auto_update": True,
                "update_interval_minutes": "abc",
            }
        )


def test_build_initial_currency_config_sets_runtime_fields() -> None:
    selection = InitialSetupSelection(
        base_currency="USD",
        display_currency="EUR",
        provider_mode="commercial",
        primary_provider="exchange_rate",
        fallback_provider="static",
        exchange_rate_api_key="secret",
        auto_update=False,
        update_interval_minutes=15,
    )

    config = build_initial_currency_config(selection)

    assert config["base_currency"] == "USD"
    assert config["display_currency"] == "EUR"
    assert config["provider_mode"] == "commercial"
    assert config["primary_provider"] == "exchange_rate"
    assert config["fallback_provider"] == "exchange_rate"
    assert config["commercial_fallback_provider"] == "static"
    assert config["exchange_rate_api_key"] == "secret"
    assert config["auto_update"] is False
    assert config["update_interval_minutes"] == 15


def test_build_initial_currency_config_preserves_inactive_fallback_key() -> None:
    selection = InitialSetupSelection(
        base_currency="USD",
        display_currency="EUR",
        provider_mode="personal",
        primary_provider="exchange_rate",
        fallback_provider="static",
        exchange_rate_api_key="secret",
        auto_update=True,
        update_interval_minutes=30,
    )

    config = build_initial_currency_config(
        selection,
        current_config={"commercial_fallback_provider": "cbr"},
    )

    assert config["fallback_provider"] == "static"
    assert config["commercial_fallback_provider"] == "cbr"


def test_ensure_initial_setup_persists_selection_and_returns_base(tmp_path: Path) -> None:
    config_path = tmp_path / "currency_config.json"

    outcome = ensure_initial_setup(
        sqlite_path=tmp_path / "missing.db",
        config_file=config_path,
        setup_runner=lambda **_kwargs: {
            "base_currency": "USD",
            "display_currency": "EUR",
            "provider_mode": "personal",
            "primary_provider": "exchange_rate",
            "fallback_provider": "static",
            "exchange_rate_api_key": "key",
            "auto_update": True,
            "update_interval_minutes": 30,
        },
    )

    saved = CurrencyService.load_config_payload(config_file=config_path, use_env_override=False)
    assert outcome.should_launch is True
    assert outcome.initial_base_currency == "USD"
    assert saved["base_currency"] == "USD"
    assert saved["display_currency"] == "EUR"
    assert saved["update_interval_minutes"] == 30


def test_supported_provider_names_use_passed_current_config() -> None:
    class _CustomProvider(BaseRateProvider):
        @property
        def name(self) -> str:
            return "custom"

        def fetch(self) -> dict[str, float]:
            return {"USD": 500.0}

    registry = CurrencyProviderRegistry()
    registry.register(
        "custom",
        lambda context: _CustomProvider() if context.config.get("allow_custom") else None,
    )

    names = _supported_provider_names(
        "KZT",
        current_config={"allow_custom": True},
        provider_registry=registry,
    )

    assert names == ("custom",)


def test_supported_provider_names_exclude_cbr_for_usd_base() -> None:
    names = _supported_provider_names("USD")

    assert "cbr" not in names
    assert "exchange_rate" in names
    assert "static" in names


def test_ensure_initial_setup_cancellation_stops_launch(tmp_path: Path) -> None:
    config_path = tmp_path / "currency_config.json"

    outcome = ensure_initial_setup(
        sqlite_path=tmp_path / "missing.db",
        config_file=config_path,
        setup_runner=lambda **_kwargs: None,
    )

    assert outcome.should_launch is False
    assert not config_path.exists()


def test_bootstrap_repository_uses_initial_base_currency_for_new_db(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(bootstrap_module, "SQLITE_PATH", str(db_path))

    repo = cast(
        SQLiteRecordRepository,
        bootstrap_repository(run_maintenance=False, initial_base_currency="USD"),
    )
    try:
        assert repo.get_schema_meta("base_currency") == "USD"
        assert repo.get_system_wallet().currency == "USD"
    finally:
        repo.close()


def test_bootstrap_repository_recovers_after_initial_setup_quarantines_malformed_db(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "finance.db"
    db_path.write_text("not a sqlite database", encoding="utf-8")
    monkeypatch.setattr(bootstrap_module, "SQLITE_PATH", str(db_path))

    assert should_run_initial_setup(db_path) is True

    repo = cast(
        SQLiteRecordRepository,
        bootstrap_repository(run_maintenance=False, initial_base_currency="USD"),
    )
    try:
        assert repo.get_schema_meta("base_currency") == "USD"
        assert repo.get_system_wallet().currency == "USD"
    finally:
        repo.close()

    quarantine_candidates = list(tmp_path.glob("finance.db.corrupt_*"))
    assert len(quarantine_candidates) == 1


def test_bootstrap_repository_does_not_override_existing_base_currency(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(bootstrap_module, "SQLITE_PATH", str(db_path))

    repo = cast(
        SQLiteRecordRepository,
        bootstrap_repository(run_maintenance=False, initial_base_currency="EUR"),
    )
    try:
        assert repo.get_schema_meta("base_currency") == "EUR"
        assert repo.get_system_wallet().currency == "EUR"
    finally:
        repo.close()

    repo = cast(
        SQLiteRecordRepository,
        bootstrap_repository(run_maintenance=False, initial_base_currency="USD"),
    )
    try:
        assert repo.get_schema_meta("base_currency") == "EUR"
        assert repo.get_system_wallet().currency == "EUR"
    finally:
        repo.close()


def test_should_run_initial_setup_false_for_initialized_db(tmp_path: Path) -> None:
    db_path = tmp_path / "initialized.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE wallets ("
            "id INTEGER PRIMARY KEY, "
            "name TEXT, "
            "currency TEXT, "
            "initial_balance REAL, "
            "initial_balance_minor INTEGER, "
            "system INTEGER, "
            "allow_negative INTEGER, "
            "is_active INTEGER)"
        )
        conn.execute("INSERT INTO schema_meta (key, value) VALUES ('base_currency', 'USD')")
        conn.execute(
            "INSERT INTO wallets ("
            "id, name, currency, initial_balance, initial_balance_minor, "
            "system, allow_negative, is_active"
            ") VALUES (1, 'Main wallet', 'USD', 0, 0, 1, 0, 1)"
        )
        conn.commit()

    assert should_run_initial_setup(db_path) is False
