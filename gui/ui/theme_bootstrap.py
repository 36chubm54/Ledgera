from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from gui.ui.theme_widgets import apply_widget_theme_overrides


def apply_ttk_theme(
    root: tk.Misc,
    *,
    palette: Any,
    known_palettes: Any,
    refresh_treeview_zebra: Any,
    font_family: str,
    font_size: int,
    heading_font: tuple[Any, ...],
    section_font: tuple[Any, ...],
    metric_font: tuple[Any, ...],
) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root["background"] = palette.background
    root.option_add("*Font", (font_family, font_size))
    root.option_add("*TCombobox*Listbox.font", (font_family, font_size))
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

    style.configure(".", font=(font_family, font_size))
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
        font=section_font,
        foreground=palette.text_muted,
        background=palette.background,
        padding=(0, 0, 0, 4),
    )
    style.configure("TLabel", background=palette.background, foreground=palette.text_primary)
    style.configure(
        "Section.TLabel",
        font=heading_font,
        foreground=palette.text_primary,
        background=palette.background,
    )
    style.configure("Subtle.TLabel", foreground=palette.text_muted, background=palette.background)
    style.configure(
        "Metric.TLabel",
        font=metric_font,
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
        font=section_font,
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
        "FormField.TLabel", background=palette.surface_form, foreground=palette.text_primary
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

    for style_name, background in (
        ("TCheckbutton", palette.background),
        ("FormField.TCheckbutton", palette.surface_form),
        ("TRadiobutton", palette.background),
    ):
        style.configure(
            style_name,
            background=background,
            foreground=palette.text_primary,
            indicatorbackground=palette.surface_elevated,
            indicatorforeground=palette.accent_blue,
            indicatormargin=4,
            focuscolor=background,
        )
        style.map(
            style_name,
            background=[("active", background), ("pressed", background)],
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
        font=(font_family, font_size),
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
        background=[("disabled", palette.surface_elevated), ("selected", palette.surface_alt)],
        foreground=[("disabled", palette.text_muted), ("selected", palette.text_primary)],
    )
    style.configure(
        "Treeview.Heading",
        font=(font_family, 9, "bold"),
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
        "TNotebook", background=palette.background, borderwidth=0, tabmargins=(0, 0, 0, 0)
    )
    style.configure(
        "TNotebook.Tab",
        padding=(14, 8),
        font=(font_family, font_size),
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
        "StatusBarMuted.TLabel", background=palette.surface_elevated, foreground=palette.text_muted
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
        "InlineField.TLabel", background=palette.inline_accent_bg, foreground=palette.text_primary
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
    apply_widget_theme_overrides(
        root,
        palette,
        known_palettes=known_palettes,
        font_family=font_family,
        refresh_treeview_zebra=refresh_treeview_zebra,
    )
    return style
