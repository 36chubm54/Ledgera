from __future__ import annotations

from domain.distribution import DistributionItem, FrozenDistributionRow, MonthlyDistribution
from gui.i18n import tr


def build_live_column_meta(
    context, items: list[DistributionItem]
) -> tuple[list[str], dict[str, str]]:
    column_ids = ["month", "fixed", "net_income"]
    headings = {
        "month": tr("common.month", "Месяц"),
        "fixed": tr("distribution.fixed", "Фиксация"),
        "net_income": (
            f"{tr('distribution.net_income', 'Чистый доход')} "
            f"({context.controller.get_display_currency_code()})"
        ),
    }
    for item in items:
        item_key = f"item_{item.id}"
        column_ids.append(item_key)
        headings[item_key] = item.name
        for subitem in context.controller.get_distribution_subitems(item.id):
            sub_key = f"sub_{subitem.id}"
            column_ids.append(sub_key)
            headings[sub_key] = f"  {subitem.name}"
    return column_ids, headings


def compose_column_meta(
    context,
    items: list[DistributionItem],
    visible_fixed_rows: list[FrozenDistributionRow],
) -> tuple[list[str], dict[str, str]]:
    column_ids, headings = build_live_column_meta(context, items)
    for frozen_row in visible_fixed_rows:
        for column_id in frozen_row.column_order:
            if column_id not in headings:
                column_ids.append(column_id)
                headings[column_id] = frozen_row.headings_by_column.get(column_id, column_id)
    return column_ids, headings


def distribution_row_values_map(
    context,
    distribution: MonthlyDistribution,
    items: list[DistributionItem],
    *,
    format_display_amount,
) -> dict[str, str]:
    item_results = {result.item.id: result for result in distribution.item_results}
    values = {
        "month": distribution.month,
        "fixed": "",
        "net_income": format_display_amount(distribution.net_income_base),
    }
    for item in items:
        result = item_results.get(item.id)
        item_key = f"item_{item.id}"
        if result is None:
            values[item_key] = "-"
            continue
        values[item_key] = format_display_amount(result.amount_base)
        sub_results = {sub.subitem.id: sub for sub in result.subitem_results}
        for subitem in context.controller.get_distribution_subitems(item.id):
            sub_key = f"sub_{subitem.id}"
            sub_result = sub_results.get(subitem.id)
            values[sub_key] = (
                "-" if sub_result is None else format_display_amount(sub_result.amount_base)
            )
    return values


def row_values_for_columns(column_ids: list[str], values_by_column: dict[str, str]) -> list[str]:
    return [values_by_column.get(column_id, "-") for column_id in column_ids]
