from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol


class NotebookLike(Protocol):
    def select(self, tab_id: object | None = None) -> object: ...

    def tab(self, tab_id: object, **kwargs: object) -> None: ...


class ChildLike(Protocol):
    def destroy(self) -> None: ...


class FrameLike(Protocol):
    def winfo_children(self) -> Sequence[ChildLike]: ...


def apply_tab_titles(
    notebook: NotebookLike,
    tab_widgets: Mapping[str, object],
    *,
    tab_titles: dict[str, str],
) -> None:
    for key, tab_widget in tab_widgets.items():
        notebook.tab(tab_widget, text=tab_titles[key])


def rebuild_built_tabs(
    *,
    notebook: NotebookLike,
    tab_keys_by_widget: dict[str, str],
    tab_order: list[str],
    built_tabs: set[str],
    tab_widgets: Mapping[str, FrameLike],
    reset_tab_bindings: Callable[[], None],
    ensure_tab_built: Callable[[str], None],
    refresh_operations: Callable[[], None],
    refresh_infographics: Callable[[], None],
    refresh_budgets: Callable[[], None],
    refresh_distribution: Callable[[], None],
) -> None:
    selected = notebook.select()
    selected_key = tab_keys_by_widget.get(str(selected))
    built_keys = [key for key in tab_order if key in built_tabs]
    for key in built_keys:
        frame = tab_widgets[key]
        for child in frame.winfo_children():
            child.destroy()
    built_tabs.clear()
    reset_tab_bindings()
    for key in built_keys:
        ensure_tab_built(key)
    if selected_key is not None and selected_key in tab_widgets:
        notebook.select(tab_widgets[selected_key])
    if "operations" in built_keys:
        refresh_operations()
    if "infographics" in built_keys:
        refresh_infographics()
    if "budget" in built_keys:
        refresh_budgets()
    if "distribution" in built_keys:
        refresh_distribution()
