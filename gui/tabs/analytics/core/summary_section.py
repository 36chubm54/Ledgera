from __future__ import annotations

from dataclasses import dataclass
from tkinter import ttk

from gui.i18n import tr
from gui.tooltip import Tooltip
from gui.ui_theme import create_card_section


@dataclass(slots=True)
class AnalyticsSummarySection:
    net_worth_label: ttk.Label
    savings_rate_label: ttk.Label
    burn_rate_label: ttk.Label
    avg_monthly_income_label: ttk.Label
    avg_monthly_expenses_label: ttk.Label
    year_income_label: ttk.Label
    year_income_usd_label: ttk.Label
    year_expense_label: ttk.Label
    day_cost_label: ttk.Label
    hour_cost_label: ttk.Label
    minute_cost_label: ttk.Label


def build_summary_section(parent, *, palette):
    dashboard_card = create_card_section(parent, tr("analytics.summary", "Сводка"))
    dashboard_card.grid(row=1, column=0, sticky="nsew", padx=(16, 6), pady=(6, 16))
    dashboard_frame = dashboard_card.winfo_children()[-1]
    dashboard_frame.grid_columnconfigure(0, weight=1)

    dashboard_row = ttk.Frame(dashboard_frame, padding=(10, 10))
    dashboard_row.grid(row=0, column=0, sticky="ew")
    dashboard_row.grid_columnconfigure(0, weight=1)
    dashboard_row.grid_columnconfigure(1, weight=1)

    dashboard_left = ttk.Frame(dashboard_row)
    dashboard_left.grid(row=0, column=0, sticky="nsew")
    dashboard_left.grid_rowconfigure(3, weight=1)
    dashboard_right = ttk.Frame(dashboard_row)
    dashboard_right.grid(row=0, column=1, sticky="nw", padx=(24, 0))

    font = ("Segoe UI", 12, "bold")

    net_worth_label = ttk.Label(
        dashboard_left,
        text=tr("analytics.net_worth", "Чистый капитал:  {amount}", amount="—"),
        font=font,
    )
    net_worth_label.grid(row=0, column=0, sticky="w")

    savings_rate_label = ttk.Label(
        dashboard_left,
        text=tr("analytics.savings_rate", "Норма сбережений: —"),
        font=font,
    )
    savings_rate_label.grid(row=1, column=0, sticky="w")

    burn_rate_label = ttk.Label(
        dashboard_left,
        text=tr("analytics.burn_rate", "Темп расходов: —"),
        font=font,
    )
    burn_rate_label.grid(row=2, column=0, sticky="w")

    tooltip_label = ttk.Label(dashboard_left, text="ⓘ", font=("Segoe UI", 10))
    tooltip_label.config(foreground=palette.text_muted)
    tooltip_label.grid(row=3, column=0, sticky="sw")

    Tooltip(
        tooltip_label,
        tr(
            "analytics.tooltip",
            "Норма сбережений = денежный поток / доход * 100%."
            "\nТемп расходов = общие расходы / число дней в периоде."
            "\nСредний доход в месяц считается по всем месяцам."
            "\nДоход за год — сумма доходов за выбранный год."
            "\nДоход за год (USD) — тот же доход после конвертации."
            "\nСредние расходы в месяц считаются по всем месяцам."
            "\nРасход за год — сумма расходов за выбранный год."
            "\nСтоимость дня, часа и минуты рассчитывается из текущего темпа расходов.",
        ),
    )

    avg_monthly_income_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.avg_income", "Средний доход в месяц: —"),
        font=font,
    )
    avg_monthly_income_label.grid(row=0, column=0, sticky="w")

    avg_monthly_expenses_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.avg_expenses", "Средние расходы в месяц: —"),
        font=font,
    )
    avg_monthly_expenses_label.grid(row=1, column=0, sticky="w")

    year_income_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.year_income", "Доход за год: —"),
        font=font,
    )
    year_income_label.grid(row=2, column=0, sticky="w", pady=(10, 0))

    year_income_usd_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.year_income_usd", "Доход за год (USD): —"),
        font=font,
    )
    year_income_usd_label.grid(row=3, column=0, sticky="w")

    year_expense_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.year_expense", "Расход за год: —"),
        font=font,
    )
    year_expense_label.grid(row=4, column=0, sticky="w")

    day_cost_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.cost_day", "Стоимость дня: —"),
        font=font,
    )
    day_cost_label.grid(row=5, column=0, sticky="w", pady=(10, 0))

    hour_cost_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.cost_hour", "Стоимость часа: —"),
        font=font,
    )
    hour_cost_label.grid(row=6, column=0, sticky="w")

    minute_cost_label = ttk.Label(
        dashboard_right,
        text=tr("analytics.cost_minute", "Стоимость минуты: —"),
        font=font,
    )
    minute_cost_label.grid(row=7, column=0, sticky="w")

    return AnalyticsSummarySection(
        net_worth_label=net_worth_label,
        savings_rate_label=savings_rate_label,
        burn_rate_label=burn_rate_label,
        avg_monthly_income_label=avg_monthly_income_label,
        avg_monthly_expenses_label=avg_monthly_expenses_label,
        year_income_label=year_income_label,
        year_income_usd_label=year_income_usd_label,
        year_expense_label=year_expense_label,
        day_cost_label=day_cost_label,
        hour_cost_label=hour_cost_label,
        minute_cost_label=minute_cost_label,
    )
