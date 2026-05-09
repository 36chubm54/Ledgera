from __future__ import annotations

from pathlib import Path

from app.services import CurrencyService
from gui.controllers import FinancialController
from infrastructure.repositories import JsonFileRecordRepository
from infrastructure.sqlite_repository import SQLiteRecordRepository
from tests.type_helpers import typed_repo


def _schema_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "db" / "schema.sql")


def test_sqlite_controller_persists_language_and_theme_preferences(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "prefs.db"), schema_path=_schema_path())
    controller = FinancialController(repo, CurrencyService())

    assert controller.load_language_preference() is None
    assert controller.load_theme_preference() is None

    controller.save_language_preference("en")
    controller.save_theme_preference("dark")

    assert controller.load_language_preference() == "en"
    assert controller.load_theme_preference() == "dark"
    repo.close()


def test_non_sqlite_controller_preferences_are_safe_noops(tmp_path: Path) -> None:
    repo = JsonFileRecordRepository(str(tmp_path / "data.json"))
    controller = FinancialController(typed_repo(repo), CurrencyService())

    controller.save_language_preference("en")
    controller.save_theme_preference("dark")

    assert controller.load_language_preference() is None
    assert controller.load_theme_preference() is None
