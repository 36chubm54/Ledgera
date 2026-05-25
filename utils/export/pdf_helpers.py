from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from reportlab.lib import colors
from reportlab.platypus import TableStyle

from utils.export.io import ensure_export_parent_dir


def build_pdf_title_style(
    font_name: str,
    *,
    font_size: int = 12,
    align: str = "CENTER",
) -> TableStyle:
    return TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey),
            ("ALIGN", (0, 0), (-1, -1), align),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
    )


def build_pdf_grid_style(
    font_name: str,
    *,
    font_size: int,
    header_background: Any,
    right_align_from_col: int,
) -> TableStyle:
    return TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), header_background),
            ("ALIGN", (right_align_from_col, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
    )


def build_pdf_warning_style(font_name: str) -> TableStyle:
    return TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.darkgoldenrod),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def build_pdf_document_output(doc: Any, filepath: str, elements: Sequence[Any]) -> None:
    ensure_export_parent_dir(filepath)
    doc.build(list(elements))  # type: ignore[arg-type]
