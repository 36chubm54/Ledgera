from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from tkinter import ROUND
from typing import Any


@dataclass(frozen=True, slots=True)
class UnderlineGeometry:
    x: int
    y: int
    width: int
    height: int
    line_y: int
    start_x: int
    end_x: int


def compute_underline_geometry(
    bbox: Sequence[int] | None,
    *,
    horizontal_padding: int,
) -> UnderlineGeometry | None:
    if bbox is None or len(bbox) < 4:
        return None
    x, y, width, height = map(int, bbox[:4])
    if width <= 0 or height <= 0:
        return None
    return UnderlineGeometry(
        x=x,
        y=y,
        width=width,
        height=height,
        line_y=max(height - 2, 1),
        start_x=x + horizontal_padding,
        end_x=x + max(width - horizontal_padding, horizontal_padding),
    )


def render_notebook_underline(
    *,
    notebook: Any,
    canvas: Any,
    background: str,
    line_color: str,
    horizontal_padding: int,
) -> bool:
    canvas.configure(bg=background)
    geometry = compute_underline_geometry(
        notebook.bbox(notebook.index("current")),
        horizontal_padding=horizontal_padding,
    )
    if geometry is None:
        canvas.place_forget()
        return False
    canvas.place(in_=notebook, x=0, y=geometry.y + geometry.line_y, relwidth=1, height=3)
    canvas.delete("all")
    canvas.create_line(
        geometry.start_x,
        1,
        geometry.end_x,
        1,
        fill=line_color,
        width=2,
        capstyle=ROUND,
    )
    canvas.lift(notebook)
    return True


def schedule_notebook_underline(
    *,
    schedule_after_idle: Any,
    render_callback: Any,
) -> str:
    return schedule_after_idle("notebook_underline", render_callback)
