from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from gui.ui.theme_bootstrap import apply_ttk_theme
from gui.ui.theme_layout import (
    create_card_section as build_card_section,
)
from gui.ui.theme_layout import (
    enable_treeview_zebra as attach_treeview_zebra,
)
from gui.ui.theme_layout import (
    refresh_treeview_zebra as repaint_treeview_zebra,
)

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 10
MICRO_FONT = (FONT_FAMILY, 9)
LABEL_FONT = (FONT_FAMILY, 10)
HEADING_FONT = (FONT_FAMILY, 11, "bold")
SECTION_FONT = (FONT_FAMILY, 10, "bold")
METRIC_FONT = (FONT_FAMILY, 13, "bold")
PAD_XS = 4
PAD_SM = 8
PAD_MD = 12
PAD_LG = 16
PAD_XL = 20
DEFAULT_THEME = "light"


@dataclass(frozen=True)
class ThemePalette:
    name: str
    background: str
    surface: str
    surface_elevated: str
    surface_alt: str
    border_soft: str
    text_primary: str
    text_muted: str
    accent_blue: str
    accent_blue_hover: str
    accent_blue_active: str
    row_alt: str
    tab_underline: str
    surface_form: str
    border_section: str
    inline_accent_bg: str
    inline_accent_border: str
    success: str
    warning: str
    danger: str
    success_tint: str
    warning_tint: str
    danger_tint: str
    chart_grid: str
    chart_axis: str
    chart_empty: str
    chart_text: str
    chart_income: str
    chart_expense: str
    chart_outline: str
    chart_series: tuple[str, ...]


THEMES: dict[str, ThemePalette] = {
    "light": ThemePalette(
        name="light",
        background="#eef4fb",
        surface="#f9fbff",
        surface_elevated="#ffffff",
        surface_alt="#f2f7ff",
        border_soft="#d8e3f2",
        text_primary="#213247",
        text_muted="#6b7f99",
        accent_blue="#2f6fed",
        accent_blue_hover="#5a8df2",
        accent_blue_active="#2459c9",
        row_alt="#f5f9ff",
        tab_underline="#2f6fed",
        surface_form="#f5f8fe",
        border_section="#e4ecf7",
        inline_accent_bg="#f0f5ff",
        inline_accent_border="#c5d8f7",
        success="#2d7d6c",
        warning="#b6842f",
        danger="#b96a73",
        success_tint="#e8f6f1",
        warning_tint="#fcf5e6",
        danger_tint="#f9e9ec",
        chart_grid="#d1d5db",
        chart_axis="#d1d5db",
        chart_empty="#6b7280",
        chart_text="#1f2937",
        chart_income="#10b981",
        chart_expense="#ef4444",
        chart_outline="#ffffff",
        chart_series=(
            "#4f46e5",
            "#06b6d4",
            "#f59e0b",
            "#10b981",
            "#ec4899",
            "#8b5cf6",
            "#14b8a6",
            "#ef4444",
            "#f97316",
            "#22c55e",
            "#0ea5e9",
            "#a855f7",
        ),
    ),
    "dark": ThemePalette(
        name="dark",
        background="#0f1727",
        surface="#162033",
        surface_elevated="#1b2740",
        surface_alt="#22304d",
        border_soft="#31415f",
        text_primary="#edf4ff",
        text_muted="#9db0cc",
        accent_blue="#67a2ff",
        accent_blue_hover="#7eb1ff",
        accent_blue_active="#4f8df0",
        row_alt="#182338",
        tab_underline="#67a2ff",
        surface_form="#1d2b44",
        border_section="#2a3a58",
        inline_accent_bg="#1e2f4a",
        inline_accent_border="#3a5070",
        success="#43b99d",
        warning="#d8ab4a",
        danger="#d98896",
        success_tint="#15352f",
        warning_tint="#3a301c",
        danger_tint="#40242d",
        chart_grid="#31415f",
        chart_axis="#40516f",
        chart_empty="#9db0cc",
        chart_text="#edf4ff",
        chart_income="#37d0a0",
        chart_expense="#ff7a88",
        chart_outline="#162033",
        chart_series=(
            "#76a7ff",
            "#36c4e0",
            "#f7b955",
            "#46d39a",
            "#ff86c4",
            "#a68bff",
            "#31d1c4",
            "#ff7a88",
            "#ff9f57",
            "#71d765",
            "#42bbff",
            "#cb7dff",
        ),
    ),
}

_current_theme = DEFAULT_THEME

BACKGROUND = THEMES[DEFAULT_THEME].background
SURFACE = THEMES[DEFAULT_THEME].surface
SURFACE_ELEVATED = THEMES[DEFAULT_THEME].surface_elevated
SURFACE_ALT = THEMES[DEFAULT_THEME].surface_alt
BORDER_SOFT = THEMES[DEFAULT_THEME].border_soft
TEXT_PRIMARY = THEMES[DEFAULT_THEME].text_primary
TEXT_MUTED = THEMES[DEFAULT_THEME].text_muted
ACCENT_BLUE = THEMES[DEFAULT_THEME].accent_blue
ACCENT_BLUE_HOVER = THEMES[DEFAULT_THEME].accent_blue_hover
ACCENT_BLUE_ACTIVE = THEMES[DEFAULT_THEME].accent_blue_active
ROW_ALT = THEMES[DEFAULT_THEME].row_alt
SUBTLE_TEXT = THEMES[DEFAULT_THEME].text_muted
PRIMARY = THEMES[DEFAULT_THEME].accent_blue
SUCCESS = THEMES[DEFAULT_THEME].success
WARNING = THEMES[DEFAULT_THEME].warning
DANGER = THEMES[DEFAULT_THEME].danger


def get_theme() -> str:
    return _current_theme


def get_palette(theme_name: str | None = None) -> ThemePalette:
    normalized = str(theme_name or _current_theme or DEFAULT_THEME).strip().lower() or DEFAULT_THEME
    return THEMES.get(normalized, THEMES[DEFAULT_THEME])


def _sync_compat_globals(palette: ThemePalette) -> None:
    global BACKGROUND
    global SURFACE
    global SURFACE_ELEVATED
    global SURFACE_ALT
    global BORDER_SOFT
    global TEXT_PRIMARY
    global TEXT_MUTED
    global ACCENT_BLUE
    global ACCENT_BLUE_HOVER
    global ACCENT_BLUE_ACTIVE
    global ROW_ALT
    global SUBTLE_TEXT
    global PRIMARY
    global SUCCESS
    global WARNING
    global DANGER

    BACKGROUND = palette.background
    SURFACE = palette.surface
    SURFACE_ELEVATED = palette.surface_elevated
    SURFACE_ALT = palette.surface_alt
    BORDER_SOFT = palette.border_soft
    TEXT_PRIMARY = palette.text_primary
    TEXT_MUTED = palette.text_muted
    ACCENT_BLUE = palette.accent_blue
    ACCENT_BLUE_HOVER = palette.accent_blue_hover
    ACCENT_BLUE_ACTIVE = palette.accent_blue_active
    ROW_ALT = palette.row_alt
    SUBTLE_TEXT = palette.text_muted
    PRIMARY = palette.accent_blue
    SUCCESS = palette.success
    WARNING = palette.warning
    DANGER = palette.danger


def set_theme(name: str) -> str:
    global _current_theme
    normalized = str(name or "").strip().lower() or DEFAULT_THEME
    if normalized not in THEMES:
        normalized = DEFAULT_THEME
    _current_theme = normalized
    _sync_compat_globals(THEMES[_current_theme])
    return _current_theme


def bootstrap_ui(root: tk.Misc, theme_name: str | None = None) -> ttk.Style:
    theme = set_theme(theme_name or _current_theme)
    return apply_ttk_theme(
        root,
        palette=get_palette(theme),
        known_palettes=THEMES.values(),
        refresh_treeview_zebra=refresh_treeview_zebra,
        font_family=FONT_FAMILY,
        font_size=FONT_SIZE,
        heading_font=HEADING_FONT,
        section_font=SECTION_FONT,
        metric_font=METRIC_FONT,
    )


def create_card_section(
    parent: tk.Misc,
    title: str,
    *,
    body_padding: tuple[int, int, int, int] = (PAD_MD, PAD_MD, PAD_MD, PAD_MD),
) -> ttk.Frame:
    return build_card_section(parent, title, pad_md=PAD_MD, body_padding=body_padding)


def refresh_treeview_zebra(tree: ttk.Treeview) -> None:
    repaint_treeview_zebra(tree, get_palette=get_palette)


def enable_treeview_zebra(tree: ttk.Treeview) -> ttk.Treeview:
    return attach_treeview_zebra(tree, get_palette=get_palette)
