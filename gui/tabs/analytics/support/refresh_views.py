from __future__ import annotations

from utils.records.tags import display_tag_name

from ..core.breakdown_section import AnalyticsBreakdownSection, apply_breakdown_mode
from ..core.monthly_section import AnalyticsMonthlySection
from ..core.summary_section import AnalyticsSummarySection
from .refresh_support import AnalyticsDisplayFormatters


def update_summary_labels(
    *,
    summary: AnalyticsSummarySection,
    palette,
    formatters: AnalyticsDisplayFormatters,
    year: int,
    net_worth: float,
    savings_rate: float,
    burn_rate: float,
    avg_monthly_income: float,
    year_income: float,
    year_income_usd: float,
    avg_monthly_expenses: float,
    year_expense: float,
    day_cost: float,
    hour_cost: float,
    minute_cost: float,
    tr,
) -> None:
    summary.net_worth_label.config(
        text=tr(
            "analytics.net_worth",
            "Чистый капитал:  {amount}",
            amount=formatters.format_display_money(net_worth, 0),
        )
    )
    summary.savings_rate_label.config(
        text=tr(
            "analytics.savings_rate_value",
            "Норма сбережений:  {value}%",
            value=f"{savings_rate:.1f}",
        ),
        foreground=palette.chart_income if savings_rate >= 0 else palette.chart_expense,
    )
    summary.burn_rate_label.config(
        text=tr(
            "analytics.burn_rate_value",
            "Темп расходов:  {value}/{unit}",
            value=formatters.format_display_amount(burn_rate, 0),
            unit=tr("analytics.day_unit", "день"),
        )
    )
    summary.avg_monthly_income_label.config(
        text=tr(
            "analytics.avg_income_value",
            "Средний доход в месяц ({year}):  {value}",
            year=year,
            value=formatters.format_display_money(avg_monthly_income, 0),
        )
    )
    summary.year_income_label.config(
        text=tr(
            "analytics.year_income_value",
            "Доход за {year} год:  {value}",
            year=year,
            value=formatters.format_display_money(year_income, 0),
        )
    )
    summary.year_income_usd_label.config(
        text=tr(
            "analytics.year_income_usd_value",
            "Доход за {year} год (USD):  {value}",
            year=year,
            value=f"{year_income_usd:,.2f}",
        )
    )
    summary.avg_monthly_expenses_label.config(
        text=tr(
            "analytics.avg_expenses_value",
            "Средние расходы в месяц:  {value}",
            value=formatters.format_display_money(avg_monthly_expenses, 0),
        )
    )
    summary.year_expense_label.config(
        text=tr(
            "analytics.year_expense_value",
            "Расход за {year} год:  {value}",
            year=year,
            value=formatters.format_display_money(year_expense, 0),
        )
    )
    summary.day_cost_label.config(
        text=tr(
            "analytics.cost_day_value",
            "Стоимость дня:  {value}",
            value=formatters.format_display_money(float(day_cost), 0),
        )
    )
    summary.hour_cost_label.config(
        text=tr(
            "analytics.cost_hour_value",
            "Стоимость часа:  {value}",
            value=formatters.format_display_money(float(hour_cost), 2),
        )
    )
    summary.minute_cost_label.config(
        text=tr(
            "analytics.cost_minute_value",
            "Стоимость минуты:  {value}",
            value=formatters.format_display_money(float(minute_cost), 2),
        )
    )


def update_breakdown_views(
    *,
    breakdown: AnalyticsBreakdownSection,
    formatters: AnalyticsDisplayFormatters,
    spending_data,
    income_data,
    tag_data,
    is_tags_mode: bool,
) -> None:
    apply_breakdown_mode(breakdown, is_tags_mode=is_tags_mode)

    breakdown.spending_tree.delete(*breakdown.spending_tree.get_children())
    for item in spending_data:
        breakdown.spending_tree.insert(
            "",
            "end",
            values=(
                getattr(item, "category", ""),
                formatters.format_display_amount(
                    float(getattr(item, "total_base", 0.0)),
                    0,
                ),
                int(getattr(item, "record_count", 0)),
            ),
        )

    breakdown.income_tree.delete(*breakdown.income_tree.get_children())
    for item in income_data:
        breakdown.income_tree.insert(
            "",
            "end",
            values=(
                getattr(item, "category", ""),
                formatters.format_display_amount(
                    float(getattr(item, "total_base", 0.0)),
                    0,
                ),
                int(getattr(item, "record_count", 0)),
            ),
        )

    breakdown.tag_tree.delete(*breakdown.tag_tree.get_children())
    for item in tag_data:
        row_tag = ""
        row_color = str(getattr(item, "color", "") or "")
        if row_color:
            row_tag = f"tag_{row_color.replace('#', '').lower()}"
            breakdown.tag_tree.tag_configure(row_tag, foreground=row_color)
        breakdown.tag_tree.insert(
            "",
            "end",
            values=(
                display_tag_name(getattr(item, "tag", "")),
                formatters.format_display_amount(
                    float(getattr(item, "total_base", 0.0)),
                    0,
                ),
                int(getattr(item, "record_count", 0)),
            ),
            tags=((row_tag,) if row_tag else ()),
        )


def update_monthly_tree(
    *,
    monthly: AnalyticsMonthlySection,
    formatters: AnalyticsDisplayFormatters,
    monthly_data,
) -> None:
    monthly.monthly_tree.delete(*monthly.monthly_tree.get_children())
    for item in monthly_data:
        cashflow = float(getattr(item, "cashflow", 0.0))
        tag = "positive" if cashflow >= 0 else "negative"
        monthly.monthly_tree.insert(
            "",
            "end",
            values=(
                getattr(item, "month", ""),
                formatters.format_display_amount(
                    float(getattr(item, "income", 0.0)),
                    0,
                ),
                formatters.format_display_amount(
                    float(getattr(item, "expenses", 0.0)),
                    0,
                ),
                formatters.format_display_amount(cashflow, 0),
                f"{float(getattr(item, 'savings_rate', 0.0)):.1f}%",
            ),
            tags=(tag,),
        )
