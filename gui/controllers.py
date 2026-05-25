from __future__ import annotations

import logging
from typing import TypeVar, cast

from app.data.records import RecordService
from app.data.repository import RecordRepository
from app.runtime.preferences import UIPreferencesService
from app.services import CurrencyService
from gui.controllers_pkg.analysis import ControllerAnalysisFacade
from gui.controllers_pkg.core import ControllerCoreMixin
from gui.controllers_pkg.debts import ControllerDebtFacade
from gui.controllers_pkg.delegates import ControllerDelegateMixin
from gui.controllers_pkg.imports import ControllerImportFacade
from gui.controllers_pkg.planning import ControllerPlanningFacade
from gui.controllers_pkg.portfolio import ControllerPortfolioFacade
from services.support.app_update import AppUpdateService

logger = logging.getLogger(__name__)
RepoCapability = TypeVar("RepoCapability")


class FinancialController(ControllerDelegateMixin, ControllerCoreMixin):
    def __init__(self, repository: RecordRepository, currency_service: CurrencyService) -> None:
        self._repository = repository
        self._currency = currency_service
        self._app_update = AppUpdateService()
        self._record_service = RecordService(repository)
        self._ui_preferences = UIPreferencesService(repository, currency_service)
        self._imports = ControllerImportFacade(
            repository=repository,
            currency=currency_service,
            ui_preferences=self._ui_preferences,
            app_update=self._app_update,
            logger=logger,
        )
        self._portfolio = ControllerPortfolioFacade(
            repository=repository,
            currency=currency_service,
            require_repository_capability=self._require_repository_capability,
        )
        self._planning = ControllerPlanningFacade(
            require_repository_capability=self._require_repository_capability,
        )
        self._debts = ControllerDebtFacade(
            repository=repository,
            require_repository_capability=self._require_repository_capability,
            get_base_currency_code=self.get_base_currency_code,
        )
        self._analysis = ControllerAnalysisFacade(
            repository=repository,
            currency=currency_service,
            require_repository_capability=self._require_repository_capability,
            asset_service=self._portfolio.asset_service,
            goal_service=self._portfolio.goal_service,
            current_net_worth_base=self.net_worth_fixed,
        )

    def _require_repository_capability(
        self,
        protocol: type[RepoCapability],
        message: str,
    ) -> RepoCapability:
        if not isinstance(self._repository, protocol):
            raise TypeError(message)
        return cast(RepoCapability, self._repository)
