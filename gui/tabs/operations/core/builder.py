"""Operations tab builder."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, ttk

from gui.ui_theme import PAD_LG, PAD_SM, PAD_XL

from ..support.flows import (
    delete_all_flow,
    delete_selected_flow,
    export_records_flow,
    import_records_flow,
)
from .contracts import OperationsTabBindings, OperationsTabContext
from .form_section import build_operation_form_section
from .import_dialog import show_import_preview_dialog
from .inline_editors import InlineEditors, build_inline_editors
from .journal_section import JournalSection, build_journal_section
from .refresh import refresh_operation_views
from .transfer_section import build_transfer_section

logger = logging.getLogger(__name__)


def build_operations_tab(
    parent: tk.Frame | ttk.Frame,
    context: OperationsTabContext,
    import_formats: dict[str, dict[str, str]],
) -> OperationsTabBindings:
    parent.grid_columnconfigure(0, weight=2, uniform="operations")
    parent.grid_columnconfigure(1, weight=5, uniform="operations")
    parent.grid_rowconfigure(0, weight=1)

    left_frame = ttk.Frame(parent)
    left_frame.grid(row=0, column=0, sticky="nsew", padx=(PAD_XL, PAD_SM), pady=PAD_LG)
    left_frame.grid_columnconfigure(0, weight=1)
    left_frame.grid_rowconfigure(0, weight=1)

    paned = ttk.PanedWindow(left_frame, orient=tk.VERTICAL)
    paned.grid(row=0, column=0, sticky="nsew")

    def _refresh_after_mutation() -> None:
        refresh_operation_views(context)
        form_section.refresh_category_combo()

    form_section = build_operation_form_section(
        paned,
        context=context,
        logger=logger,
        on_saved=_refresh_after_mutation,
    )

    inline_editors: InlineEditors | None = None
    journal_section: JournalSection

    def delete_selected() -> None:
        delete_selected_flow(
            context=context,
            records_tree=journal_section.records_tree,
            refresh_after_mutation=_refresh_after_mutation,
        )

    def edit_selected_record_inline() -> None:
        if inline_editors is None:
            return
        inline_editors.edit_selected_record_inline()

    def delete_all() -> None:
        delete_all_flow(
            context=context,
            refresh_after_mutation=_refresh_after_mutation,
        )

    def import_records_data() -> None:
        import_records_flow(
            parent=parent,
            context=context,
            import_formats=import_formats,
            format_name=journal_section.import_format_var.get(),
            mode_label=journal_section.import_mode_label_var.get(),
            show_import_preview_dialog=show_import_preview_dialog,
            refresh_after_mutation=_refresh_after_mutation,
        )

    def export_records_data() -> None:
        export_records_flow(
            context=context,
            import_formats=import_formats,
            format_name=journal_section.import_format_var.get(),
            asksaveasfilename=filedialog.asksaveasfilename,
        )

    format_options = [
        format_name for format_name in ("CSV", "XLSX") if format_name in import_formats
    ]

    journal_section = build_journal_section(
        parent,
        format_options=format_options,
        on_delete_selected=delete_selected,
        on_edit_selected=edit_selected_record_inline,
        on_refresh_list=context._refresh_list,
        on_delete_all=delete_all,
        on_import=import_records_data,
        on_export=export_records_data,
    )

    transfer_section = build_transfer_section(
        paned,
        context=context,
        logger=logger,
        base_currency_code=form_section.base_currency_code,
        on_saved=_refresh_after_mutation,
    )

    inline_editors = build_inline_editors(
        list_frame=journal_section.list_frame,
        records_tree=journal_section.records_tree,
        context=context,
        logger=logger,
        refresh_category_combo=form_section.refresh_category_combo,
        sync_tag_color_from_input=form_section.sync_tag_color_from_input,
        base_currency_code=form_section.base_currency_code,
        is_kzt_currency=form_section.is_kzt_currency,
        amount_edit_label_text=form_section.amount_edit_label_text,
        amount_edit_tooltip_text=form_section.amount_edit_tooltip_text,
        after_update=_refresh_after_mutation,
    )

    context._refresh_list()

    return OperationsTabBindings(
        records_tree=journal_section.records_tree,
        tags_tree=journal_section.tags_tree,
        refresh_operation_wallet_menu=form_section.refresh_operation_wallet_menu,
        refresh_transfer_wallet_menus=transfer_section.refresh_transfer_wallet_menus,
        set_type_income=form_section.set_type_income,
        set_type_expense=form_section.set_type_expense,
        save_record=form_section.save_record,
        select_first=journal_section.select_first,
        select_last=journal_section.select_last,
        delete_selected=delete_selected,
        delete_all=delete_all,
        edit_selected=edit_selected_record_inline,
        inline_editor_active=inline_editors.inline_editor_active,
    )
