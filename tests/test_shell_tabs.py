from __future__ import annotations

from dataclasses import dataclass, field

from gui.shell.core.tabs import apply_tab_titles, rebuild_built_tabs


@dataclass
class _Child:
    destroyed: bool = False

    def destroy(self) -> None:
        self.destroyed = True


@dataclass
class _Frame:
    children: list[_Child] = field(default_factory=list)

    def winfo_children(self) -> list[_Child]:
        return self.children


@dataclass
class _Notebook:
    selected: object
    tabs: dict[object, dict[str, object]] = field(default_factory=dict)
    selected_history: list[object] = field(default_factory=list)

    def select(self, tab_id: object | None = None) -> object:
        if tab_id is None:
            return self.selected
        self.selected = tab_id
        self.selected_history.append(tab_id)
        return tab_id

    def tab(self, tab_id: object, **kwargs: object) -> None:
        self.tabs.setdefault(tab_id, {}).update(kwargs)


def test_apply_tab_titles_updates_notebook_tabs() -> None:
    notebook = _Notebook(selected="operations")
    tab_widgets = {"operations": object(), "reports": object()}

    apply_tab_titles(
        notebook,
        tab_widgets,
        tab_titles={"operations": "Operations", "reports": "Reports"},
    )

    assert notebook.tabs[tab_widgets["operations"]]["text"] == "Operations"
    assert notebook.tabs[tab_widgets["reports"]]["text"] == "Reports"


def test_rebuild_built_tabs_recreates_and_refreshes_built_sections() -> None:
    ops_frame = _Frame(children=[_Child(), _Child()])
    reports_frame = _Frame(children=[_Child()])
    notebook = _Notebook(selected="ops_widget")
    tab_widgets = {"operations": ops_frame, "reports": reports_frame}
    tab_keys_by_widget = {"ops_widget": "operations"}
    built_tabs = {"operations", "reports"}
    ensured: list[str] = []
    called: list[str] = []

    rebuild_built_tabs(
        notebook=notebook,
        tab_keys_by_widget=tab_keys_by_widget,
        tab_order=["operations", "reports"],
        built_tabs=built_tabs,
        tab_widgets=tab_widgets,
        reset_tab_bindings=lambda: called.append("reset"),
        ensure_tab_built=lambda key: ensured.append(key),
        refresh_operations=lambda: called.append("operations"),
        refresh_infographics=lambda: called.append("infographics"),
        refresh_budgets=lambda: called.append("budgets"),
        refresh_distribution=lambda: called.append("distribution"),
    )

    assert all(child.destroyed for child in ops_frame.children + reports_frame.children)
    assert ensured == ["operations", "reports"]
    assert called == ["reset", "operations"]
    assert notebook.selected_history == [ops_frame]
    assert built_tabs == set()
