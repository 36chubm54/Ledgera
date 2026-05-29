use ledgera_engine_core::minor_to_money_value;

use crate::{
    MonthlyCashflowRow, MonthlyCumulativeRow, NetWorthDeltaRow, StorageResult,
    metrics_monthly_summary, minor_amount_expr, signed_minor_amount_expr, sqlite_err,
    with_cached_read_connection,
};

pub fn timeline_monthly_cashflow(
    db_path: &str,
    start_date: Option<&str>,
    end_date: Option<&str>,
) -> StorageResult<Vec<MonthlyCashflowRow>> {
    let rows = metrics_monthly_summary(db_path, start_date, end_date)?;
    Ok(rows
        .into_iter()
        .map(|row| MonthlyCashflowRow {
            month: row.month,
            income: row.income,
            expenses: row.expenses,
            cashflow: row.cashflow,
        })
        .collect())
}

pub fn timeline_cumulative_income_expense(
    db_path: &str,
) -> StorageResult<Vec<MonthlyCumulativeRow>> {
    with_cached_read_connection(db_path, |conn| {
        let amount_expr = minor_amount_expr("amount_base");
        let sql = format!(
            "SELECT \
                month, \
                SUM(monthly_income) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_income, \
                SUM(monthly_expenses) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_expenses \
             FROM ( \
                SELECT \
                    strftime('%Y-%m', date) AS month, \
                    COALESCE(SUM(CASE type WHEN 'income' THEN {amount_expr} ELSE 0 END), 0) AS monthly_income, \
                    COALESCE(SUM(CASE WHEN type IN ('expense', 'mandatory_expense') THEN {amount_expr} ELSE 0 END), 0) AS monthly_expenses \
                FROM records \
                WHERE transfer_id IS NULL \
                GROUP BY strftime('%Y-%m', date) \
             ) \
             ORDER BY month"
        );
        let mut stmt = conn.prepare(&sql).map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| {
                Ok(MonthlyCumulativeRow {
                    month: row.get(0)?,
                    cumulative_income: minor_to_money_value(row.get::<_, i64>(1)?),
                    cumulative_expenses: minor_to_money_value(row.get::<_, i64>(2)?),
                })
            })
            .map_err(sqlite_err)?;

        let mut result = Vec::new();
        for row in rows {
            result.push(row.map_err(sqlite_err)?);
        }
        Ok(result)
    })
}

pub fn timeline_net_worth_monthly_deltas(db_path: &str) -> StorageResult<Vec<NetWorthDeltaRow>> {
    with_cached_read_connection(db_path, |conn| {
        let signed_expr = signed_minor_amount_expr("amount_base", "type");
        let sql = format!(
            "SELECT \
                month, \
                SUM(signed_delta) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_delta \
             FROM ( \
                SELECT \
                    strftime('%Y-%m', date) AS month, \
                    SUM({signed_expr}) AS signed_delta \
                FROM records \
                GROUP BY strftime('%Y-%m', date) \
             ) \
             ORDER BY month"
        );
        let mut stmt = conn.prepare(&sql).map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| {
                Ok(NetWorthDeltaRow {
                    month: row.get(0)?,
                    running_delta: minor_to_money_value(row.get::<_, i64>(1)?),
                })
            })
            .map_err(sqlite_err)?;

        let mut result = Vec::new();
        for row in rows {
            result.push(row.map_err(sqlite_err)?);
        }
        Ok(result)
    })
}
