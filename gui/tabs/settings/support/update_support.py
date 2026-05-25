from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.update import AppReleaseAsset, AppUpdateReleaseInfo, PendingUpdateInstallState
from gui.i18n import tr
from services.support.app_update import is_newer_app_version

if TYPE_CHECKING:
    from ..core.contracts import SettingsController


@dataclass(frozen=True, slots=True)
class UpdateSectionEnvironment:
    supported: bool
    packaged_mode: bool
    appimage_mode: bool
    linux_package_kind: str
    current_version: str
    release_page_url: str
    is_linux: bool
    is_source_mode: bool
    is_packaged_linux: bool
    has_known_linux_package_kind: bool
    can_check_updates: bool


def format_update_size(value: int | None) -> str:
    if value is None:
        return tr("settings.updates.size.unknown", "неизвестно")
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


def center_update_dialog(dialog: tk.Toplevel, owner: tk.Misc) -> None:
    dialog.update_idletasks()
    width = max(dialog.winfo_reqwidth(), 420)
    height = max(dialog.winfo_reqheight(), 180)
    owner_window = owner.winfo_toplevel()
    x = owner_window.winfo_rootx() + max((owner_window.winfo_width() - width) // 2, 0)
    y = owner_window.winfo_rooty() + max((owner_window.winfo_height() - height) // 2, 0)
    dialog.geometry(f"{width}x{height}+{x}+{y}")


def build_update_environment(
    controller: SettingsController,
    *,
    platform_name: str,
) -> UpdateSectionEnvironment:
    supported = bool(controller.is_app_update_supported())
    security_diagnostics = controller.get_runtime_security_diagnostics()
    packaged_mode = bool(security_diagnostics.get("packaged_mode", False))
    appimage_mode = bool(security_diagnostics.get("appimage_mode", False))
    linux_package_kind = str(security_diagnostics.get("linux_package_kind") or "").strip().lower()
    current_version = str(controller.get_app_version() or "").strip() or "unknown"
    release_page_url = str(controller.get_app_release_page_url() or "").strip()
    is_linux = platform_name.startswith("linux")
    is_source_mode = not packaged_mode
    is_packaged_linux = packaged_mode and is_linux
    has_known_linux_package_kind = (
        is_packaged_linux and not appimage_mode and linux_package_kind in {"deb", "rpm"}
    )
    can_check_updates = supported or has_known_linux_package_kind
    return UpdateSectionEnvironment(
        supported=supported,
        packaged_mode=packaged_mode,
        appimage_mode=appimage_mode,
        linux_package_kind=linux_package_kind,
        current_version=current_version,
        release_page_url=release_page_url,
        is_linux=is_linux,
        is_source_mode=is_source_mode,
        is_packaged_linux=is_packaged_linux,
        has_known_linux_package_kind=has_known_linux_package_kind,
        can_check_updates=can_check_updates,
    )


def artifact_label(kind: str) -> str:
    if kind in {"linux-deb", "linux-rpm"}:
        return tr("settings.updates.artifact.linux_package", "Linux package")
    if kind == "linux-appimage":
        return tr("settings.updates.artifact.appimage", "AppImage")
    return tr("settings.updates.artifact.windows_installer", "Windows installer")


def is_linux_package_artifact(kind: str) -> bool:
    return kind in {"linux-deb", "linux-rpm"}


def pending_state_to_release(
    state: PendingUpdateInstallState,
    *,
    release_page_url: str,
) -> AppUpdateReleaseInfo:
    try:
        size_bytes = state.artifact_path.stat().st_size if state.artifact_path.is_file() else None
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


def load_pending_update_install_state(
    controller: SettingsController,
    *,
    current_version: str,
) -> PendingUpdateInstallState | None:
    state = controller.load_pending_update_install_state()
    if state is None:
        return None
    if not state.artifact_path.is_file() or not is_newer_app_version(
        current_version, state.version
    ):
        controller.clear_pending_update_install_state()
        return None
    return state


def ready_status_text(environment: UpdateSectionEnvironment) -> str:
    if environment.has_known_linux_package_kind:
        return tr(
            "settings.updates.linux_ready",
            "Можно проверить наличие нового Linux-пакета.",
        )
    if environment.can_check_updates and environment.packaged_mode:
        return tr(
            "settings.updates.ready",
            "Можно проверить наличие нового релиза.",
        )
    if environment.is_source_mode:
        return tr(
            "settings.updates.source_manual",
            "Для source-mode встроенная установка обновлений не поддерживается. "
            "Используйте страницу релизов GitHub вручную.",
        )
    if environment.is_packaged_linux and environment.appimage_mode:
        return tr(
            "settings.updates.linux_appimage_manual",
            "Для AppImage встроенная установка обновлений пока недоступна. "
            "Скачайте новый AppImage со страницы релизов GitHub.",
        )
    if environment.is_packaged_linux:
        return tr(
            "settings.updates.linux_manual",
            "Для Linux packaged builds встроенная установка обновлений пока недоступна. "
            "Скачайте новый Linux-пакет или AppImage со страницы релизов GitHub.",
        )
    if environment.is_linux:
        return tr(
            "settings.updates.linux_source_manual",
            "Для Linux source-mode встроенная установка обновлений не поддерживается. "
            "Используйте страницу релизов GitHub вручную.",
        )
    return tr(
        "settings.updates.unsupported",
        "Обновление из приложения доступно только на Windows.",
    )


def install_ready_status_text(version: str) -> str:
    return tr(
        "settings.updates.install_ready",
        "Обновление v{version} уже скачано и готово к установке.",
        version=version,
    )


def resolve_release_page_url(
    *,
    pending_state: PendingUpdateInstallState | None,
    release: AppUpdateReleaseInfo | None,
    release_page_url: str,
) -> str:
    if pending_state is not None and pending_state.release_url:
        return pending_state.release_url
    if release is not None and release.release_url:
        return release.release_url
    return release_page_url


def should_enable_release_page_button(
    *,
    environment: UpdateSectionEnvironment,
    update_flow_active: bool,
    pending_state: PendingUpdateInstallState | None,
    release: AppUpdateReleaseInfo | None,
    release_page_url: str,
) -> bool:
    if update_flow_active:
        return False
    if not resolve_release_page_url(
        pending_state=pending_state,
        release=release,
        release_page_url=release_page_url,
    ):
        return False
    if pending_state is not None:
        return True
    return environment.supported or environment.is_linux or environment.is_source_mode
