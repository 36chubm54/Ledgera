from __future__ import annotations

from collections.abc import Callable


def set_online_mode(
    *,
    enabled: bool,
    is_online: bool,
    set_use_online: Callable[[bool], None],
    refresh_online_service: Callable[[str], bool],
    load_offline_rates: Callable[[], None],
) -> bool:
    normalized = bool(enabled)
    if normalized == bool(is_online):
        return False
    set_use_online(normalized)
    if normalized:
        refresh_online_service("CurrencyService: failed to fetch rates on mode switch")
    else:
        load_offline_rates()
    return True


def refresh_online_rates(
    *,
    is_online: bool,
    refresh_online_service: Callable[[str], bool],
) -> bool:
    if not is_online:
        return False
    return refresh_online_service("CurrencyService: manual rate refresh failed")
