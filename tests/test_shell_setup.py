from __future__ import annotations

from types import SimpleNamespace

from gui.shell.shell_setup import attach_tab_aliases, initialize_shell_state


def test_initialize_shell_state_sets_expected_defaults() -> None:
    owner = SimpleNamespace()

    initialize_shell_state(owner, after_jobs={"job": "id"})

    assert owner._record_id_to_repo_index == {}
    assert owner._built_tabs == set()
    assert owner._after_jobs == {"job": "id"}
    assert owner.records_tree is None
    assert owner._theme_label_to_key == {}
    assert owner.monthly_bar_canvas is None


def test_attach_tab_aliases_assigns_named_tab_attributes() -> None:
    owner = SimpleNamespace()
    tabs = {
        "infographics": object(),
        "operations": object(),
        "reports": object(),
        "analytics": object(),
        "dashboard": object(),
        "budget": object(),
        "debts": object(),
        "distribution": object(),
        "settings": object(),
    }

    attach_tab_aliases(owner, tabs)

    assert owner.tab_infographics is tabs["infographics"]
    assert owner.tab_distribution is tabs["distribution"]
    assert owner.tab_settings is tabs["settings"]
