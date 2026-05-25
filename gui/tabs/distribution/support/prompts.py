from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DistributionActionUi:
    messagebox_module: Any
    ask_text_fn: Any
    ask_numeric_text_fn: Any
