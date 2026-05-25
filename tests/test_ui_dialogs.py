from __future__ import annotations

import logging
import tkinter as tk

from gui.ui_dialogs import _play_system_sound, _run_modal


def test_play_system_sound_logs_tk_bell_fallback_failure(monkeypatch, caplog) -> None:
    class BrokenRoot:
        def bell(self) -> None:
            raise tk.TclError("bell denied")

    monkeypatch.setattr("gui.ui_dialogs.platform.system", lambda: "Linux")
    monkeypatch.setattr("gui.ui_dialogs.tk._get_default_root", lambda: BrokenRoot())
    caplog.set_level(logging.DEBUG)

    _play_system_sound("warning")

    assert "Tk bell fallback failed" in caplog.text
    assert "bell denied" in caplog.text


def test_run_modal_logs_temp_root_cleanup_failure(caplog) -> None:
    class DialogStub:
        def update_idletasks(self) -> None:
            return None

        def grab_set(self) -> None:
            return None

        def focus_set(self) -> None:
            return None

    class OwnerStub:
        def wait_window(self, _dialog: object) -> None:
            return None

    class BrokenTempRoot:
        def destroy(self) -> None:
            raise tk.TclError("temp root locked")

    caplog.set_level(logging.DEBUG)

    _run_modal(DialogStub(), OwnerStub(), temp_root=BrokenTempRoot())  # type: ignore[arg-type]

    assert "Temporary dialog root cleanup failed" in caplog.text
    assert "temp root locked" in caplog.text
