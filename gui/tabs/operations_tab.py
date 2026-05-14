"""Compatibility shim for the operations tab."""

from __future__ import annotations

from gui.tabs.operations.builder import build_operations_tab
from gui.tabs.operations.contracts import OperationsTabBindings, OperationsTabContext

__all__ = ["OperationsTabBindings", "OperationsTabContext", "build_operations_tab"]
