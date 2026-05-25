from __future__ import annotations

from dataclasses import dataclass, field

from gui.shell.core.notebook import (
    compute_underline_geometry,
    render_notebook_underline,
    schedule_notebook_underline,
)


@dataclass
class _Notebook:
    bbox_value: tuple[int, int, int, int] | None

    def index(self, spec: str) -> int:
        assert spec == "current"
        return 0

    def bbox(self, index: int) -> tuple[int, int, int, int] | None:
        assert index == 0
        return self.bbox_value


@dataclass
class _Canvas:
    configured_bg: str | None = None
    placed: dict[str, object] | None = None
    forgot: bool = False
    deleted: list[object] = field(default_factory=list)
    lines: list[tuple[tuple[object, ...], dict[str, object]]] = field(default_factory=list)
    lifted: object | None = None

    def configure(self, **kwargs: object) -> None:
        self.configured_bg = str(kwargs.get("bg"))

    def place_forget(self) -> None:
        self.forgot = True

    def place(self, **kwargs: object) -> None:
        self.placed = kwargs

    def delete(self, tag_or_id: object) -> None:
        self.deleted.append(tag_or_id)

    def create_line(self, *args: object, **kwargs: object) -> object:
        self.lines.append((args, kwargs))
        return object()

    def lift(self, above_this: object | None = None) -> None:
        self.lifted = above_this


def test_compute_underline_geometry_rejects_invalid_bbox() -> None:
    assert compute_underline_geometry(None, horizontal_padding=8) is None
    assert compute_underline_geometry((1, 2, 0, 10), horizontal_padding=8) is None


def test_render_notebook_underline_draws_expected_line() -> None:
    notebook = _Notebook((10, 20, 100, 30))
    canvas = _Canvas()

    rendered = render_notebook_underline(
        notebook=notebook,
        canvas=canvas,
        background="#111111",
        line_color="#ffffff",
        horizontal_padding=8,
    )

    assert rendered is True
    assert canvas.configured_bg == "#111111"
    assert canvas.placed is not None
    assert canvas.deleted == ["all"]
    assert canvas.lines
    assert canvas.lifted is notebook


def test_schedule_notebook_underline_delegates_to_idle_scheduler() -> None:
    calls: list[tuple[str, object]] = []

    job_id = schedule_notebook_underline(
        schedule_after_idle=lambda key, callback: calls.append((key, callback)) or "job-1",
        render_callback=lambda: None,
    )

    assert job_id == "job-1"
    assert calls and calls[0][0] == "notebook_underline"
