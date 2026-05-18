from __future__ import annotations

import queue
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Any

from domain.update import AppUpdateCheckResult, AppUpdateDownloadProgress, AppUpdateReleaseInfo
from gui.i18n import tr
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XS, create_card_section, get_palette

from .wallets_section import MessageBoxLike


def _format_size(value: int | None) -> str:
    if value is None:
        return tr("settings.updates.size.unknown", "неизвестно")
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


def _center_dialog(dialog: tk.Toplevel, owner: tk.Misc) -> None:
    dialog.update_idletasks()
    width = max(dialog.winfo_reqwidth(), 420)
    height = max(dialog.winfo_reqheight(), 180)
    owner_window = owner.winfo_toplevel()
    x = owner_window.winfo_rootx() + max((owner_window.winfo_width() - width) // 2, 0)
    y = owner_window.winfo_rooty() + max((owner_window.winfo_height() - height) // 2, 0)
    dialog.geometry(f"{width}x{height}+{x}+{y}")


def build_update_section(
    parent_panel: tk.Frame | ttk.Frame,
    *,
    context: Any,
    messagebox_module: MessageBoxLike = messagebox,
    row_index: int = 0,
) -> None:
    pad_x = PAD_SM
    pad_y = PAD_XS
    supported = bool(context.controller.is_app_update_supported())
    security_diagnostics = context.controller.get_runtime_security_diagnostics()
    packaged_mode = bool(security_diagnostics.get("packaged_mode", False))
    current_version = str(context.controller.get_app_version() or "").strip() or "unknown"
    latest_release_holder: dict[str, AppUpdateReleaseInfo | None] = {"value": None}
    update_flow_state = {"active": False}
    status_var = tk.StringVar(
        value=(
            tr(
                "settings.updates.ready",
                "Можно проверить наличие нового релиза.",
            )
            if supported and packaged_mode
            else tr(
                "settings.updates.source_mode",
                "Режим source: обновление доступно для тестирования. "
                "Скачанный установщик обновляет packaged app, а не этот checkout.",
            )
            if supported
            else tr(
                "settings.updates.unsupported",
                "Обновление из приложения доступно только на Windows.",
            )
        )
    )

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
        elif supported:
            check_button.state(["!disabled"])

    def _open_release_page() -> None:
        release = latest_release_holder["value"]
        if release is None or not release.release_url:
            return
        webbrowser.open(release.release_url)

    def _show_download_dialog(release: AppUpdateReleaseInfo) -> None:
        owner = parent_panel.winfo_toplevel()
        dialog = tk.Toplevel(owner)
        dialog.withdraw()
        dialog.title(tr("settings.updates.download.title", "Загрузка обновления"))
        dialog.transient(owner)
        dialog.configure(background=get_palette().background)
        dialog.resizable(False, False)
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(0, weight=1)
        body = ttk.Frame(dialog, padding=16)
        body.grid(row=0, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        ttk.Label(
            body,
            text=tr(
                "settings.updates.download.heading",
                "Загружается установщик v{version}",
                version=release.version,
            ),
            style="Hint.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, PAD_SM))

        progress_text_var = tk.StringVar(
            value=tr("settings.updates.download.preparing", "Подготавливаем загрузку...")
        )
        ttk.Label(
            body,
            textvariable=progress_text_var,
            style="Hint.TLabel",
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, PAD_SM))

        progress = ttk.Progressbar(body, mode="determinate", maximum=100.0)
        progress.grid(row=2, column=0, sticky="ew")
        size_var = tk.StringVar(
            value=tr(
                "settings.updates.download.size",
                "Получено: {downloaded} / {total}",
                downloaded=_format_size(0),
                total=_format_size(release.asset.size_bytes),
            )
        )
        ttk.Label(body, textvariable=size_var, style="Hint.TLabel").grid(
            row=3, column=0, sticky="w", pady=(PAD_XS, 0)
        )

        running = {"active": True, "indeterminate": False}
        progress_queue: queue.SimpleQueue[AppUpdateDownloadProgress] = queue.SimpleQueue()

        def _close_guard() -> None:
            if running["active"]:
                dialog.bell()
                return
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", _close_guard)
        _center_dialog(dialog, owner)
        dialog.deiconify()
        dialog.grab_set()

        def _apply_progress(snapshot: AppUpdateDownloadProgress) -> None:
            progress_text_var.set(
                tr(
                    "settings.updates.download.progress",
                    "Скачиваем установщик...",
                )
            )
            total = snapshot.total_bytes
            if total is None or total <= 0:
                if not running["indeterminate"]:
                    progress.configure(mode="indeterminate")
                    progress.start(12)
                    running["indeterminate"] = True
                size_var.set(
                    tr(
                        "settings.updates.download.size",
                        "Получено: {downloaded} / {total}",
                        downloaded=_format_size(snapshot.bytes_downloaded),
                        total=_format_size(total),
                    )
                )
                return

            if running["indeterminate"]:
                progress.stop()
                progress.configure(mode="determinate")
                running["indeterminate"] = False
            progress["value"] = min(
                100.0,
                (float(snapshot.bytes_downloaded) / float(total)) * 100.0,
            )
            size_var.set(
                tr(
                    "settings.updates.download.size",
                    "Получено: {downloaded} / {total}",
                    downloaded=_format_size(snapshot.bytes_downloaded),
                    total=_format_size(total),
                )
            )

        def _poll_progress() -> None:
            while True:
                try:
                    snapshot = progress_queue.get_nowait()
                except queue.Empty:
                    break
                _apply_progress(snapshot)
            if running["active"] and dialog.winfo_exists():
                dialog.after(100, _poll_progress)

        def task():
            return context.controller.download_app_update(
                release,
                on_progress=lambda snapshot: progress_queue.put(snapshot),
            )

        def on_success(result) -> None:
            _set_update_flow_active(False)
            running["active"] = False
            if running["indeterminate"]:
                progress.stop()
            progress_text_var.set(
                tr(
                    "settings.updates.download.ready",
                    "Загрузка завершена.",
                )
            )
            dialog.grab_release()
            if dialog.winfo_exists():
                dialog.destroy()
            status_var.set(
                tr(
                    "settings.updates.downloaded",
                    "Обновление v{version} загружено: {filename}",
                    version=release.version,
                    filename=result.downloaded_path.name,
                )
            )
            if messagebox_module.askyesno(
                tr("settings.updates.install.title", "Установить обновление"),
                tr(
                    (
                        "settings.updates.install.source_prompt"
                        if not packaged_mode
                        else "settings.updates.install.prompt"
                    ),
                    (
                        "Вы запущены из source checkout. Скачанный установщик обновит "
                        "установленную Windows-версию приложения, а не этот исходный "
                        "проект. Продолжить?"
                        if not packaged_mode
                        else "Обновление v{version} загружено. "
                        "Закрыть приложение и запустить установщик сейчас?"
                    ),
                    version=release.version,
                ),
            ):
                try:
                    context._launch_installer_and_exit(str(result.downloaded_path))
                except RuntimeError as error:
                    messagebox_module.showerror(
                        tr("common.error", "Ошибка"),
                        tr(
                            "settings.updates.install.error",
                            "Не удалось запустить установщик: {error}",
                            error=str(error),
                        ),
                    )

        def on_error(error: BaseException) -> None:
            _set_update_flow_active(False)
            running["active"] = False
            if running["indeterminate"]:
                progress.stop()
            progress_text_var.set(
                tr(
                    "settings.updates.download.failed_status",
                    "Загрузка прервана.",
                )
            )
            dialog.grab_release()
            if dialog.winfo_exists():
                dialog.destroy()
            status_var.set(tr("settings.updates.download.failed", "Не удалось скачать обновление."))
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.updates.download.error",
                    "Не удалось скачать обновление: {error}",
                    error=str(error),
                ),
            )

        dialog.after(100, _poll_progress)
        context._run_background(
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message="",
            block_ui=False,
        )

    def _on_check_updates() -> None:
        if update_flow_state["active"]:
            return
        _set_update_flow_active(True)
        status_var.set(tr("settings.updates.checking", "Проверяем GitHub Release..."))

        def task() -> AppUpdateCheckResult:
            return context.controller.check_for_app_update()

        def on_success(result: AppUpdateCheckResult) -> None:
            latest_release_holder["value"] = result.latest_release
            if not result.update_available or result.latest_release is None:
                _set_update_flow_active(False)
                release_link_button.state(["disabled"])
                status_var.set(
                    tr(
                        "settings.updates.latest",
                        "Установлена актуальная версия v{version}.",
                        version=result.current_version,
                    )
                )
                messagebox_module.showinfo(
                    tr("settings.updates.title", "Обновление приложения"),
                    tr(
                        "settings.updates.none",
                        "Новых обновлений не найдено. Установлена версия v{version}.",
                        version=result.current_version,
                    ),
                )
                return

            release = result.latest_release
            status_var.set(
                tr(
                    "settings.updates.available",
                    "Доступно обновление v{version}.",
                    version=release.version,
                )
            )
            release_link_button.state(["!disabled"])
            should_download = messagebox_module.askyesno(
                tr("settings.updates.available.title", "Доступно обновление"),
                tr(
                    "settings.updates.available.prompt",
                    "Найдена версия v{version}. Скачать Windows installer сейчас?",
                    version=release.version,
                ),
            )
            if should_download:
                _show_download_dialog(release)
                return
            _set_update_flow_active(False)

        def on_error(error: BaseException) -> None:
            _set_update_flow_active(False)
            latest_release_holder["value"] = None
            release_link_button.state(["disabled"])
            status_var.set(tr("settings.updates.check.failed", "Не удалось проверить обновления."))
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.updates.check.error",
                    "Не удалось проверить обновления: {error}",
                    error=str(error),
                ),
            )

        context._run_background(
            task,
            on_success=on_success,
            on_error=on_error,
            busy_message="",
            block_ui=False,
        )

    buttons = ttk.Frame(update_frame, style="Card.TFrame")
    buttons.grid(row=2, column=0, columnspan=2, sticky="ew", padx=pad_x, pady=(PAD_SM, 0))
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)

    check_button = ttk.Button(
        buttons,
        text=tr("settings.updates.check_button", "Проверить обновления"),
        style="Primary.TButton",
        command=_on_check_updates,
    )
    check_button.grid(row=0, column=0, sticky="ew", padx=(0, PAD_XS))
    if not supported:
        check_button.state(["disabled"])

    release_link_button = ttk.Button(
        buttons,
        text=tr("settings.updates.release_page", "Страница релиза"),
        command=_open_release_page,
    )
    release_link_button.grid(row=0, column=1, sticky="ew", padx=(PAD_XS, 0))
    release_link_button.state(["disabled"])
