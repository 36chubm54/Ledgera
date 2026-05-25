from __future__ import annotations

import sys
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Any

from domain.update import (
    AppUpdateReleaseInfo,
    PendingUpdateInstallState,
)
from gui.i18n import tr
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XS, create_card_section

from .support.update_flow import handle_update_check, show_update_download_dialog
from .support.update_support import (
    build_update_environment,
    install_ready_status_text,
    load_pending_update_install_state,
    pending_state_to_release,
    ready_status_text,
    resolve_release_page_url,
    should_enable_release_page_button,
)
from .support.wallets_support import MessageBoxLike


def build_update_section(
    parent_panel: tk.Frame | ttk.Frame,
    *,
    context: Any,
    messagebox_module: MessageBoxLike = messagebox,
    row_index: int = 0,
) -> None:
    pad_x = PAD_SM
    pad_y = PAD_XS
    environment = build_update_environment(context.controller, platform_name=sys.platform)
    current_version = environment.current_version
    release_page_url = environment.release_page_url
    can_check_updates = environment.can_check_updates
    latest_release_holder: dict[str, AppUpdateReleaseInfo | None] = {"value": None}
    pending_install_holder: dict[str, PendingUpdateInstallState | None] = {"value": None}
    update_flow_state = {"active": False}
    primary_button_text = tk.StringVar(
        value=tr("settings.updates.check_button", "Проверить обновления")
    )

    def _clear_pending_install_state() -> None:
        pending_install_holder["value"] = None
        context.controller.clear_pending_update_install_state()

    def _load_pending_install_state() -> PendingUpdateInstallState | None:
        return load_pending_update_install_state(
            context.controller,
            current_version=current_version,
        )

    def _set_primary_button_install_mode(enabled: bool) -> None:
        primary_button_text.set(
            tr(
                "settings.updates.install_button",
                "Установить обновление",
            )
            if enabled
            else tr("settings.updates.check_button", "Проверить обновления")
        )

    def _ready_status_text() -> str:
        return ready_status_text(environment)

    def _set_ready_status() -> None:
        status_var.set(_ready_status_text())

    status_var = tk.StringVar(value=_ready_status_text())

    update_card = create_card_section(
        parent_panel,
        tr("settings.updates.title", "Обновление приложения"),
    )
    update_card.grid(row=row_index, column=0, sticky="ew", pady=(0, PAD_LG))
    update_frame = update_card.winfo_children()[-1]
    update_frame.grid_columnconfigure(1, weight=1)

    ttk.Label(
        update_frame,
        text=tr("settings.updates.current_version", "Текущая версия:"),
        style="FormField.TLabel",
    ).grid(row=0, column=0, sticky="w", padx=pad_x, pady=pad_y)
    ttk.Label(
        update_frame,
        text=f"v{current_version}",
        style="FormField.TLabel",
    ).grid(row=0, column=1, sticky="w", padx=(0, pad_x), pady=pad_y)

    ttk.Label(
        update_frame,
        text=tr("settings.updates.status", "Статус:"),
        style="FormField.TLabel",
    ).grid(row=1, column=0, sticky="nw", padx=pad_x, pady=pad_y)
    status_label = ttk.Label(
        update_frame,
        textvariable=status_var,
        style="CardText.TLabel",
        justify="left",
        wraplength=520,
    )
    status_label.grid(row=1, column=1, sticky="ew", padx=(0, pad_x), pady=pad_y)

    def _set_update_flow_active(active: bool) -> None:
        update_flow_state["active"] = active
        if active:
            check_button.state(["disabled"])
        elif can_check_updates:
            check_button.state(["!disabled"])

    def _refresh_release_button_state() -> None:
        if not should_enable_release_page_button(
            environment=environment,
            update_flow_active=update_flow_state["active"],
            pending_state=pending_install_holder["value"],
            release=latest_release_holder["value"],
            release_page_url=release_page_url,
        ):
            release_link_button.state(["disabled"])
            return
        release_link_button.state(["!disabled"])

    def _set_pending_install_state(state: PendingUpdateInstallState | None) -> None:
        pending_install_holder["value"] = state
        _set_primary_button_install_mode(state is not None)
        if state is not None:
            status_var.set(install_ready_status_text(state.version))
        _refresh_release_button_state()

    def _open_release_page() -> None:
        target_url = resolve_release_page_url(
            pending_state=pending_install_holder["value"],
            release=latest_release_holder["value"],
            release_page_url=release_page_url,
        )
        if not target_url:
            return
        webbrowser.open(target_url)

    def _show_download_dialog(release: AppUpdateReleaseInfo) -> None:
        show_update_download_dialog(
            parent_panel=parent_panel,
            context=context,
            messagebox_module=messagebox_module,
            release=release,
            release_page_url=release_page_url,
            set_update_flow_active=_set_update_flow_active,
            set_pending_install_state=_set_pending_install_state,
            set_status=status_var.set,
            refresh_release_button_state=_refresh_release_button_state,
            open_url=webbrowser.open,
        )

    def _on_check_updates() -> None:
        handle_update_check(
            context=context,
            messagebox_module=messagebox_module,
            current_version=current_version,
            release_page_url=release_page_url,
            update_flow_active=update_flow_state["active"],
            pending_state=pending_install_holder["value"],
            clear_pending_install_state=_clear_pending_install_state,
            set_ready_status=_set_ready_status,
            refresh_release_button_state=_refresh_release_button_state,
            set_update_flow_active=_set_update_flow_active,
            set_status=status_var.set,
            latest_release_holder=latest_release_holder,
            show_download_dialog=_show_download_dialog,
            open_url=webbrowser.open,
        )

    buttons = ttk.Frame(update_frame, style="Card.TFrame")
    buttons.grid(row=2, column=0, columnspan=2, sticky="ew", padx=pad_x, pady=(PAD_SM, 0))
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)

    check_button = ttk.Button(
        buttons,
        textvariable=primary_button_text,
        style="Primary.TButton",
        command=_on_check_updates,
    )
    check_button.grid(row=0, column=0, sticky="ew", padx=(0, PAD_XS))
    if not can_check_updates:
        check_button.state(["disabled"])

    release_link_button = ttk.Button(
        buttons,
        text=tr("settings.updates.release_page", "Страница релиза"),
        command=_open_release_page,
    )
    release_link_button.grid(row=0, column=1, sticky="ew", padx=(PAD_XS, 0))
    pending_state = _load_pending_install_state()
    if pending_state is not None:
        latest_release_holder["value"] = pending_state_to_release(
            pending_state,
            release_page_url=release_page_url,
        )
    _set_pending_install_state(pending_state)
    if pending_state is None:
        _refresh_release_button_state()
