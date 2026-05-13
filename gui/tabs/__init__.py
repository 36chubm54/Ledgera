from .analytics_tab import AnalyticsTabBindings, build_analytics_tab
from .budget_tab import BudgetTabBindings, build_budget_tab
from .dashboard_tab import DashboardTabBindings, build_dashboard_tab
from .debts_tab import DebtsTabBindings, build_debts_tab
from .distribution_tab import DistributionTabBindings, build_distribution_tab
from .infographics_tab import InfographicsTabBindings, build_infographics_tab
from .mandatory_tab import MandatoryTabBindings, build_mandatory_tab
from .operations_tab import OperationsTabBindings, build_operations_tab
from .reports_tab import build_reports_tab
from .settings_tab import build_settings_tab

__all__ = [
    "BudgetTabBindings",
    "DebtsTabBindings",
    "AnalyticsTabBindings",
    "DashboardTabBindings",
    "DistributionTabBindings",
    "InfographicsTabBindings",
    "MandatoryTabBindings",
    "OperationsTabBindings",
    "build_budget_tab",
    "build_debts_tab",
    "build_analytics_tab",
    "build_dashboard_tab",
    "build_distribution_tab",
    "build_infographics_tab",
    "build_mandatory_tab",
    "build_operations_tab",
    "build_reports_tab",
    "build_settings_tab",
]
