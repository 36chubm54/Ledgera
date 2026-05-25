from __future__ import annotations

import os
import tkinter as tk
from tkinter import scrolledtext, ttk

from domain.audit import AuditFinding, AuditReport
from gui.i18n import tr
from gui.ui_helpers import center_dialog
from gui.ui_theme import get_palette


def _format_audit_finding(finding: AuditFinding, *, passed: bool = False) -> str:
    suffix = f" — {finding.detail}" if finding.detail else ""
    prefix = "✔ " if passed else ""
    return f"{prefix}[{finding.check}] {finding.message}{suffix}"


def _populate_audit_section(
    widget: scrolledtext.ScrolledText,
    findings: tuple[AuditFinding, ...],
    *,
    passed: bool = False,
    background: str | None = None,
) -> None:
    palette = get_palette()
    effective_background = background or palette.surface_elevated
    widget.configure(
        background=effective_background,
        foreground=palette.text_primary,
        insertbackground=palette.text_primary,
        selectbackground=palette.accent_blue,
        selectforeground=palette.surface_elevated,
        highlightbackground=palette.border_soft,
        highlightcolor=palette.border_soft,
        relief="flat",
        borderwidth=1,
    )
    if background is not None:
        widget.configure(background=effective_background)
    widget.configure(state="normal")
    widget.delete("1.0", tk.END)
    if findings:
        lines = [_format_audit_finding(finding, passed=passed) for finding in findings]
        widget.insert("1.0", "\n".join(lines))
    else:
        widget.insert("1.0", tr("settings.audit.none", "(none)"))
    widget.configure(state="disabled")


def show_audit_report_dialog(report: AuditReport, parent: tk.Misc) -> None:
    palette = get_palette()
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(tr("settings.audit.report.title", "Отчет аудита"))
    dialog.minsize(560, 480)
    dialog.transient(parent.winfo_toplevel())
    dialog.configure(background=palette.background)
    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(0, weight=1)

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill="both", expand=True)
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_rowconfigure(3, weight=1)
    frame.grid_rowconfigure(4, weight=1)
    frame.grid_rowconfigure(5, weight=1)

    ttk.Label(
        frame,
        text=tr("settings.audit.db", "База данных: {name}", name=os.path.basename(report.db_path)),
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(frame, text=report.summary()).grid(row=1, column=0, sticky="w", pady=(4, 10))

    errors_frame = ttk.LabelFrame(
        frame,
        text=tr("settings.audit.errors", "Ошибки ({count})", count=len(report.errors)),
    )
    errors_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
    errors_frame.grid_columnconfigure(0, weight=1)
    errors_frame.grid_rowconfigure(0, weight=1)

    warnings_frame = ttk.LabelFrame(
        frame,
        text=tr(
            "settings.audit.warnings",
            "Предупреждения ({count})",
            count=len(report.warnings),
        ),
    )
    warnings_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 8))
    warnings_frame.grid_columnconfigure(0, weight=1)
    warnings_frame.grid_rowconfigure(0, weight=1)

    passed_frame = ttk.LabelFrame(
        frame,
        text=tr("settings.audit.passed", "Пройдено ({count})", count=len(report.passed)),
    )
    passed_frame.grid(row=5, column=0, sticky="nsew", pady=(0, 10))
    passed_frame.grid_columnconfigure(0, weight=1)
    passed_frame.grid_rowconfigure(0, weight=1)

    errors_text = scrolledtext.ScrolledText(errors_frame, height=7, wrap="word")
    errors_text.grid(row=0, column=0, sticky="nsew")
    warnings_text = scrolledtext.ScrolledText(warnings_frame, height=7, wrap="word")
    warnings_text.grid(row=0, column=0, sticky="nsew")
    passed_text = scrolledtext.ScrolledText(passed_frame, height=8, wrap="word")
    passed_text.grid(row=0, column=0, sticky="nsew")

    _populate_audit_section(
        errors_text,
        report.errors,
        background=palette.danger_tint if report.errors else None,
    )
    _populate_audit_section(
        warnings_text,
        report.warnings,
        background=palette.warning_tint if report.warnings else None,
    )
    _populate_audit_section(
        passed_text,
        report.passed,
        passed=True,
        background=palette.success_tint if report.is_clean else None,
    )

    close_button = ttk.Button(
        frame,
        text=tr("common.close", "Закрыть"),
        command=dialog.destroy,
    )
    close_button.grid(row=6, column=0, sticky="e")

    center_dialog(dialog, parent, min_width=560, min_height=480)
    dialog.deiconify()
    dialog.grab_set()
    close_button.focus_set()
