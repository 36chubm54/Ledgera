from __future__ import annotations

from domain.debt import Debt
from domain.reports import Report
from domain.validation import parse_ymd


def debts_for_report_period(report: Report, debts: list[Debt] | None) -> list[Debt]:
    normalized = list(debts or [])
    if not normalized:
        return []

    if not report.period_start_date or not report.period_end_date:
        return sorted(normalized, key=lambda item: (str(item.status.value), str(item.contact_name)))

    start = parse_ymd(report.period_start_date)
    end = parse_ymd(report.period_end_date)
    visible: list[Debt] = []
    for debt in normalized:
        created = parse_ymd(debt.created_at)
        closed = parse_ymd(debt.closed_at) if debt.closed_at else None
        if created > end:
            continue
        if closed is not None and closed < start:
            continue
        visible.append(debt)
    return sorted(visible, key=lambda item: (str(item.status.value), str(item.contact_name)))


def debt_progress_percent(debt: Debt) -> float:
    total = max(int(debt.total_amount_minor), 1)
    settled = max(0, int(debt.total_amount_minor) - int(debt.remaining_amount_minor))
    return round(settled * 100.0 / total, 2)
