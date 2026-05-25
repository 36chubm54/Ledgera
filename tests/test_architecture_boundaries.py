from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _iter_python_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.py") if path.is_file())


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_app_layer_does_not_import_infrastructure_repository_contracts() -> None:
    offenders: list[str] = []
    for path in _iter_python_files(ROOT / "app"):
        text = path.read_text(encoding="utf-8")
        if (
            "from infrastructure.sqlite_repository import" in text
            or "import infrastructure.sqlite_repository" in text
            or "from infrastructure.repositories import" in text
            or "import infrastructure.repositories" in text
        ):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_app_layer_does_not_import_gui_modules() -> None:
    offenders: list[str] = []
    for path in _iter_python_files(ROOT / "app"):
        text = path.read_text(encoding="utf-8")
        if "from gui." in text or "import gui." in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_domain_reports_has_no_io_helpers() -> None:
    report_path = ROOT / "domain" / "reports.py"
    text = report_path.read_text(encoding="utf-8")
    assert "def to_csv(" not in text
    assert "def from_csv(" not in text
    assert "def from_xlsx(" not in text
    assert "utils.csv_utils" not in text
    assert "utils.excel_utils" not in text


def test_services_layer_does_not_import_concrete_sqlite_repository() -> None:
    offenders: list[str] = []
    for path in _iter_python_files(ROOT / "services"):
        text = path.read_text(encoding="utf-8")
        if (
            "from infrastructure.sqlite_repository import SQLiteRecordRepository" in text
            or "import infrastructure.sqlite_repository" in text
        ):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_currency_service_facade_uses_extracted_helper_modules() -> None:
    service_path = ROOT / "app" / "services.py"
    text = service_path.read_text(encoding="utf-8")
    assert "from app.currency.config_flow import" in text
    assert "from app.currency.display import" in text
    assert "from app.currency.file_store import" in text
    assert "from app.currency.online_mode import" in text
    assert "from app.currency.runtime_config import" in text
    assert "from app.currency.runtime_engine import" in text


def test_app_has_no_top_level_compat_shim_files() -> None:
    legacy_shims = [
        ROOT / "app" / "audit_runner.py",
        ROOT / "app" / "finance_service.py",
        ROOT / "app" / "import_support.py",
        ROOT / "app" / "preferences_service.py",
        ROOT / "app" / "record_service.py",
        ROOT / "app" / "repository.py",
        ROOT / "app" / "repository_protocols.py",
        ROOT / "app" / "secret_storage.py",
        ROOT / "app" / "use_cases.py",
        ROOT / "app" / "use_cases_pkg" / "records.py",
    ]
    assert all(not path.exists() for path in legacy_shims)


def test_import_service_facade_uses_extracted_helper_modules() -> None:
    service_path = ROOT / "services" / "import_service.py"
    text = service_path.read_text(encoding="utf-8")
    assert "from services.importing.workflow import" in text
    assert "from services.importing.service_support import" in text


def test_service_helper_facades_use_extracted_helper_modules() -> None:
    expectations = {
        ROOT / "services" / "support" / "app_update.py": None,
        ROOT / "services" / "support" / "currency.py": None,
        ROOT / "services" / "support" / "sql_money.py": None,
    }
    assert all(path.exists() for path in expectations)


def test_extracted_helper_layers_do_not_import_gui_modules() -> None:
    offenders: list[str] = []
    helper_files = [
        ROOT / "app" / "currency" / "config_flow.py",
        ROOT / "app" / "currency" / "display.py",
        ROOT / "app" / "currency" / "file_store.py",
        ROOT / "app" / "currency" / "online_mode.py",
        ROOT / "app" / "currency" / "runtime_config.py",
        ROOT / "app" / "currency" / "runtime_engine.py",
        ROOT / "services" / "importing" / "adapters.py",
        ROOT / "services" / "importing" / "service_support.py",
        ROOT / "services" / "importing" / "workflow.py",
        ROOT / "app" / "data" / "records.py",
        ROOT / "app" / "data" / "repository.py",
        ROOT / "app" / "data" / "protocols.py",
        ROOT / "app" / "importing" / "finance.py",
        ROOT / "app" / "importing" / "support.py",
        ROOT / "app" / "runtime" / "audit.py",
        ROOT / "app" / "runtime" / "preferences.py",
        ROOT / "app" / "runtime" / "secret_storage.py",
        ROOT / "services" / "analytics" / "balance.py",
        ROOT / "services" / "analytics" / "dashboard.py",
        ROOT / "services" / "analytics" / "metrics.py",
        ROOT / "services" / "analytics" / "report.py",
        ROOT / "services" / "analytics" / "timeline.py",
        ROOT / "services" / "planning" / "budget" / "service.py",
        ROOT / "services" / "planning" / "debts" / "service.py",
        ROOT / "services" / "planning" / "distribution" / "service.py",
        ROOT / "services" / "portfolio" / "assets.py",
        ROOT / "services" / "portfolio" / "goals.py",
    ]
    for path in helper_files:
        text = path.read_text(encoding="utf-8")
        if "from gui." in text or "import gui." in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_import_helper_layers_do_not_import_concrete_sqlite_repository() -> None:
    offenders: list[str] = []
    helper_files = [
        ROOT / "services" / "importing" / "adapters.py",
        ROOT / "services" / "importing" / "service_support.py",
        ROOT / "services" / "importing" / "workflow.py",
    ]
    for path in helper_files:
        text = path.read_text(encoding="utf-8")
        if (
            "from infrastructure.sqlite_repository import" in text
            or "import infrastructure.sqlite_repository" in text
        ):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_runtime_and_data_helper_layers_do_not_import_gui_modules() -> None:
    offenders: list[str] = []
    helper_files = [
        ROOT / "app" / "runtime" / "audit.py",
        ROOT / "app" / "runtime" / "preferences.py",
        ROOT / "app" / "runtime" / "secret_storage.py",
        ROOT / "app" / "data" / "records.py",
        ROOT / "app" / "data" / "repository.py",
        ROOT / "app" / "data" / "protocols.py",
    ]
    for path in helper_files:
        text = path.read_text(encoding="utf-8")
        if "from gui." in text or "import gui." in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_gui_controller_does_not_import_concrete_sqlite_repository() -> None:
    controller_path = ROOT / "gui" / "controllers.py"
    text = controller_path.read_text(encoding="utf-8")
    assert "from infrastructure.sqlite_repository import SQLiteRecordRepository" not in text
    assert "import infrastructure.sqlite_repository" not in text


def test_use_cases_packages_do_not_reintroduce_records_fascade() -> None:
    records_fascade = ROOT / "app" / "use_cases_pkg" / "records.py"
    assert not records_fascade.exists()


def test_gui_tabs_have_no_legacy_tab_shim_files() -> None:
    legacy_shims = [
        ROOT / "gui" / "tabs" / "analytics_tab.py",
        ROOT / "gui" / "tabs" / "budget_tab.py",
        ROOT / "gui" / "tabs" / "dashboard_tab.py",
        ROOT / "gui" / "tabs" / "debts_tab.py",
        ROOT / "gui" / "tabs" / "distribution_tab.py",
        ROOT / "gui" / "tabs" / "infographics_tab.py",
        ROOT / "gui" / "tabs" / "mandatory_tab.py",
        ROOT / "gui" / "tabs" / "operations_tab.py",
        ROOT / "gui" / "tabs" / "reports_tab.py",
        ROOT / "gui" / "tabs" / "settings_tab.py",
    ]
    assert all(not path.exists() for path in legacy_shims)


def test_gui_settings_has_no_legacy_support_shim_files() -> None:
    legacy_shims = [
        ROOT / "gui" / "tabs" / "settings" / "audit_dialog.py",
        ROOT / "gui" / "tabs" / "settings" / "builder.py",
        ROOT / "gui" / "tabs" / "settings" / "contracts.py",
        ROOT / "gui" / "tabs" / "settings" / "update_flow.py",
        ROOT / "gui" / "tabs" / "settings" / "update_support.py",
        ROOT / "gui" / "tabs" / "settings" / "wallets_support.py",
        ROOT / "gui" / "tabs" / "settings" / "wallets_ui.py",
    ]
    assert all(not path.exists() for path in legacy_shims)


def test_gui_tab_internal_modules_do_not_import_tab_package_entrypoints() -> None:
    offenders: list[str] = []
    tab_dirs = [
        ROOT / "gui" / "tabs" / "analytics",
        ROOT / "gui" / "tabs" / "budget",
        ROOT / "gui" / "tabs" / "dashboard",
        ROOT / "gui" / "tabs" / "debts",
        ROOT / "gui" / "tabs" / "distribution",
        ROOT / "gui" / "tabs" / "infographics",
        ROOT / "gui" / "tabs" / "mandatory",
        ROOT / "gui" / "tabs" / "operations",
        ROOT / "gui" / "tabs" / "reports",
        ROOT / "gui" / "tabs" / "settings",
    ]
    package_import_markers = [
        "from gui.tabs.analytics import",
        "import gui.tabs.analytics",
        "from gui.tabs.budget import",
        "import gui.tabs.budget",
        "from gui.tabs.dashboard import",
        "import gui.tabs.dashboard",
        "from gui.tabs.debts import",
        "import gui.tabs.debts",
        "from gui.tabs.distribution import",
        "import gui.tabs.distribution",
        "from gui.tabs.infographics import",
        "import gui.tabs.infographics",
        "from gui.tabs.mandatory import",
        "import gui.tabs.mandatory",
        "from gui.tabs.operations import",
        "import gui.tabs.operations",
        "from gui.tabs.reports import",
        "import gui.tabs.reports",
        "from gui.tabs.settings import",
        "import gui.tabs.settings",
    ]
    for directory in tab_dirs:
        for path in _iter_python_files(directory):
            if path.name == "__init__.py":
                continue
            text = _read_text(path)
            if any(marker in text for marker in package_import_markers):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_app_internal_packages_do_not_import_top_level_compat_facades() -> None:
    offenders: list[str] = []
    internal_dirs = [
        ROOT / "app" / "data",
        ROOT / "app" / "importing",
        ROOT / "app" / "runtime",
        ROOT / "app" / "use_cases_pkg",
    ]
    forbidden_markers = [
        "from app.audit_runner import",
        "import app.audit_runner",
        "from app.finance_service import",
        "import app.finance_service",
        "from app.import_support import",
        "import app.import_support",
        "from app.preferences_service import",
        "import app.preferences_service",
        "from app.record_service import",
        "import app.record_service",
        "from app.repository import",
        "import app.repository",
        "from app.repository_protocols import",
        "import app.repository_protocols",
        "from app.secret_storage import",
        "import app.secret_storage",
        "from app.use_cases import",
        "import app.use_cases",
    ]
    for directory in internal_dirs:
        for path in _iter_python_files(directory):
            text = _read_text(path)
            if any(marker in text for marker in forbidden_markers):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_gui_runtime_uses_tab_packages_not_removed_tab_shims() -> None:
    runtime_files = [
        ROOT / "gui" / "tab_lifecycle.py",
        ROOT / "gui" / "tabs" / "__init__.py",
        ROOT / "gui" / "tkinter_gui.py",
    ]
    for path in runtime_files:
        text = _read_text(path)
        assert "_tab import" not in text
        assert "_tab.py" not in text
