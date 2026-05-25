"""Analytics tab subpackage."""

from .core.builder import build_analytics_tab
from .core.contracts import AnalyticsTabBindings, AnalyticsTabContext
from .core.render import _draw_breakdown_pie, _draw_net_worth_line

__all__ = [
    "AnalyticsTabBindings",
    "AnalyticsTabContext",
    "build_analytics_tab",
    "_draw_breakdown_pie",
    "_draw_net_worth_line",
]
