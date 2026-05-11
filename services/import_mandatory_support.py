from __future__ import annotations

import logging
from collections.abc import Callable

from app.finance_service import FinanceService
from domain.import_policy import ImportPolicy
from domain.import_result import ImportResult
from domain.records import MandatoryExpenseRecord
from services.import_parser import ParsedImportData
from utils.import_core import parse_import_row
from utils.money import to_money_float

FixedOptionalMoney = Callable[[float | None], float | None]
FixedOptionalRate = Callable[[float | None], float | None]
NormalizeMandatoryDescription = Callable[[str, str], str]


def import_mandatory_payload(
    finance_service: FinanceService,
    *,
    parsed: ParsedImportData,
    policy: ImportPolicy,
    fixed_amount_base_fn: FixedOptionalMoney,
    fixed_rate_fn: FixedOptionalRate,
    normalize_description_fn: NormalizeMandatoryDescription,
    logger: logging.Logger,
) -> ImportResult:
    source_rows = parsed.mandatory_rows if parsed.file_type == "json" else parsed.rows
    finance_service.reset_mandatory_for_import()
    get_rate = finance_service.get_currency_rate if policy == ImportPolicy.CURRENT_RATE else None
    wallet_ids = {int(wallet.id) for wallet in finance_service.load_wallets()}

    imported = 0
    skipped = 0
    errors: list[str] = []
    for index, row in enumerate(source_rows, start=2):
        record, _, error = parse_import_row(
            row,
            row_label=f"row {index}",
            policy=policy,
            get_rate=get_rate,
            mandatory_only=True,
        )
        if error:
            skipped += 1
            errors.append(error)
            continue
        if not isinstance(record, MandatoryExpenseRecord):
            skipped += 1
            errors.append(f"row {index}: expected mandatory expense")
            continue
        if int(record.wallet_id) not in wallet_ids:
            skipped += 1
            errors.append(f"row {index}: wallet not found ({int(record.wallet_id)})")
            continue
        description = normalize_description_fn(
            str(record.description or ""),
            str(record.category),
        )
        finance_service.create_mandatory_expense(
            amount=to_money_float(record.amount_original or 0.0),
            currency=str(record.currency).upper(),
            wallet_id=int(record.wallet_id),
            category=str(record.category),
            description=description,
            period=str(record.period),
            date=str(record.date or ""),
            amount_base=fixed_amount_base_fn(record.amount_base),
            rate_at_operation=fixed_rate_fn(record.rate_at_operation),
        )
        imported += 1
    logger.info(
        "Mandatory import completed file=%s wallets=0 records=0 transfers=0 templates=%s",
        parsed.path,
        imported,
    )
    return ImportResult(imported=imported, skipped=skipped, errors=tuple(errors))
