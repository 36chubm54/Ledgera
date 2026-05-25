from __future__ import annotations

import queue
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from domain.update import (
    AppUpdateCheckResult,
    AppUpdateDownloadProgress,
    AppUpdateReleaseInfo,
    PendingUpdateInstallState,
)
from gui.i18n import tr
from gui.ui_theme import PAD_SM, PAD_XS, get_palette
from services.support.app_update import is_newer_app_version

from .update_support import (
    artifact_label,
    center_update_dialog,
    format_update_size,
    is_linux_package_artifact,
)

if TYPE_CHECKING:
    from ..core.contracts import SettingsTabContext
    from .wallets_support import MessageBoxLike


def show_update_download_dialog(
    *,
    parent_panel: tk.Frame | ttk.Frame,
    context: SettingsTabContext,
    messagebox_module: MessageBoxLike,
    release: AppUpdateReleaseInfo,
    release_page_url: str,
    set_update_flow_active: Callable[[bool], None],
    set_pending_install_state: Callable[[PendingUpdateInstallState | None], None],
    set_status: Callable[[str], None],
    refresh_release_button_state: Callable[[], None],
    open_url: Callable[[str], Any],
) -> None:
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
            "Загружается {artifact} v{version}",
            artifact=artifact_label(release.asset.kind),
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
            downloaded=format_update_size(0),
            total=format_update_size(release.asset.size_bytes),
        )
    )
    ttk.Label(body, textvariable=size_var, style="Hint.TLabel").grid(
        row=3, column=0, sticky="w", pady=(PAD_XS, 0)
    )

    running = {"active": True, "indeterminate": False}
    poll_after_id: dict[str, str | None] = {"value": None}
    progress_queue: queue.SimpleQueue[AppUpdateDownloadProgress] = queue.SimpleQueue()

    def _cancel_poll() -> None:
        after_id = poll_after_id["value"]
        poll_after_id["value"] = None
        if after_id is None:
            return
        try:
            dialog.after_cancel(after_id)
        except tk.TclError:
            return

    def _close_guard() -> None:
        if running["active"]:
            dialog.bell()
            return
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", _close_guard)
    center_update_dialog(dialog, owner)
    dialog.deiconify()
    dialog.grab_set()

    def _apply_progress(snapshot: AppUpdateDownloadProgress) -> None:
        progress_text_var.set(
            tr(
                "settings.updates.download.progress",
                "Скачиваем {artifact}...",
                artifact=artifact_label(release.asset.kind),
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
                    downloaded=format_update_size(snapshot.bytes_downloaded),
                    total=format_update_size(total),
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
                downloaded=format_update_size(snapshot.bytes_downloaded),
                total=format_update_size(total),
            )
        )

    def _poll_progress() -> None:
        poll_after_id["value"] = None
        if not dialog.winfo_exists():
            return
        while True:
            try:
                snapshot = progress_queue.get_nowait()
            except queue.Empty:
                break
            _apply_progress(snapshot)
        if running["active"] and dialog.winfo_exists():
            poll_after_id["value"] = dialog.after(100, _poll_progress)

    def task():
        return context.controller.download_app_update(
            release,
            on_progress=lambda snapshot: progress_queue.put(snapshot),
        )

    def on_success(result) -> None:
        set_update_flow_active(False)
        running["active"] = False
        _cancel_poll()
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
        pending_state = PendingUpdateInstallState(
            version=release.version,
            asset_kind=release.asset.kind,
            artifact_path=result.downloaded_path,
            release_url=release.release_url or release_page_url,
        )
        context.controller.save_pending_update_install_state(pending_state)
        set_pending_install_state(pending_state)
        set_status(
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
                    "settings.updates.install.linux_terminal_prompt"
                    if is_linux_package_artifact(release.asset.kind)
                    else "settings.updates.install.prompt"
                ),
                (
                    "Обновление v{version} загружено. "
                    "Закрыть приложение и открыть терминал для установки скачанного "
                    "{artifact} через sudo сейчас?"
                    if is_linux_package_artifact(release.asset.kind)
                    else "Обновление v{version} загружено. "
                    "Закрыть приложение и открыть скачанный {artifact} сейчас?"
                ),
                artifact=artifact_label(release.asset.kind),
                version=release.version,
            ),
        ):
            try:
                context._launch_downloaded_update_and_exit(
                    str(result.downloaded_path),
                    target_version=release.version,
                )
            except RuntimeError as error:
                messagebox_module.showerror(
                    tr("common.error", "Ошибка"),
                    tr(
                        "settings.updates.install.error",
                        "Не удалось открыть скачанный файл обновления: {error}",
                        error=str(error),
                    ),
                )
                fallback_url = release.release_url or release_page_url
                if fallback_url and messagebox_module.askyesno(
                    tr("settings.updates.release_page", "Страница релиза"),
                    tr(
                        "settings.updates.install.release_page_fallback",
                        "Не удалось запустить установку обновления. Открыть страницу релиза GitHub?",  # noqa: E501
                    ),
                ):
                    open_url(fallback_url)

    def on_error(error: BaseException) -> None:
        set_update_flow_active(False)
        running["active"] = False
        _cancel_poll()
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
        set_status(tr("settings.updates.download.failed", "Не удалось скачать обновление."))
        messagebox_module.showerror(
            tr("common.error", "Ошибка"),
            tr(
                "settings.updates.download.error",
                "Не удалось скачать обновление: {error}",
                error=str(error),
            ),
        )
        refresh_release_button_state()

    poll_after_id["value"] = dialog.after(100, _poll_progress)
    context._run_background(
        task,
        on_success=on_success,
        on_error=on_error,
        busy_message="",
        block_ui=False,
    )


def handle_update_check(
    *,
    context: SettingsTabContext,
    messagebox_module: MessageBoxLike,
    current_version: str,
    release_page_url: str,
    update_flow_active: bool,
    pending_state: PendingUpdateInstallState | None,
    clear_pending_install_state: Callable[[], None],
    set_ready_status: Callable[[], None],
    refresh_release_button_state: Callable[[], None],
    set_update_flow_active: Callable[[bool], None],
    set_status: Callable[[str], None],
    latest_release_holder: dict[str, AppUpdateReleaseInfo | None],
    show_download_dialog: Callable[[AppUpdateReleaseInfo], None],
    open_url: Callable[[str], Any],
) -> None:
    if update_flow_active:
        return
    if pending_state is not None:
        if not pending_state.artifact_path.is_file() or not is_newer_app_version(
            current_version,
            pending_state.version,
        ):
            clear_pending_install_state()
            set_ready_status()
            refresh_release_button_state()
        else:
            try:
                context._launch_downloaded_update_and_exit(
                    str(pending_state.artifact_path),
                    target_version=pending_state.version,
                )
            except RuntimeError as error:
                messagebox_module.showerror(
                    tr("common.error", "Ошибка"),
                    tr(
                        "settings.updates.install.error",
                        "Не удалось открыть скачанный файл обновления: {error}",
                        error=str(error),
                    ),
                )
                fallback_url = pending_state.release_url or release_page_url
                if fallback_url and messagebox_module.askyesno(
                    tr("settings.updates.release_page", "Страница релиза"),
                    tr(
                        "settings.updates.install.release_page_fallback",
                        "Не удалось запустить установку обновления. Открыть страницу релиза GitHub?",  # noqa: E501
                    ),
                ):
                    open_url(fallback_url)
            return
    set_update_flow_active(True)
    set_status(tr("settings.updates.checking", "Проверяем GitHub Release..."))

    def task() -> AppUpdateCheckResult:
        return context.controller.check_for_app_update()

    def on_success(result: AppUpdateCheckResult) -> None:
        latest_release_holder["value"] = result.latest_release
        if not result.update_available or result.latest_release is None:
            set_update_flow_active(False)
            refresh_release_button_state()
            set_status(
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
        set_status(
            tr(
                "settings.updates.available",
                "Доступно обновление v{version}.",
                version=release.version,
            )
        )
        refresh_release_button_state()
        should_download = messagebox_module.askyesno(
            tr("settings.updates.available.title", "Доступно обновление"),
            tr(
                "settings.updates.available.prompt",
                "Найдена версия v{version}. Скачать {artifact} сейчас?",
                artifact=artifact_label(release.asset.kind),
                version=release.version,
            ),
        )
        if should_download:
            show_download_dialog(release)
            return
        set_update_flow_active(False)

    def on_error(error: BaseException) -> None:
        set_update_flow_active(False)
        latest_release_holder["value"] = None
        refresh_release_button_state()
        set_status(tr("settings.updates.check.failed", "Не удалось проверить обновления."))
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
