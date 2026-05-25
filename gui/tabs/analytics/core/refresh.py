from __future__ import annotations

import logging
import tkinter as tk

from domain.validation import ensure_not_future, parse_ymd
from gui.i18n import tr
from gui.ui_helpers import show_error

from ..support.refresh_support import (
    AnalyticsDisplayFormatters,
    AnalyticsRefreshState,
)
from ..support.refresh_views import (
    update_breakdown_views,
    update_monthly_tree,
    update_summary_labels,
)
from .breakdown_section import AnalyticsBreakdownSection
from .contracts import AnalyticsTabContext
from .monthly_section import AnalyticsMonthlySection, AnalyticsTimelineSection
from .render import _draw_breakdown_pie, _draw_net_worth_line
from .summary_section import AnalyticsSummarySection

logger = logging.getLogger(__name__)


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

        update_summary_labels(
            summary=summary,
            palette=palette,
            formatters=formatters,
            year=year,
            net_worth=net_worth,
            savings_rate=savings_rate,
            burn_rate=burn_rate,
            avg_monthly_income=avg_monthly_income,
            year_income=year_income,
            year_income_usd=year_income_usd,
            avg_monthly_expenses=avg_monthly_expenses,
            year_expense=year_expense,
            day_cost=float(day_cost),
            hour_cost=float(hour_cost),
            minute_cost=float(minute_cost),
            tr=tr,
        )

        timeline_data = context.controller.get_net_worth_timeline()
        state.last_timeline_data = list(timeline_data) if timeline_data else []
        _draw_net_worth_line(
            timeline.timeline_canvas,
            state.last_timeline_data,
            format_amount=lambda value: formatters.format_display_amount(value, 0),
        )

        is_tags_mode = bool(breakdown_by_tags_var.get())
        spending_data = context.controller.get_spending_by_category(start, end)
        income_data = context.controller.get_income_by_category(start, end)
        tag_data = context.controller.get_spending_by_tag(start, end)
        update_breakdown_views(
            breakdown=breakdown,
            formatters=formatters,
            spending_data=spending_data,
            income_data=income_data,
            tag_data=tag_data,
            is_tags_mode=is_tags_mode,
        )

        state.last_breakdown_data = list(tag_data) if is_tags_mode else list(spending_data)
        _draw_breakdown_pie(
            breakdown.category_canvas,
            state.last_breakdown_data,
            format_amount=lambda value: formatters.format_display_amount(value, 0),
        )

        monthly_data = context.controller.get_monthly_summary(start_date=start, end_date=end)
        update_monthly_tree(
            monthly=monthly,
            formatters=formatters,
            monthly_data=monthly_data,
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
