from __future__ import annotations

import gc
import logging
import os
from typing import Any


def ensure_export_parent_dir(filepath: str) -> None:
    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)


def close_workbook_safely(workbook: Any, *, context: str, logger: logging.Logger) -> None:
    try:
        workbook.close()
    except (AttributeError, OSError, RuntimeError, ValueError) as exc:
        logger.debug("Workbook close degraded after %s: %s", context, exc, exc_info=True)


def save_workbook_output(
    workbook: Any, filepath: str, *, context: str, logger: logging.Logger
) -> None:
    ensure_export_parent_dir(filepath)
    workbook.save(filepath)
    close_workbook_safely(workbook, context=context, logger=logger)
    gc.collect()


def finalize_workbook_io(workbook: Any, *, context: str, logger: logging.Logger) -> None:
    close_workbook_safely(workbook, context=context, logger=logger)
    gc.collect()
