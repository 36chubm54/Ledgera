from __future__ import annotations

from pathlib import Path

from app.services import CurrencyService
from domain.update import PendingUpdateCleanupState, PendingUpdateInstallState
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


def test_sqlite_controller_clears_malformed_pending_update_install_state(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "prefs.db"), schema_path=_schema_path())
    controller = FinancialController(repo, CurrencyService())
    repo.set_schema_meta("pending_update_install", "{broken")

    assert controller.load_pending_update_install_state() is None
    assert repo.get_schema_meta("pending_update_install") == ""
    repo.close()


def test_sqlite_controller_reconciles_pending_update_states_after_upgrade(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "prefs.db"), schema_path=_schema_path())
    controller = FinancialController(repo, CurrencyService())
    artifact_path = tmp_path / "Ledgera-2.5.1-x86_64.deb"
    artifact_path.write_text("package", encoding="utf-8")

    controller.save_pending_update_install_state(
        PendingUpdateInstallState(
            version="2.5.1",
            asset_kind="linux-deb",
            artifact_path=artifact_path,
            release_url="https://example.invalid/release",
        )
    )
    controller.mark_pending_update_cleanup(
        artifact_path=str(artifact_path),
        target_version="2.5.1",
    )

    controller._app_update.get_current_version = lambda: "2.5.1"  # type: ignore[method-assign]
    controller.reconcile_pending_update_state()

    assert controller.load_pending_update_install_state() is None
    assert controller._ui_preferences.load_pending_update_cleanup_state() is None  # type: ignore[attr-defined]
    assert not artifact_path.exists()
    repo.close()


def test_sqlite_controller_keeps_pending_cleanup_on_old_version_restart(tmp_path: Path) -> None:
    repo = SQLiteRecordRepository(str(tmp_path / "prefs.db"), schema_path=_schema_path())
    controller = FinancialController(repo, CurrencyService())
    artifact_path = tmp_path / "Ledgera-2.5.1-x86_64.rpm"
    artifact_path.write_text("package", encoding="utf-8")

    controller._ui_preferences.save_pending_update_cleanup_state(  # type: ignore[attr-defined]
        PendingUpdateCleanupState(
            artifact_path=artifact_path,
            target_version="2.5.1",
        )
    )

    controller._app_update.get_current_version = lambda: "2.5.0-rc2"  # type: ignore[method-assign]
    controller.reconcile_pending_update_state()

    cleanup_state = controller._ui_preferences.load_pending_update_cleanup_state()  # type: ignore[attr-defined]
    assert cleanup_state is not None
    assert cleanup_state.artifact_path == artifact_path
    assert artifact_path.exists()
    repo.close()
