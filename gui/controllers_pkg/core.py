from __future__ import annotations

from typing import Any

from gui.controllers_pkg.import_bridge import ControllerImportBridgeMixin
from gui.controllers_pkg.records_mandatory import ControllerRecordsMandatoryMixin
from gui.controllers_pkg.runtime import ControllerRuntimeMixin
from gui.controllers_pkg.wallets_transfers import ControllerWalletsTransfersMixin


class ControllerCoreMixin(
    ControllerRecordsMandatoryMixin,
    ControllerWalletsTransfersMixin,
    ControllerImportBridgeMixin,
    ControllerRuntimeMixin,
):
    _repository: Any
    _currency: Any
    _app_update: Any
    _record_service: Any
    _ui_preferences: Any
    _imports: Any
    _metrics_service: Any
    replace_assets: Any
    replace_goals: Any
