from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _iter_python_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.py") if path.is_file())


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


def test_gui_controller_does_not_import_concrete_sqlite_repository() -> None:
    controller_path = ROOT / "gui" / "controllers.py"
    text = controller_path.read_text(encoding="utf-8")
    assert "from infrastructure.sqlite_repository import SQLiteRecordRepository" not in text
    assert "import infrastructure.sqlite_repository" not in text
