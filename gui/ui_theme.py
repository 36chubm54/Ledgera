from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Literal

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
    palette = get_palette(theme)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root["background"] = palette.background
    root.option_add("*Font", (FONT_FAMILY, FONT_SIZE))
    root.option_add("*TCombobox*Listbox.font", (FONT_FAMILY, FONT_SIZE))
    root.option_add("*TCombobox*Listbox.background", palette.surface_elevated)
    root.option_add("*TCombobox*Listbox.foreground", palette.text_primary)
    root.option_add("*TCombobox*Listbox.selectBackground", palette.accent_blue)
    root.option_add("*TCombobox*Listbox.selectForeground", palette.surface_elevated)
    root.option_add("*Listbox.background", palette.surface_elevated)
    root.option_add("*Listbox.foreground", palette.text_primary)
    root.option_add("*Listbox.selectBackground", palette.accent_blue)
    root.option_add("*Listbox.selectForeground", palette.surface_elevated)
    root.option_add("*Menu.background", palette.surface_elevated)
    root.option_add("*Menu.foreground", palette.text_primary)
    root.option_add("*Menu.activeBackground", palette.surface_alt)
    root.option_add("*Menu.activeForeground", palette.text_primary)
    root.option_add("*Menu.borderWidth", 0)

    style.configure(".", font=(FONT_FAMILY, FONT_SIZE))
    style.configure("TFrame", background=palette.background)
    style.configure(
        "TLabelframe",
        background=palette.surface,
        borderwidth=1,
        relief="flat",
        bordercolor=palette.border_section,
        lightcolor=palette.surface,
        darkcolor=palette.surface,
    )
    style.configure(
        "TLabelframe.Label",
        font=SECTION_FONT,
        foreground=palette.text_muted,
        background=palette.background,
        padding=(0, 0, 0, 4),
    )
    style.configure("TLabel", background=palette.background, foreground=palette.text_primary)
    style.configure(
        "Section.TLabel",
        font=HEADING_FONT,
        foreground=palette.text_primary,
        background=palette.background,
    )
    style.configure("Subtle.TLabel", foreground=palette.text_muted, background=palette.background)
    style.configure(
        "Metric.TLabel",
        font=METRIC_FONT,
        foreground=palette.text_primary,
        background=palette.background,
    )
    style.configure(
        "Card.TFrame",
        background=palette.surface_form,
        borderwidth=1,
        relief="flat",
        bordercolor=palette.border_section,
        lightcolor=palette.surface_form,
        darkcolor=palette.surface_form,
    )
    style.configure("CardBody.TFrame", background=palette.surface_form)
    style.configure(
        "CardTitle.TLabel",
        font=SECTION_FONT,
        foreground=palette.text_muted,
        background=palette.surface_form,
        padding=(0, 0, 0, 6),
    )
    style.configure(
        "CardText.TLabel", background=palette.surface_form, foreground=palette.text_primary
    )
    style.configure(
        "CardSubtle.TLabel", background=palette.surface_form, foreground=palette.text_muted
    )
    style.configure(
        "FormField.TLabel",
        background=palette.surface_form,
        foreground=palette.text_primary,
    )
    style.configure("SectionDivider.TSeparator", background=palette.border_section)
    style.configure(
        "StatusMuted.TLabel", foreground=palette.text_muted, background=palette.background
    )
    style.configure(
        "StatusSuccess.TLabel", foreground=palette.success, background=palette.background
    )
    style.configure(
        "StatusWarning.TLabel", foreground=palette.warning, background=palette.background
    )
    style.configure("StatusDanger.TLabel", foreground=palette.danger, background=palette.background)

    style.configure(
        "TButton",
        padding=(8, 5),
        background=palette.surface_elevated,
        foreground=palette.text_primary,
        borderwidth=0,
        relief="flat",
        focusthickness=0,
        bordercolor=palette.border_soft,
    )
    style.map(
        "TButton",
        background=[("active", palette.surface_alt), ("pressed", palette.surface_alt)],
        relief=[("!disabled", "flat")],
        foreground=[("disabled", palette.text_muted)],
    )
    style.configure(
        "Primary.TButton",
        padding=(12, 7),
        background=palette.accent_blue,
        foreground=palette.surface_elevated,
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", palette.accent_blue_hover),
            ("pressed", palette.accent_blue_active),
            ("!disabled", palette.accent_blue),
        ],
        foreground=[("!disabled", palette.surface_elevated)],
    )
    style.configure(
        "TMenubutton",
        padding=(8, 5),
        background=palette.surface_elevated,
        foreground=palette.text_primary,
        borderwidth=1,
        relief="flat",
        arrowcolor=palette.text_muted,
    )
    style.map(
        "TMenubutton",
        background=[("active", palette.surface_alt), ("pressed", palette.surface_alt)],
        bordercolor=[("!disabled", palette.border_soft)],
    )

    style.configure(
        "TEntry",
        padding=(6, 5),
        fieldbackground=palette.surface_elevated,
        foreground=palette.text_primary,
        insertcolor=palette.text_primary,
        bordercolor=palette.border_section,
        lightcolor=palette.border_section,
        darkcolor=palette.border_section,
        selectbackground=palette.accent_blue,
        selectforeground=palette.surface_elevated,
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", palette.accent_blue)],
        lightcolor=[("focus", palette.accent_blue)],
        darkcolor=[("focus", palette.accent_blue)],
        fieldbackground=[("focus", palette.surface_elevated)],
    )
    style.configure(
        "TCombobox",
        padding=(6, 5),
        fieldbackground=palette.surface_elevated,
        background=palette.surface_elevated,
        foreground=palette.text_primary,
        arrowcolor=palette.text_muted,
        bordercolor=palette.border_section,
        lightcolor=palette.border_section,
        darkcolor=palette.border_section,
        arrowsize=14,
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", palette.surface_elevated),
            ("focus readonly", palette.surface_elevated),
            ("active readonly", palette.surface_elevated),
        ],
        background=[
            ("readonly", palette.surface_elevated),
            ("focus readonly", palette.surface_elevated),
            ("active readonly", palette.surface_elevated),
        ],
        foreground=[
            ("readonly", palette.text_primary),
            ("focus readonly", palette.text_primary),
            ("active readonly", palette.text_primary),
        ],
        selectbackground=[("readonly", palette.surface_elevated)],
        selectforeground=[("readonly", palette.text_primary)],
        bordercolor=[("focus", palette.accent_blue)],
        lightcolor=[("focus", palette.accent_blue)],
        darkcolor=[("focus", palette.accent_blue)],
        arrowcolor=[("disabled", palette.text_muted), ("!disabled", palette.text_muted)],
    )
    style.configure(
        "StatusBar.TCombobox",
        padding=(3, 2),
        fieldbackground=palette.surface_elevated,
        background=palette.surface_elevated,
        foreground=palette.text_primary,
        arrowcolor=palette.text_muted,
        bordercolor=palette.border_soft,
        arrowsize=12,
    )
    style.map(
        "StatusBar.TCombobox",
        fieldbackground=[
            ("readonly", palette.surface_elevated),
            ("focus readonly", palette.surface_elevated),
            ("active readonly", palette.surface_elevated),
        ],
        background=[
            ("readonly", palette.surface_elevated),
            ("focus readonly", palette.surface_elevated),
            ("active readonly", palette.surface_elevated),
        ],
        foreground=[
            ("readonly", palette.text_primary),
            ("focus readonly", palette.text_primary),
            ("active readonly", palette.text_primary),
        ],
        selectbackground=[("readonly", palette.surface_elevated)],
        selectforeground=[("readonly", palette.text_primary)],
        bordercolor=[("focus", palette.accent_blue)],
        lightcolor=[("focus", palette.accent_blue)],
        darkcolor=[("focus", palette.accent_blue)],
        arrowcolor=[("disabled", palette.text_muted), ("!disabled", palette.text_muted)],
    )

    style.configure(
        "TCheckbutton",
        background=palette.background,
        foreground=palette.text_primary,
        indicatorbackground=palette.surface_elevated,
        indicatorforeground=palette.accent_blue,
        indicatormargin=4,
        focuscolor=palette.background,
    )
    style.map(
        "TCheckbutton",
        background=[("active", palette.background), ("pressed", palette.background)],
        foreground=[("active", palette.text_primary), ("pressed", palette.text_primary)],
        indicatorbackground=[
            ("selected", palette.accent_blue),
            ("active", palette.surface_alt),
            ("pressed", palette.surface_alt),
        ],
        indicatorforeground=[("selected", palette.surface_elevated)],
    )
    style.configure(
        "FormField.TCheckbutton",
        background=palette.surface_form,
        foreground=palette.text_primary,
        indicatorbackground=palette.surface_elevated,
        indicatorforeground=palette.accent_blue,
        indicatormargin=4,
        focuscolor=palette.surface_form,
    )
    style.map(
        "FormField.TCheckbutton",
        background=[("active", palette.surface_form), ("pressed", palette.surface_form)],
        foreground=[("active", palette.text_primary), ("pressed", palette.text_primary)],
        indicatorbackground=[
            ("selected", palette.accent_blue),
            ("active", palette.surface_alt),
            ("pressed", palette.surface_alt),
        ],
        indicatorforeground=[("selected", palette.surface_elevated)],
    )
    style.configure(
        "TRadiobutton",
        background=palette.background,
        foreground=palette.text_primary,
        indicatorbackground=palette.surface_elevated,
        indicatorforeground=palette.accent_blue,
        indicatormargin=4,
        focuscolor=palette.background,
    )
    style.map(
        "TRadiobutton",
        background=[("active", palette.background), ("pressed", palette.background)],
        foreground=[("active", palette.text_primary), ("pressed", palette.text_primary)],
        indicatorbackground=[
            ("selected", palette.accent_blue),
            ("active", palette.surface_alt),
            ("pressed", palette.surface_alt),
        ],
        indicatorforeground=[("selected", palette.surface_elevated)],
    )

    for scrollbar_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            scrollbar_style,
            troughcolor=palette.surface_alt,
            background=palette.surface,
            arrowcolor=palette.text_muted,
            bordercolor=palette.border_soft,
            lightcolor=palette.surface_alt,
            darkcolor=palette.surface_alt,
            gripcount=0,
            arrowsize=12,
        )
        style.map(
            scrollbar_style,
            background=[("active", palette.surface_elevated), ("pressed", palette.surface)],
        )

    style.configure(
        "Treeview",
        rowheight=28,
        font=(FONT_FAMILY, FONT_SIZE),
        fieldbackground=palette.surface_elevated,
        background=palette.surface_elevated,
        foreground=palette.text_primary,
        bordercolor=palette.border_section,
        lightcolor=palette.surface_elevated,
        darkcolor=palette.surface_elevated,
        borderwidth=0,
    )
    style.map(
        "Treeview",
        background=[
            ("disabled", palette.surface_elevated),
            ("selected", palette.surface_alt),
        ],
        foreground=[
            ("disabled", palette.text_muted),
            ("selected", palette.text_primary),
        ],
    )
    style.configure(
        "Treeview.Heading",
        font=(FONT_FAMILY, 9, "bold"),
        padding=(10, 7),
        background=palette.surface_alt,
        foreground=palette.text_muted,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", palette.surface), ("pressed", palette.surface_alt)],
        foreground=[("active", palette.text_primary), ("pressed", palette.text_primary)],
        bordercolor=[("active", palette.border_soft), ("pressed", palette.accent_blue)],
        lightcolor=[("active", palette.surface), ("pressed", palette.surface_alt)],
        darkcolor=[("active", palette.surface), ("pressed", palette.surface_alt)],
    )

    style.configure(
        "TNotebook",
        background=palette.background,
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        padding=(14, 8),
        font=(FONT_FAMILY, FONT_SIZE),
        background=palette.background,
        foreground=palette.text_muted,
        borderwidth=0,
        focusthickness=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", palette.background), ("active", palette.surface)],
        foreground=[("selected", palette.text_primary), ("active", palette.text_primary)],
    )

    for paned_style in ("TPanedwindow", "Reports.TPanedwindow"):
        style.configure(
            paned_style,
            background=palette.background,
            borderwidth=0,
            sashthickness=10,
            relief="flat",
            sashrelief="flat",
            gripcount=0,
            handlesize=0,
        )

    style.configure(
        "StatusBar.TFrame",
        background=palette.surface_elevated,
        borderwidth=1,
        relief="flat",
        bordercolor=palette.border_soft,
        lightcolor=palette.surface_elevated,
        darkcolor=palette.surface_elevated,
    )
    style.configure(
        "StatusBar.TLabel",
        background=palette.surface_elevated,
        foreground=palette.text_primary,
        padding=(0, 0, 0, 0),
    )
    style.configure(
        "StatusBarMuted.TLabel",
        background=palette.surface_elevated,
        foreground=palette.text_muted,
    )
    style.configure("StatusBar.TSeparator", background=palette.border_section)
    style.configure(
        "StatusBar.TCheckbutton",
        background=palette.surface_elevated,
        foreground=palette.text_primary,
        indicatorbackground=palette.surface_elevated,
        indicatorforeground=palette.accent_blue,
        focuscolor=palette.surface_elevated,
    )
    style.map(
        "StatusBar.TCheckbutton",
        background=[("active", palette.surface_elevated), ("pressed", palette.surface_elevated)],
        foreground=[("active", palette.text_primary), ("pressed", palette.text_primary)],
        indicatorbackground=[
            ("selected", palette.accent_blue),
            ("active", palette.surface_alt),
            ("pressed", palette.surface_alt),
        ],
        indicatorforeground=[("selected", palette.surface_elevated)],
    )
    style.configure(
        "StatusBar.TButton",
        background=palette.surface_elevated,
        foreground=palette.text_muted,
        relief="flat",
        padding=(7, 2),
        font=("", 9),
        borderwidth=0,
    )
    style.map(
        "StatusBar.TButton",
        background=[("active", palette.surface_alt)],
        foreground=[("active", palette.text_primary)],
    )
    style.configure(
        "InlinePanel.TFrame",
        background=palette.inline_accent_bg,
        borderwidth=1,
        relief="flat",
        bordercolor=palette.inline_accent_border,
        lightcolor=palette.inline_accent_bg,
        darkcolor=palette.inline_accent_bg,
    )
    style.configure(
        "InlineField.TLabel",
        background=palette.inline_accent_bg,
        foreground=palette.text_primary,
    )
    style.configure(
        "InlineField.TCheckbutton",
        background=palette.inline_accent_bg,
        foreground=palette.text_primary,
        indicatorbackground=palette.surface_elevated,
        indicatorforeground=palette.accent_blue,
        indicatormargin=4,
        focuscolor=palette.inline_accent_bg,
    )
    style.map(
        "InlineField.TCheckbutton",
        background=[("active", palette.inline_accent_bg), ("pressed", palette.inline_accent_bg)],
        foreground=[("active", palette.text_primary), ("pressed", palette.text_primary)],
        indicatorbackground=[
            ("selected", palette.accent_blue),
            ("active", palette.surface_alt),
            ("pressed", palette.surface_alt),
        ],
        indicatorforeground=[("selected", palette.surface_elevated)],
    )
    style.configure(
        "TProgressbar",
        troughcolor=palette.surface_alt,
        background=palette.accent_blue,
        borderwidth=0,
    )
    _apply_canvas_theme(root, palette)
    _apply_treeview_theme(root, palette)
    _apply_combobox_popdown_theme(root, palette)
    return style


def create_card_section(
    parent: tk.Misc,
    title: str,
    *,
    body_padding: tuple[int, int, int, int] = (PAD_MD, PAD_MD, PAD_MD, PAD_MD),
) -> ttk.Frame:
    card = ttk.Frame(parent, style="Card.TFrame", padding=body_padding)
    card.grid_columnconfigure(0, weight=1)
    ttk.Label(card, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="ew")
    ttk.Separator(card, orient=tk.HORIZONTAL, style="SectionDivider.TSeparator").grid(
        row=1, column=0, sticky="ew", pady=(0, PAD_MD)
    )
    body = ttk.Frame(card, style="CardBody.TFrame")
    body.grid(row=2, column=0, sticky="nsew")
    card.grid_rowconfigure(2, weight=1)
    body.grid_columnconfigure(0, weight=1)
    return card


def _sync_treeview_row_tags(tree: ttk.Treeview) -> None:
    selection = set(tree.selection())
    for index, iid in enumerate(tree.get_children("")):
        current_tags = tuple(str(tag) for tag in tree.item(iid, "tags"))
        base_tags = tuple(tag for tag in current_tags if tag not in {"alt", "alt_selected"})
        zebra_tag = "alt_selected" if iid in selection and index % 2 else "alt" if index % 2 else ""
        if zebra_tag:
            tree.item(iid, tags=base_tags + (zebra_tag,))
        else:
            tree.item(iid, tags=base_tags)


def refresh_treeview_zebra(tree: ttk.Treeview) -> None:
    palette = get_palette()
    tree.tag_configure("alt", background=palette.row_alt)
    tree.tag_configure(
        "alt_selected",
        background=palette.surface_alt,
    )
    _sync_treeview_row_tags(tree)


def _schedule_treeview_zebra_refresh(tree: ttk.Treeview) -> None:
    if bool(getattr(tree, "_zebra_refresh_pending", False)):
        return
    setattr(tree, "_zebra_refresh_pending", True)  # noqa: B010

    def _run() -> None:
        setattr(tree, "_zebra_refresh_pending", False)  # noqa: B010
        if bool(tree.winfo_exists()):
            _sync_treeview_row_tags(tree)

    tree.after_idle(_run)


def enable_treeview_zebra(tree: ttk.Treeview) -> ttk.Treeview:
    if bool(getattr(tree, "_zebra_enabled", False)):
        refresh_treeview_zebra(tree)
        return tree

    palette = get_palette()
    tree.tag_configure("alt", background=palette.row_alt)
    tree.tag_configure(
        "alt_selected",
        background=palette.surface_alt,
    )
    original_insert = tree.insert
    original_delete = tree.delete
    original_move = tree.move

    def _insert(
        parent: str, index: int | Literal["end"], iid: str | int | None = None, **kw: Any
    ) -> str:
        item_id = original_insert(parent, index, iid=iid, **kw)
        _schedule_treeview_zebra_refresh(tree)
        return item_id

    def _delete(*items: str) -> None:
        original_delete(*items)
        _schedule_treeview_zebra_refresh(tree)

    def _move(item: str, parent: str, index: int | Literal["end"]) -> None:
        original_move(item, parent, index)
        _schedule_treeview_zebra_refresh(tree)

    tree.insert = _insert  # type: ignore[assignment]
    tree.delete = _delete  # type: ignore[assignment]
    tree.move = _move  # type: ignore[assignment]
    tree.bind("<<TreeviewSelect>>", lambda _event: _schedule_treeview_zebra_refresh(tree), add="+")
    setattr(tree, "_zebra_enabled", True)  # noqa: B010
    _schedule_treeview_zebra_refresh(tree)
    return tree


def _apply_combobox_popdown_theme(root: tk.Misc, palette: ThemePalette) -> None:
    for widget in _walk_widgets(root):
        if isinstance(widget, ttk.Combobox):
            _configure_combobox_popdown(widget, palette)


def _apply_treeview_theme(root: tk.Misc, palette: ThemePalette) -> None:
    for widget in _walk_widgets(root):
        if isinstance(widget, ttk.Treeview):
            _configure_treeview_theme(widget, palette)


def _apply_canvas_theme(root: tk.Misc, palette: ThemePalette) -> None:
    for widget in _walk_widgets(root):
        if isinstance(widget, tk.Canvas):
            _configure_canvas_theme(widget, palette)


def _walk_widgets(root: tk.Misc) -> list[tk.Misc]:
    widgets: list[tk.Misc] = []
    for child in root.winfo_children():
        widgets.append(child)
        widgets.extend(_walk_widgets(child))
    return widgets


def _configure_combobox_popdown(widget: ttk.Combobox, palette: ThemePalette) -> None:
    try:
        popdown = str(widget.tk.eval(f"ttk::combobox::PopdownWindow {widget}"))
        listbox = f"{popdown}.f.l"
        widget.tk.call(
            listbox,
            "configure",
            "-background",
            palette.surface_elevated,
            "-foreground",
            palette.text_primary,
            "-selectbackground",
            palette.accent_blue,
            "-selectforeground",
            palette.surface_elevated,
            "-highlightthickness",
            0,
            "-borderwidth",
            0,
        )
    except tk.TclError:
        return


def _remap_theme_color(color: str, palette: ThemePalette) -> str:
    value = str(color or "").strip().lower()
    if not value:
        return color
    for source_palette in THEMES.values():
        if value == source_palette.background.lower():
            return palette.background
        if value == source_palette.surface.lower():
            return palette.surface
        if value == source_palette.surface_elevated.lower():
            return palette.surface_elevated
        if value == source_palette.surface_alt.lower():
            return palette.surface_alt
        if value == source_palette.surface_form.lower():
            return palette.surface_form
        if value == source_palette.border_soft.lower():
            return palette.border_soft
        if value == source_palette.border_section.lower():
            return palette.border_section
        if value == source_palette.row_alt.lower():
            return palette.row_alt
        if value == source_palette.inline_accent_bg.lower():
            return palette.inline_accent_bg
        if value == source_palette.success_tint.lower():
            return palette.success_tint
        if value == source_palette.warning_tint.lower():
            return palette.warning_tint
        if value == source_palette.danger_tint.lower():
            return palette.danger_tint
    return color


def _configure_canvas_theme(canvas: tk.Canvas, palette: ThemePalette) -> None:
    try:
        current_bg = str(canvas.cget("bg"))
        current_highlight = str(canvas.cget("highlightbackground"))
        current_border = str(canvas.cget("highlightcolor"))
        new_bg = _remap_theme_color(current_bg, palette)
        new_highlight = _remap_theme_color(current_highlight, palette)
        new_border = _remap_theme_color(current_border, palette)
        canvas.configure(
            bg=new_bg,
            highlightbackground=new_highlight,
            highlightcolor=new_border,
        )
    except tk.TclError:
        return


def _configure_treeview_theme(tree: ttk.Treeview, palette: ThemePalette) -> None:
    try:
        tree.tag_configure("alt", background=palette.row_alt)
        tree.tag_configure(
            "alt_selected",
            background=palette.surface_alt,
        )
        tree.tag_configure("positive", foreground=palette.chart_income)
        tree.tag_configure("negative", foreground=palette.chart_expense)
        tree.tag_configure("overspent", foreground=palette.danger)
        tree.tag_configure("overpace", foreground=palette.warning)
        tree.tag_configure("on_track", foreground=palette.success)
        tree.tag_configure("future", foreground=palette.text_muted)
        tree.tag_configure("expired", foreground=palette.text_muted)
        tree.tag_configure("writeoff", foreground=palette.text_muted)
        tree.tag_configure(
            "group_header",
            foreground=palette.accent_blue,
            background=palette.surface_elevated,
            font=(FONT_FAMILY, 9, "bold"),
        )
        tree.tag_configure(
            "item",
            foreground=palette.text_primary,
            background=palette.surface_elevated,
        )
        tree.tag_configure(
            "subitem",
            foreground=palette.accent_blue,
            background=palette.surface_elevated,
        )
        tree.tag_configure(
            "neg_row",
            background=palette.danger_tint,
            foreground=palette.text_primary,
        )
        tree.tag_configure(
            "odd_row",
            background=palette.row_alt,
            foreground=palette.text_primary,
        )
        tree.tag_configure(
            "even_row",
            background=palette.surface_elevated,
            foreground=palette.text_primary,
        )
        refresh_treeview_zebra(tree)
    except tk.TclError:
        return
