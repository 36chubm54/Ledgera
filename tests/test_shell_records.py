from __future__ import annotations

import logging
import tkinter as tk
from types import SimpleNamespace
from typing import Any, cast

from gui.shell.core.records import (
    clear_records_tooltip_state,
    destroy_records_tooltip_window,
    hide_owner_records_tooltip,
    process_records_tooltip_event,
    refresh_owner_record_views,
    refresh_record_views,
    show_owner_records_tooltip,
    show_records_tooltip_window,
    tooltip_description_for_row,
    tooltip_row_id,
    tooltip_state_matches,
)


class _FakeTree:
    def __init__(self) -> None:
        self.rows: list[tuple[str, tuple[object, ...], tuple[str, ...]]] = []
        self.heading_calls: list[tuple[str, str]] = []
        self.tag_configs: dict[str, dict[str, object]] = {}

    def heading(self, key: str, *, text: str) -> None:
        self.heading_calls.append((key, text))

    def get_children(self) -> list[str]:
        return [row_id for row_id, _values, _tags in self.rows]

    def delete(self, iid: str) -> None:
        self.rows = [row for row in self.rows if row[0] != iid]

    def tag_configure(self, tag: str, **kwargs: object) -> None:
        self.tag_configs[tag] = kwargs

    def insert(
        self,
        _parent: str,
        _index: str,
        *,
        iid: str | None = None,
        values: tuple[object, ...],
        tags: tuple[str, ...] = (),
    ) -> None:
        self.rows.append((iid or f"row-{len(self.rows)}", values, tags))

    def identify_row(self, _y: int) -> str:
        return "row-1"


class _FakeTooltip:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class _FakeEvent:
    y = 10
    x_root = 100
    y_root = 200


def test_refresh_record_views_populates_rows_maps_and_heading() -> None:
    records_tree = _FakeTree()
    tags_tree = _FakeTree()
    controller = SimpleNamespace(
        build_record_list_items=lambda records=None: [
            SimpleNamespace(
                record_id="row-1",
                repository_index=3,
                domain_record_id=7,
                description_text="Internet payment",
                kind="expense",
                tags=("mandatory",),
                tags_text="mandatory",
            )
        ],
        list_tags=lambda: [SimpleNamespace(name="mandatory", color="#ff0000")],
    )

    repo_map, domain_map, desc_map = refresh_record_views(
        controller=controller,
        records_tree=cast(Any, records_tree),
        record_tags_tree=cast(Any, tags_tree),
        records=None,
        display_currency_code="USD",
        build_record_tree_values=lambda item, kind: (item.record_id, kind),
        kind_to_foreground={"expense": "#f00"},
        foreground_for_kind=lambda kind: kind == "expense",
        color_for_tag=lambda _name: "#ff0000",
    )

    assert records_tree.heading_calls == [("kzt", "USD")]
    assert repo_map == {"row-1": 3}
    assert domain_map == {"row-1": 7}
    assert desc_map == {"row-1": "Internet payment"}
    assert records_tree.rows[0][1] == ("row-1", "expense")
    assert tags_tree.rows[0][1] == ("mandatory",)


def test_refresh_record_views_skips_tag_lookup_without_tags_tree() -> None:
    records_tree = _FakeTree()
    controller = SimpleNamespace(
        build_record_list_items=lambda records=None: [
            SimpleNamespace(
                record_id="row-1",
                repository_index=1,
                domain_record_id=2,
                description_text="Desc",
                kind="expense",
                tags=(),
                tags_text="",
            )
        ],
        list_tags=lambda: (_ for _ in ()).throw(AssertionError("tag lookup is unexpected")),
    )

    repo_map, domain_map, desc_map = refresh_record_views(
        controller=controller,
        records_tree=cast(Any, records_tree),
        record_tags_tree=None,
        records=None,
        display_currency_code="USD",
        build_record_tree_values=lambda item, kind: (item.record_id, kind),
        kind_to_foreground={"expense": "#f00"},
        foreground_for_kind=lambda kind: kind == "expense",
        color_for_tag=lambda _name: "#ff0000",
    )

    assert repo_map == {"row-1": 1}
    assert domain_map == {"row-1": 2}
    assert desc_map == {"row-1": "Desc"}


def test_tooltip_helpers_use_description_map_and_state() -> None:
    description = tooltip_description_for_row("row-1", {"row-1": "Hello"})

    assert description == "Hello"
    assert tooltip_state_matches(
        description="Hello",
        tooltip_text="Hello",
        tooltip_window=cast(Any, _FakeTooltip()),
    )
    assert not tooltip_state_matches(
        description="Hello",
        tooltip_text="Other",
        tooltip_window=cast(Any, _FakeTooltip()),
    )


def test_tooltip_row_id_and_destroy_window() -> None:
    tooltip = _FakeTooltip()

    assert tooltip_row_id(cast(Any, _FakeTree()), cast(Any, _FakeEvent())) == "row-1"
    destroy_records_tooltip_window(cast(Any, tooltip))
    assert tooltip.destroyed is True


def test_destroy_records_tooltip_window_logs_expected_cleanup_failure(caplog) -> None:
    class _BrokenTooltip:
        def destroy(self) -> None:
            raise tk.TclError("tooltip already closed")

    caplog.set_level(logging.DEBUG)

    destroy_records_tooltip_window(cast(Any, _BrokenTooltip()))

    assert "Records tooltip cleanup skipped" in caplog.text
    assert "tooltip already closed" in caplog.text


def test_show_records_tooltip_window_returns_popup(monkeypatch) -> None:
    expected = _FakeTooltip()

    monkeypatch.setattr(
        "gui.shell.core.records.show_popup_tooltip",
        lambda **_kwargs: expected,
    )

    result = show_records_tooltip_window(
        records_tree=cast(Any, _FakeTree()),
        event=cast(Any, _FakeEvent()),
        description="Tooltip",
    )

    assert result is expected


def test_clear_and_process_records_tooltip_state(monkeypatch) -> None:
    owner = SimpleNamespace(_records_tooltip_window=object(), _records_tooltip_text="x")
    clear_records_tooltip_state(owner)

    assert owner._records_tooltip_window is None
    assert owner._records_tooltip_text == ""

    shown = _FakeTooltip()
    monkeypatch.setattr(
        "gui.shell.core.records.show_popup_tooltip",
        lambda **_kwargs: shown,
    )
    tooltip_text, tooltip_window = process_records_tooltip_event(
        records_tree=cast(Any, _FakeTree()),
        event=cast(Any, _FakeEvent()),
        description_map={"row-1": "Hello"},
        tooltip_text="",
        tooltip_window=None,
        hide_tooltip=lambda: None,
    )

    assert tooltip_text == "Hello"
    assert tooltip_window is shown


def test_refresh_owner_record_views_and_owner_tooltip_helpers(monkeypatch) -> None:
    owner = SimpleNamespace(
        controller=SimpleNamespace(
            get_display_currency_code=lambda: "USD",
            to_display_amount=lambda amount: amount / 2,
            build_record_list_items=lambda records=None: [
                SimpleNamespace(
                    record_id="row-1",
                    repository_index=1,
                    domain_record_id=2,
                    description_text="Desc",
                    kind="expense",
                    tags=("mandatory",),
                    tags_text="mandatory",
                    invariant_id=7,
                    date="2026-05-11",
                    type_label="expense",
                    category="Groceries",
                    amount_original=10.0,
                    currency="USD",
                    amount_base=4500.0,
                    wallet_label="W1",
                    extra="",
                )
            ],
            list_tags=lambda: [SimpleNamespace(name="mandatory", color="#ff0000")],
        ),
        records_tree=cast(Any, _FakeTree()),
        record_tags_tree=cast(Any, _FakeTree()),
        _record_id_to_repo_index={},
        _record_id_to_domain_id={},
        _record_id_to_description={},
        _records_tooltip_window=None,
        _records_tooltip_text="",
    )

    assert refresh_owner_record_views(owner) is True
    assert owner._record_id_to_repo_index == {"row-1": 1}

    shown = _FakeTooltip()
    monkeypatch.setattr(
        "gui.shell.core.records.show_popup_tooltip",
        lambda **_kwargs: shown,
    )
    show_owner_records_tooltip(owner, cast(Any, _FakeEvent()))
    assert owner._records_tooltip_text == "Desc"
    assert owner._records_tooltip_window is shown

    hide_owner_records_tooltip(owner)
    assert owner._records_tooltip_window is None


def test_refresh_record_views_logs_expected_tag_style_failures(caplog) -> None:
    class _BrokenTree(_FakeTree):
        def tag_configure(self, tag: str, **kwargs: object) -> None:
            raise tk.TclError(f"cannot style {tag}")

    records_tree = _BrokenTree()
    tags_tree = _BrokenTree()
    controller = SimpleNamespace(
        build_record_list_items=lambda records=None: [
            SimpleNamespace(
                record_id="row-1",
                repository_index=1,
                domain_record_id=2,
                description_text="Desc",
                kind="expense",
                tags=("mandatory",),
                tags_text="mandatory",
            )
        ],
        list_tags=lambda: [SimpleNamespace(name="mandatory", color="#ff0000")],
    )

    caplog.set_level(logging.DEBUG)

    refresh_record_views(
        controller=controller,
        records_tree=cast(Any, records_tree),
        record_tags_tree=cast(Any, tags_tree),
        records=None,
        display_currency_code="USD",
        build_record_tree_values=lambda item, kind: (item.record_id, kind),
        kind_to_foreground={"expense": "#f00"},
        foreground_for_kind=lambda kind: kind == "expense",
        color_for_tag=lambda _name: "#ff0000",
    )

    assert "Records tree tag style skipped for expense" in caplog.text
    assert "Record tags tree style skipped for tag_color_ff0000" in caplog.text
