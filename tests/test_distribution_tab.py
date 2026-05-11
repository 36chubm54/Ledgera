from __future__ import annotations

from gui.tabs.distribution_tab import _snapshot_values_to_display


def test_snapshot_values_to_display_reformats_numeric_distribution_columns() -> None:
    values = {
        "month": "2026-05",
        "fixed": "✓",
        "net_income": "-76,750.72",
        "item_1": "11,178",
        "sub_5": "-4,605.04",
        "label": "unchanged",
    }

    def _format_display_amount(amount: float, precision: int) -> str:
        assert precision == 2
        return f"disp:{amount:.2f}"

    actual = _snapshot_values_to_display(
        values,
        format_display_amount=_format_display_amount,
    )

    assert actual["month"] == "2026-05"
    assert actual["fixed"] == "✓"
    assert actual["net_income"] == "disp:-76750.72"
    assert actual["item_1"] == "disp:11178.00"
    assert actual["sub_5"] == "disp:-4605.04"
    assert actual["label"] == "unchanged"
