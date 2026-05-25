from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol


class NotebookLike(Protocol):
    def select(self, tab_id: object | None = None) -> object: ...


def ensure_tab_built(
    built_tabs: set[str],
    tab_key: str,
    *,
    build_tab_for_key: Callable[[str], bool],
) -> bool:
    if tab_key in built_tabs:
        return False
    if not build_tab_for_key(tab_key):
        return False
    built_tabs.add(tab_key)
    return True


def handle_tab_changed(
    notebook: NotebookLike,
    tab_keys_by_widget: Mapping[str, str],
    *,
    ensure_tab_built_for_key: Callable[[str], None],
    schedule_notebook_underline: Callable[[], None],
) -> None:
    selected = notebook.select()
    tab_key = tab_keys_by_widget.get(str(selected))
    if tab_key is not None:
        ensure_tab_built_for_key(tab_key)
    schedule_notebook_underline()


def schedule_deferred_action(
    schedule_after_idle: Callable[[str, Callable[[], None]], str],
    key: str,
    callback: Callable[[], None],
) -> str:
    return schedule_after_idle(key, callback)
