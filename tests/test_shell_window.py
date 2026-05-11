from __future__ import annotations

from gui.shell.shell_window import configure_main_window


class _FakeWindow:
    def __init__(self) -> None:
        self.geometry_value: str | None = None
        self.minsize_value: tuple[int, int] | None = None
        self.protocol_calls: list[tuple[str, object]] = []

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def geometry(self, value: str) -> None:
        self.geometry_value = value

    def minsize(self, width: int, height: int) -> None:
        self.minsize_value = (width, height)

    def protocol(self, name: str, callback: object) -> None:
        self.protocol_calls.append((name, callback))

    def destroy(self) -> None:
        return None


def test_configure_main_window_sets_geometry_and_protocol() -> None:
    window = _FakeWindow()

    configure_main_window(window)

    assert window.geometry_value == "1640x939"
    assert window.minsize_value == (1640, 939)
    assert window.protocol_calls and window.protocol_calls[0][0] == "WM_DELETE_WINDOW"
