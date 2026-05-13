from __future__ import annotations

from gui.i18n import tr


def app_title() -> str:
    return tr("app.title", "Финансовый учет")


def get_tab_titles() -> dict[str, str]:
    return {
        "infographics": tr("tab.infographics", "Инфографика"),
        "operations": tr("tab.operations", "Операции"),
        "reports": tr("tab.reports", "Отчеты"),
        "analytics": tr("tab.analytics", "Аналитика"),
        "dashboard": tr("tab.dashboard", "Дашборд"),
        "budget": tr("tab.budget", "Бюджет"),
        "debts": tr("tab.debts", "Долги"),
        "distribution": tr("tab.distribution", "Распределение"),
        "mandatory": tr("tab.mandatory", "Обязательные"),
        "settings": tr("tab.settings", "Настройки"),
    }


def get_import_formats() -> dict[str, dict[str, str]]:
    return {
        "CSV": {"ext": ".csv", "desc": tr("format.csv", "CSV")},
        "XLSX": {"ext": ".xlsx", "desc": tr("format.xlsx", "Excel")},
        "JSON": {"ext": ".json", "desc": tr("format.json", "JSON")},
    }
