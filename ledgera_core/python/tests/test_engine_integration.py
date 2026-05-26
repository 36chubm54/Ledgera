import sys
from pathlib import Path
from typing import Protocol, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ledgera_core as _ledgera_core


class _LedgeraCoreModule(Protocol):
    def calculate_daily_burn(self, total_spent: float, days_passed: int) -> float: ...


ledgera_core = cast(_LedgeraCoreModule, _ledgera_core)


def test_rust_core_integration() -> None:
    total = 50000.0
    days = 10

    expected = 5000.0
    actual = ledgera_core.calculate_daily_burn(total, days)

    assert actual == expected, f"Rust вернул {actual}, ожидалось {expected}"


def test_rust_edge_cases() -> None:
    assert ledgera_core.calculate_daily_burn(1000.0, -1) == 1000.0
