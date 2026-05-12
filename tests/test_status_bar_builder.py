from __future__ import annotations

from gui.status_bar_builder import (
    build_language_codes,
    build_theme_label_to_key,
    combobox_code_width,
    resolve_current_theme_label,
)


def test_combobox_code_width_respects_limits() -> None:
    assert combobox_code_width(["KZT", "USD"]) == 4
    assert combobox_code_width(["DISPLAY"]) == 6


def test_build_language_codes_contains_current_language() -> None:
    codes = build_language_codes()

    assert "RU" in codes


def test_theme_label_mapping_and_resolution_are_consistent() -> None:
    mapping = build_theme_label_to_key()
    current_label = resolve_current_theme_label(mapping)

    assert mapping
    assert current_label in mapping
