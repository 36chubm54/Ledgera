from __future__ import annotations

import queue
import sys
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Any

from domain.update import (
    AppReleaseAsset,
    AppUpdateCheckResult,
    AppUpdateDownloadProgress,
    AppUpdateReleaseInfo,
    PendingUpdateInstallState,
)
from gui.i18n import tr
from gui.ui_dialogs import messagebox_compat as messagebox
from gui.ui_theme import PAD_LG, PAD_SM, PAD_XS, create_card_section, get_palette
from services.app_update_service import is_newer_app_version

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
    appimage_mode = bool(security_diagnostics.get("appimage_mode", False))
    linux_package_kind = str(security_diagnostics.get("linux_package_kind") or "").strip().lower()
    current_version = str(context.controller.get_app_version() or "").strip() or "unknown"
    release_page_url = str(context.controller.get_app_release_page_url() or "").strip()
    is_linux = sys.platform.startswith("linux")
    is_source_mode = not packaged_mode
    is_packaged_linux = packaged_mode and is_linux
    has_known_linux_package_kind = (
        is_packaged_linux and not appimage_mode and linux_package_kind in {"deb", "rpm"}
    )
    can_check_updates = supported or has_known_linux_package_kind
    latest_release_holder: dict[str, AppUpdateReleaseInfo | None] = {"value": None}
    pending_install_holder: dict[str, PendingUpdateInstallState | None] = {"value": None}
    update_flow_state = {"active": False}
    primary_button_text = tk.StringVar(
        value=tr("settings.updates.check_button", "Проверить обновления")
    )

    def _artifact_label(kind: str) -> str:
        if kind in {"linux-deb", "linux-rpm"}:
            return tr("settings.updates.artifact.linux_package", "Linux package")
        if kind == "linux-appimage":
            return tr("settings.updates.artifact.appimage", "AppImage")
        return tr("settings.updates.artifact.windows_installer", "Windows installer")

    def _is_linux_package_artifact(kind: str) -> bool:
        return kind in {"linux-deb", "linux-rpm"}

    def _pending_state_to_release(state: PendingUpdateInstallState) -> AppUpdateReleaseInfo:
        try:
            size_bytes = (
                state.artifact_path.stat().st_size if state.artifact_path.is_file() else None
            )
        except OSError:
            size_bytes = None
        return AppUpdateReleaseInfo(
            version=state.version,
            tag_name=f"v{state.version}",
            release_url=state.release_url or release_page_url,
            asset=AppReleaseAsset(
                name=state.artifact_path.name,
                download_url="",
                size_bytes=size_bytes,
                kind=state.asset_kind,
            ),
        )

    def _clear_pending_install_state() -> None:
        pending_install_holder["value"] = None
        context.controller.clear_pending_update_install_state()

    def _load_pending_install_state() -> PendingUpdateInstallState | None:
        state = context.controller.load_pending_update_install_state()
        if state is None:
            return None
        if not state.artifact_path.is_file() or not is_newer_app_version(
            current_version, state.version
        ):
            context.controller.clear_pending_update_install_state()
            return None
        return state

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
        if has_known_linux_package_kind:
            return tr(
                "settings.updates.linux_ready",
                "Можно проверить наличие нового Linux-пакета.",
            )
        if can_check_updates and packaged_mode:
            return tr(
                "settings.updates.ready",
                "Можно проверить наличие нового релиза.",
            )
        if is_source_mode:
            return tr(
                "settings.updates.source_manual",
                "Для source-mode встроенная установка обновлений не поддерживается. "
                "Используйте страницу релизов GitHub вручную.",
            )
        if is_packaged_linux and appimage_mode:
            return tr(
                "settings.updates.linux_appimage_manual",
                "Для AppImage встроенная установка обновлений пока недоступна. "
                "Скачайте новый AppImage со страницы релизов GitHub.",
            )
        if is_packaged_linux:
            return tr(
                "settings.updates.linux_manual",
                "Для Linux packaged builds встроенная установка обновлений пока недоступна. "
                "Скачайте новый Linux-пакет или AppImage со страницы релизов GitHub.",
            )
        if is_linux:
            return tr(
                "settings.updates.linux_source_manual",
                "Для Linux source-mode встроенная установка обновлений не поддерживается. "
                "Используйте страницу релизов GitHub вручную.",
            )
        return tr(
            "settings.updates.unsupported",
            "Обновление из приложения доступно только на Windows.",
        )

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
        has_fallback_url = bool(
            (pending_install_holder["value"] and pending_install_holder["value"].release_url)
            or (latest_release_holder["value"] and latest_release_holder["value"].release_url)
            or release_page_url
        )
        if update_flow_state["active"] or not has_fallback_url:
            release_link_button.state(["disabled"])
            return
        if pending_install_holder["value"] is not None:
            release_link_button.state(["!disabled"])
            return
        if supported or is_linux or is_source_mode:
            release_link_button.state(["!disabled"])
            return
        release_link_button.state(["disabled"])

    def _set_pending_install_state(state: PendingUpdateInstallState | None) -> None:
        pending_install_holder["value"] = state
        _set_primary_button_install_mode(state is not None)
        if state is not None:
            status_var.set(
                tr(
                    "settings.updates.install_ready",
                    "Обновление v{version} уже скачано и готово к установке.",
                    version=state.version,
                )
            )
        _refresh_release_button_state()

    def _open_release_page() -> None:
        pending_state = pending_install_holder["value"]
        if pending_state is not None and pending_state.release_url:
            webbrowser.open(pending_state.release_url)
            return
        release = latest_release_holder["value"]
        if release is not None and release.release_url:
            webbrowser.open(release.release_url)
            return
        if not release_page_url:
            return
        webbrowser.open(release_page_url)

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
                "Загружается {artifact} v{version}",
                artifact=_artifact_label(release.asset.kind),
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
        _center_dialog(dialog, owner)
        dialog.deiconify()
        dialog.grab_set()

        def _apply_progress(snapshot: AppUpdateDownloadProgress) -> None:
            progress_text_var.set(
                tr(
                    "settings.updates.download.progress",
                    "Скачиваем {artifact}...",
                    artifact=_artifact_label(release.asset.kind),
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
            _set_update_flow_active(False)
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
            _set_pending_install_state(pending_state)
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
                        "settings.updates.install.linux_terminal_prompt"
                        if _is_linux_package_artifact(release.asset.kind)
                        else "settings.updates.install.prompt"
                    ),
                    (
                        "Обновление v{version} загружено. "
                        "Закрыть приложение и открыть терминал для установки скачанного "
                        "{artifact} через sudo сейчас?"
                        if _is_linux_package_artifact(release.asset.kind)
                        else "Обновление v{version} загружено. "
                        "Закрыть приложение и открыть скачанный {artifact} сейчас?"
                    ),
                    artifact=_artifact_label(release.asset.kind),
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
                        webbrowser.open(fallback_url)

        def on_error(error: BaseException) -> None:
            _set_update_flow_active(False)
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
            status_var.set(tr("settings.updates.download.failed", "Не удалось скачать обновление."))
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.updates.download.error",
                    "Не удалось скачать обновление: {error}",
                    error=str(error),
                ),
            )
            _refresh_release_button_state()

        poll_after_id["value"] = dialog.after(100, _poll_progress)
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
        pending_state = pending_install_holder["value"]
        if pending_state is not None:
            if not pending_state.artifact_path.is_file() or not is_newer_app_version(
                current_version,
                pending_state.version,
            ):
                _clear_pending_install_state()
                _set_ready_status()
                _refresh_release_button_state()
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
                        webbrowser.open(fallback_url)
                return
        _set_update_flow_active(True)
        status_var.set(tr("settings.updates.checking", "Проверяем GitHub Release..."))

        def task() -> AppUpdateCheckResult:
            return context.controller.check_for_app_update()

        def on_success(result: AppUpdateCheckResult) -> None:
            latest_release_holder["value"] = result.latest_release
            if not result.update_available or result.latest_release is None:
                _set_update_flow_active(False)
                _refresh_release_button_state()
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
            _refresh_release_button_state()
            should_download = messagebox_module.askyesno(
                tr("settings.updates.available.title", "Доступно обновление"),
                tr(
                    "settings.updates.available.prompt",
                    "Найдена версия v{version}. Скачать {artifact} сейчас?",
                    artifact=_artifact_label(release.asset.kind),
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
            _refresh_release_button_state()
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
        latest_release_holder["value"] = _pending_state_to_release(pending_state)
    _set_pending_install_state(pending_state)
    if pending_state is None:
        _refresh_release_button_state()
