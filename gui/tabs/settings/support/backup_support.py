from __future__ import annotations

from typing import Any

from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from gui.helpers import open_in_file_manager
from gui.i18n import tr

from .wallets_support import MessageBoxLike


def refresh_after_backup_import(
    *,
    context: Any,
    refresh_wallets: Any,
) -> None:
    refresh_mandatory = getattr(context, "refresh_mandatory", None)
    if callable(refresh_mandatory):
        refresh_mandatory()
    refresh_wallets()
    context._refresh_list()
    context._refresh_charts()
    context._refresh_budgets()
    context._refresh_all()


def start_backup_import(
    *,
    context: Any,
    filepath: str,
    messagebox_module: MessageBoxLike,
    refresh_wallets: Any,
) -> None:
    def task(force: bool) -> ImportResult:
        return context.controller.import_records(
            "JSON",
            filepath,
            ImportPolicy.FULL_BACKUP,
            force=force,
        )

    def on_success(result: ImportResult) -> None:
        details = ""
        if result.skipped:
            details = f"\nSkipped: {result.skipped}\n- " + "\n- ".join(result.errors[:5])
        messagebox_module.showinfo(
            tr("common.done", "Готово"),
            tr(
                "settings.backup.import.success",
                "Резервная копия импортирована. Импортировано сущностей: {count}.{details}",
                count=result.imported,
                details=details,
            ),
        )
        refresh_after_backup_import(context=context, refresh_wallets=refresh_wallets)

    def run_import(force: bool) -> None:
        def current_task() -> ImportResult:
            return task(force)

        def on_error(exc: BaseException) -> None:
            try:
                from utils.backup_utils import BackupReadonlyError

                is_readonly = isinstance(exc, BackupReadonlyError)
            except ImportError:
                is_readonly = False

            if is_readonly and not force:
                if messagebox_module.askyesno(
                    tr("settings.backup.readonly.title", "Снимок только для чтения"),
                    tr(
                        "settings.backup.readonly.confirm",
                        "Резервная копия доступна только для чтения. "
                        "Импортировать с принудительным режимом?",
                    ),
                ):
                    run_import(True)
                return
            messagebox_module.showerror(
                tr("common.error", "Ошибка"),
                tr(
                    "settings.backup.import.error",
                    "Не удалось импортировать резервную копию: {error}",
                    error=exc,
                ),
            )

        context._run_background(
            current_task,
            on_success=on_success,
            on_error=on_error,
            busy_message=tr("settings.backup.import.busy", "Импортируем полную копию..."),
        )

    run_import(False)


def build_backup_export_payload(context: Any) -> dict[str, Any]:
    wallets = context.repository.load_wallets()
    records = context.repository.load_all()
    mandatory_expenses = context.repository.load_mandatory_expenses()
    budgets = context.controller.get_budgets()
    debts = context.controller.get_debts()
    debt_payments = []
    for debt in debts:
        debt_payments.extend(context.controller.get_debt_history(debt.id))
    assets = context.controller.get_assets(active_only=False)
    asset_snapshots = []
    for asset in assets:
        asset_snapshots.extend(context.controller.get_asset_history(asset.id))
    goals = context.controller.get_goals()
    distribution_items, distribution_subitems_by_item = (
        context.controller.export_distribution_structure()
    )
    distribution_subitems = [
        subitem
        for item_id in sorted(distribution_subitems_by_item)
        for subitem in distribution_subitems_by_item[item_id]
    ]
    distribution_snapshots = context.controller.get_frozen_distribution_rows()
    transfers = context.repository.load_transfers()
    return {
        "wallets": wallets,
        "records": records,
        "mandatory_expenses": mandatory_expenses,
        "budgets": budgets,
        "debts": debts,
        "debt_payments": debt_payments,
        "assets": assets,
        "asset_snapshots": asset_snapshots,
        "goals": goals,
        "distribution_items": distribution_items,
        "distribution_subitems": distribution_subitems,
        "distribution_snapshots": distribution_snapshots,
        "transfers": transfers,
    }


def start_backup_export(
    *,
    context: Any,
    filepath: str,
    messagebox_module: MessageBoxLike,
) -> None:
    def task() -> None:
        from gui.exporters import export_full_backup

        payload = build_backup_export_payload(context)
        export_full_backup(
            filepath,
            storage_mode="sqlite",
            **payload,
        )

    def on_success(_: Any) -> None:
        messagebox_module.showinfo(
            tr("common.done", "Готово"),
            tr(
                "settings.backup.export.success",
                "Полная копия экспортирована в {filepath}",
                filepath=filepath,
            ),
        )
        open_in_file_manager(str(filepath))

    context._run_background(
        task,
        on_success=on_success,
        busy_message=tr("settings.backup.export.busy", "Экспортируем полную копию..."),
    )
