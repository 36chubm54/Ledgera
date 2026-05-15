from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, field

from domain.validation import ensure_not_future, parse_ymd
from gui.i18n import tr
from gui.ui_helpers import show_error
from utils.tag_utils import display_tag_name

from .breakdown_section import AnalyticsBreakdownSection, apply_breakdown_mode
from .contracts import AnalyticsTabContext
from .monthly_section import AnalyticsMonthlySection, AnalyticsTimelineSection
from .render import _draw_breakdown_pie, _draw_net_worth_line
from .summary_section import AnalyticsSummarySection

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AnalyticsDisplayFormatters:
    display_code: Callable[[], str]
    format_display_amount: Callable[[float, int], str]
    format_display_money: Callable[[float, int], str]


@dataclass(slots=True)
class AnalyticsRefreshState:
    last_timeline_data: list = field(default_factory=list)
    last_breakdown_data: list = field(default_factory=list)
    redraw_job: str | None = None


def build_display_formatters(context: AnalyticsTabContext) -> AnalyticsDisplayFormatters:
    def display_code() -> str:
        getter = getattr(context.controller, "get_display_currency_code", None)
        if callable(getter):
            return str(getter())
        getter = getattr(context.controller, "get_display_currency", None)
        if callable(getter):
            return str(getter())
        return "KZT"

    def format_display_amount(amount: float, precision: int = 0) -> str:
        formatter = getattr(context.controller, "format_display_amount", None)
        if callable(formatter):
            return str(formatter(amount, precision=precision))
        return f"{float(amount):,.{precision}f}"

    def format_display_money(amount: float, precision: int = 0) -> str:
        formatter = getattr(context.controller, "format_display_money", None)
        if callable(formatter):
            try:
                return str(formatter(amount, precision=precision))
            except TypeError:
                return str(formatter(amount, precision))
        return f"{format_display_amount(amount, precision=precision)} {display_code()}"

    return AnalyticsDisplayFormatters(
        display_code=display_code,
        format_display_amount=format_display_amount,
        format_display_money=format_display_money,
    )


def redraw_analytics_canvases(
    *,
    state: AnalyticsRefreshState,
    timeline: AnalyticsTimelineSection,
    breakdown: AnalyticsBreakdownSection,
    formatters: AnalyticsDisplayFormatters,
) -> None:
    state.redraw_job = None
    _draw_net_worth_line(
        timeline.timeline_canvas,
        state.last_timeline_data,
        format_amount=lambda value: formatters.format_display_amount(value, 0),
    )
    _draw_breakdown_pie(
        breakdown.category_canvas,
        state.last_breakdown_data,
        format_amount=lambda value: formatters.format_display_amount(value, 0),
    )


def schedule_analytics_redraw(
    *,
    context: AnalyticsTabContext,
    state: AnalyticsRefreshState,
    timeline: AnalyticsTimelineSection,
    breakdown: AnalyticsBreakdownSection,
    formatters: AnalyticsDisplayFormatters,
) -> None:
    if state.redraw_job is not None:
        try:
            context.after_cancel(state.redraw_job)
        except (tk.TclError, RuntimeError):
            pass
    state.redraw_job = context.after(
        120,
        lambda: redraw_analytics_canvases(
            state=state,
            timeline=timeline,
            breakdown=breakdown,
            formatters=formatters,
        ),
    )


def refresh_analytics(
    *,
    context: AnalyticsTabContext,
    summary: AnalyticsSummarySection,
    breakdown: AnalyticsBreakdownSection,
    timeline: AnalyticsTimelineSection,
    monthly: AnalyticsMonthlySection,
    breakdown_by_tags_var: tk.BooleanVar,
    period_from_text: str,
    period_to_text: str,
    default_start: str,
    default_end: str,
    palette,
    formatters: AnalyticsDisplayFormatters,
    state: AnalyticsRefreshState,
) -> None:
    start = period_from_text.strip() or default_start
    end = period_to_text.strip() or default_end

    try:
        parsed_start = parse_ymd(start)
        parsed_end = parse_ymd(end)
        ensure_not_future(parsed_start)
        ensure_not_future(parsed_end)
        if parsed_start > parsed_end:
            raise ValueError(
                tr(
                    "analytics.error.period_order",
                    "Начальная дата должна быть не позже конечной.",
                )
            )

        start = parsed_start.isoformat()
        end = parsed_end.isoformat()

        net_worth = float(context.controller.get_total_balance(date=end))
        savings_rate = float(context.controller.get_savings_rate(start, end))
        burn_rate = float(context.controller.get_burn_rate(start, end))
        year = int(parsed_end.year)
        avg_monthly_income = float(
            context.controller.get_average_monthly_income(year, up_to_date=end)
        )
        year_income = float(context.controller.get_year_income(year, up_to_date=end))
        year_income_usd = float(context.controller.convert_base_to_usd(year_income))
        year_expense = float(context.controller.get_year_expense(year, up_to_date=end))
        avg_monthly_expenses = float(context.controller.get_average_monthly_expenses(start, end))
        day_cost, hour_cost, minute_cost = context.controller.get_time_costs(start, end)

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

        timeline_data = context.controller.get_net_worth_timeline()
        state.last_timeline_data = list(timeline_data) if timeline_data else []
        _draw_net_worth_line(
            timeline.timeline_canvas,
            state.last_timeline_data,
            format_amount=lambda value: formatters.format_display_amount(value, 0),
        )

        is_tags_mode = bool(breakdown_by_tags_var.get())
        apply_breakdown_mode(breakdown, is_tags_mode=is_tags_mode)

        spending_data = context.controller.get_spending_by_category(start, end)
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

        income_data = context.controller.get_income_by_category(start, end)
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

        tag_data = context.controller.get_spending_by_tag(start, end)
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

        state.last_breakdown_data = list(tag_data) if is_tags_mode else list(spending_data)
        _draw_breakdown_pie(
            breakdown.category_canvas,
            state.last_breakdown_data,
            format_amount=lambda value: formatters.format_display_amount(value, 0),
        )

        monthly_data = context.controller.get_monthly_summary(start_date=start, end_date=end)
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
    except (ValueError, TypeError, RuntimeError, tk.TclError) as error:
        logger.warning("Analytics refresh error: %s", error)
        if isinstance(error, ValueError):
            show_error(
                tr(
                    "analytics.error.invalid_period",
                    "{error}\n\nИспользуйте формат YYYY-MM-DD и убедитесь, "
                    "что даты не из будущего.",
                    error=error,
                ),
                title=tr("analytics.error.invalid_period_title", "Некорректный период"),
            )
