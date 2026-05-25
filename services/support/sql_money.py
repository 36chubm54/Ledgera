from __future__ import annotations


def minor_amount_expr(column: str) -> str:
    return (
        "CASE "
        f"WHEN {column}_minor IS NOT NULL "
        f"AND ({column}_minor != 0 OR ROUND({column}, 2) = 0) "
        f"THEN {column}_minor "
        f"ELSE CAST(ROUND({column} * 100.0) AS INTEGER) "
        "END"
    )


def money_expr(column: str) -> str:
    return f"({minor_amount_expr(column)} / 100.0)"


def signed_minor_amount_expr(column: str, type_column: str = "type") -> str:
    amount_expr = minor_amount_expr(column)
    return f"CASE WHEN {type_column} = 'income' THEN {amount_expr} ELSE -{amount_expr} END"
