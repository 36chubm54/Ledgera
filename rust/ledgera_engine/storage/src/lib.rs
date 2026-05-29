use ledgera_engine_core::{minor_to_money_value, rate_float_from_text};
use rusqlite::{Connection, OptionalExtension};
use std::cell::RefCell;
use std::collections::HashMap;

pub type StorageResult<T> = Result<T, String>;
pub type WalletBalanceRow = (i64, String, String, f64, f64);

#[derive(Debug, Clone, PartialEq)]
pub struct WalletRow {
    pub id: i64,
    pub name: String,
    pub currency: String,
    pub initial_balance: f64,
    pub system: bool,
    pub allow_negative: bool,
    pub is_active: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TransferRow {
    pub id: i64,
    pub from_wallet_id: i64,
    pub to_wallet_id: i64,
    pub date: String,
    pub amount_original: f64,
    pub currency: String,
    pub rate_at_operation: f64,
    pub amount_base: f64,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MandatoryExpenseRow {
    pub id: i64,
    pub wallet_id: i64,
    pub amount_original: f64,
    pub currency: String,
    pub rate_at_operation: f64,
    pub amount_base: f64,
    pub category: String,
    pub description: String,
    pub period: String,
    pub date: String,
    pub auto_pay: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RecordRow {
    pub id: i64,
    pub record_type: String,
    pub date: String,
    pub wallet_id: i64,
    pub transfer_id: Option<i64>,
    pub related_debt_id: Option<i64>,
    pub amount_original: f64,
    pub currency: String,
    pub rate_at_operation: f64,
    pub amount_base: f64,
    pub category: String,
    pub description: String,
    pub period: Option<String>,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CategoryMetricRow {
    pub category: String,
    pub total_base: f64,
    pub record_count: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TagMetricRow {
    pub tag: String,
    pub color: String,
    pub total_base: f64,
    pub record_count: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TagCoverageRow {
    pub tagged_count: i64,
    pub total_count: i64,
    pub coverage_pct: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MonthlySummaryRow {
    pub month: String,
    pub income: f64,
    pub expenses: f64,
    pub cashflow: f64,
    pub savings_rate: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MonthlyCashflowRow {
    pub month: String,
    pub income: f64,
    pub expenses: f64,
    pub cashflow: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MonthlyCumulativeRow {
    pub month: String,
    pub cumulative_income: f64,
    pub cumulative_expenses: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NetWorthDeltaRow {
    pub month: String,
    pub running_delta: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MetricsPeriodSnapshot {
    pub savings_rate: f64,
    pub burn_rate: f64,
    pub spending_by_category: Vec<CategoryMetricRow>,
    pub income_by_category: Vec<CategoryMetricRow>,
    pub spending_by_tag: Vec<TagMetricRow>,
    pub tag_coverage: TagCoverageRow,
    pub monthly_summary: Vec<MonthlySummaryRow>,
    pub monthly_cashflow: Vec<MonthlyCashflowRow>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MetricsRefreshSnapshot {
    pub savings_rate: f64,
    pub burn_rate: f64,
    pub spending_by_category: Vec<CategoryMetricRow>,
    pub income_by_category: Vec<CategoryMetricRow>,
    pub spending_by_tag: Vec<TagMetricRow>,
    pub monthly_summary: Vec<MonthlySummaryRow>,
}

mod metrics;
mod timeline;

pub use metrics::{
    metrics_period_snapshot, metrics_refresh_snapshot,
    metrics_burn_rate, metrics_income_by_category, metrics_monthly_summary, metrics_savings_rate,
    metrics_spending_by_category, metrics_spending_by_tag, metrics_tag_coverage,
};
pub use timeline::{
    timeline_cumulative_income_expense, timeline_monthly_cashflow,
    timeline_net_worth_monthly_deltas,
};

pub(crate) fn sqlite_err(err: rusqlite::Error) -> String {
    format!("sqlite error: {err}")
}

fn open_sqlite_connection(db_path: &str) -> StorageResult<Connection> {
    Connection::open(db_path).map_err(sqlite_err)
}

thread_local! {
    static READ_CONNECTIONS: RefCell<HashMap<String, Connection>> = RefCell::new(HashMap::new());
}

pub(crate) fn with_cached_read_connection<T>(
    db_path: &str,
    callback: impl FnOnce(&Connection) -> StorageResult<T>,
) -> StorageResult<T> {
    READ_CONNECTIONS.with(|connections| {
        let mut connections = connections.borrow_mut();
        if !connections.contains_key(db_path) {
            connections.insert(db_path.to_owned(), open_sqlite_connection(db_path)?);
        }
        let conn = connections
            .get(db_path)
            .ok_or_else(|| "sqlite connection cache miss".to_owned())?;
        callback(conn)
    })
}

pub fn storage_clear_read_connection_cache() {
    READ_CONNECTIONS.with(|connections| {
        connections.borrow_mut().clear();
    });
}

pub(crate) fn minor_amount_expr(column: &str) -> String {
    format!(
        "CASE \
         WHEN {column}_minor IS NOT NULL \
         AND ({column}_minor != 0 OR ROUND({column}, 2) = 0) \
         THEN {column}_minor \
         ELSE CAST(ROUND({column} * 100.0) AS INTEGER) \
         END"
    )
}

pub(crate) fn signed_minor_amount_expr(column: &str, type_column: &str) -> String {
    let amount_expr = minor_amount_expr(column);
    format!("CASE WHEN {type_column} = 'income' THEN {amount_expr} ELSE -{amount_expr} END")
}

pub(crate) fn round_money(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

pub(crate) fn limit_clause(limit: Option<i64>) -> String {
    match limit {
        Some(value) if value >= 0 => format!(" LIMIT {value}"),
        _ => String::new(),
    }
}

pub(crate) fn table_has_column(
    conn: &Connection,
    table: &str,
    column: &str,
) -> StorageResult<bool> {
    let mut stmt = conn
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(sqlite_err)?;
    for row in rows {
        if row.map_err(sqlite_err)? == column {
            return Ok(true);
        }
    }
    Ok(false)
}

fn money_value_from_sql_row(
    row: &rusqlite::Row<'_>,
    real_index: usize,
    minor_index: usize,
) -> rusqlite::Result<f64> {
    let minor_value: Option<i64> = row.get(minor_index)?;
    if let Some(minor) = minor_value {
        Ok(minor_to_money_value(minor))
    } else {
        row.get::<_, f64>(real_index)
    }
}

fn rate_value_from_sql_row(
    row: &rusqlite::Row<'_>,
    real_index: usize,
    text_index: usize,
) -> rusqlite::Result<f64> {
    let rate_text = row.get::<_, Option<String>>(text_index)?;
    if let Some(text) = rate_text {
        if text.trim().is_empty() {
            row.get::<_, f64>(real_index)
        } else {
            rate_float_from_text(text.trim()).map_err(|err| {
                rusqlite::Error::FromSqlConversionFailure(
                    text_index,
                    rusqlite::types::Type::Text,
                    Box::new(std::io::Error::other(err)),
                )
            })
        }
    } else {
        row.get::<_, f64>(real_index)
    }
}

pub fn wallet_balance_parts(
    db_path: &str,
    wallet_id: i64,
    up_to_date: Option<&str>,
) -> StorageResult<Option<(f64, String, f64)>> {
    let conn = open_sqlite_connection(db_path)?;
    let wallet_row = conn
        .query_row(
            "SELECT \
                COALESCE(initial_balance_minor, CAST(ROUND(initial_balance * 100.0) AS INTEGER), 0), \
                currency \
             FROM wallets \
             WHERE id = ?1 AND is_active = 1",
            [wallet_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?)),
        )
        .optional()
        .map_err(sqlite_err)?;
    let Some((initial_minor, currency)) = wallet_row else {
        return Ok(None);
    };

    let signed_expr = signed_minor_amount_expr("amount_base", "type");
    let delta_minor = if let Some(date) = up_to_date {
        let sql = format!(
            "SELECT COALESCE(SUM({signed_expr}), 0) \
             FROM records WHERE wallet_id = ?1 AND date <= ?2"
        );
        conn.query_row(&sql, (&wallet_id, &date), |row| row.get::<_, i64>(0))
            .map_err(sqlite_err)?
    } else {
        let sql =
            format!("SELECT COALESCE(SUM({signed_expr}), 0) FROM records WHERE wallet_id = ?1");
        conn.query_row(&sql, [wallet_id], |row| row.get::<_, i64>(0))
            .map_err(sqlite_err)?
    };

    Ok(Some((
        minor_to_money_value(initial_minor),
        currency,
        minor_to_money_value(delta_minor),
    )))
}

pub fn wallet_balance_rows(
    db_path: &str,
    up_to_date: Option<&str>,
) -> StorageResult<Vec<WalletBalanceRow>> {
    let conn = open_sqlite_connection(db_path)?;
    let signed_expr = signed_minor_amount_expr("r.amount_base", "r.type");
    let mut sql = format!(
        "SELECT \
            w.id, \
            w.name, \
            w.currency, \
            COALESCE(w.initial_balance_minor, CAST(ROUND(w.initial_balance * 100.0) AS INTEGER), 0) AS initial_minor, \
            COALESCE(SUM({signed_expr}), 0) AS delta_minor \
         FROM wallets AS w \
         LEFT JOIN records AS r ON r.wallet_id = w.id"
    );
    if up_to_date.is_some() {
        sql.push_str(" AND r.date <= ?1");
    }
    sql.push_str(
        " WHERE w.is_active = 1 GROUP BY w.id, w.name, w.currency, initial_minor ORDER BY w.id",
    );

    let mut stmt = conn.prepare(&sql).map_err(sqlite_err)?;
    let mapper = |row: &rusqlite::Row<'_>| -> rusqlite::Result<WalletBalanceRow> {
        let initial_minor: i64 = row.get(3)?;
        let delta_minor: i64 = row.get(4)?;
        Ok((
            row.get(0)?,
            row.get(1)?,
            row.get(2)?,
            minor_to_money_value(initial_minor),
            minor_to_money_value(delta_minor),
        ))
    };
    let mapped = if let Some(date) = up_to_date {
        stmt.query_map([date], mapper).map_err(sqlite_err)?
    } else {
        stmt.query_map([], mapper).map_err(sqlite_err)?
    };

    let mut rows = Vec::new();
    for row in mapped {
        rows.push(row.map_err(sqlite_err)?);
    }
    Ok(rows)
}

pub fn cashflow_sum(
    db_path: &str,
    record_type: &str,
    start_date: &str,
    end_date: &str,
) -> StorageResult<f64> {
    let conn = open_sqlite_connection(db_path)?;
    let amount_expr = minor_amount_expr("amount_base");
    let minor_total = if record_type == "expense" {
        let sql = format!(
            "SELECT COALESCE(SUM({amount_expr}), 0) \
             FROM records \
             WHERE type IN ('expense', 'mandatory_expense') \
               AND transfer_id IS NULL \
               AND date >= ?1 AND date <= ?2"
        );
        conn.query_row(&sql, (start_date, end_date), |row| row.get::<_, i64>(0))
            .map_err(sqlite_err)?
    } else {
        let sql = format!(
            "SELECT COALESCE(SUM({amount_expr}), 0) \
             FROM records \
             WHERE type = ?1 \
               AND transfer_id IS NULL \
               AND date >= ?2 AND date <= ?3"
        );
        conn.query_row(&sql, (record_type, start_date, end_date), |row| {
            row.get::<_, i64>(0)
        })
        .map_err(sqlite_err)?
    };
    Ok(minor_to_money_value(minor_total))
}

pub fn wallet_list_rows(db_path: &str) -> StorageResult<Vec<WalletRow>> {
    let conn = open_sqlite_connection(db_path)?;
    let mut stmt = conn
        .prepare(
            "SELECT
                id,
                name,
                currency,
                initial_balance,
                initial_balance_minor,
                system,
                allow_negative,
                is_active
             FROM wallets
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(WalletRow {
                id: row.get(0)?,
                name: row.get(1)?,
                currency: row.get(2)?,
                initial_balance: money_value_from_sql_row(row, 3, 4)?,
                system: row.get::<_, i64>(5)? != 0,
                allow_negative: row.get::<_, i64>(6)? != 0,
                is_active: row.get::<_, i64>(7)? != 0,
            })
        })
        .map_err(sqlite_err)?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(sqlite_err)?);
    }
    Ok(result)
}

pub fn transfer_list_rows(db_path: &str) -> StorageResult<Vec<TransferRow>> {
    let conn = open_sqlite_connection(db_path)?;
    let mut stmt = conn
        .prepare(
            "SELECT
                id,
                from_wallet_id,
                to_wallet_id,
                date,
                amount_original,
                amount_original_minor,
                currency,
                rate_at_operation,
                rate_at_operation_text,
                amount_base,
                amount_base_minor,
                description
             FROM transfers
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(TransferRow {
                id: row.get(0)?,
                from_wallet_id: row.get(1)?,
                to_wallet_id: row.get(2)?,
                date: row.get(3)?,
                amount_original: money_value_from_sql_row(row, 4, 5)?,
                currency: row.get(6)?,
                rate_at_operation: rate_value_from_sql_row(row, 7, 8)?,
                amount_base: money_value_from_sql_row(row, 9, 10)?,
                description: row.get(11)?,
            })
        })
        .map_err(sqlite_err)?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(sqlite_err)?);
    }
    Ok(result)
}

pub fn transfer_id_by_record_index(db_path: &str, index: i64) -> StorageResult<Option<i64>> {
    if index < 0 {
        return Ok(None);
    }
    let conn = open_sqlite_connection(db_path)?;
    conn.query_row(
        "SELECT transfer_id
         FROM records
         ORDER BY id
         LIMIT 1 OFFSET ?1",
        [index],
        |row| row.get::<_, Option<i64>>(0),
    )
    .optional()
    .map_err(sqlite_err)
    .map(|value| value.flatten())
}

fn mandatory_expense_select_sql(conn: &Connection, filter_by_id: bool) -> StorageResult<String> {
    let mut stmt = conn
        .prepare("PRAGMA table_info(mandatory_expenses)")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(sqlite_err)?;
    let mut has_date = false;
    let mut has_auto_pay = false;
    for row in rows {
        let name = row.map_err(sqlite_err)?;
        if name == "date" {
            has_date = true;
        } else if name == "auto_pay" {
            has_auto_pay = true;
        }
    }

    let mut sql = String::from(
        "SELECT
            id,
            wallet_id,
            amount_original,
            amount_original_minor,
            currency,
            rate_at_operation,
            rate_at_operation_text,
            amount_base,
            amount_base_minor,
            category,
            description,
            period",
    );
    if has_date {
        sql.push_str(",\n            date");
    } else {
        sql.push_str(",\n            NULL AS date");
    }
    if has_auto_pay {
        sql.push_str(",\n            auto_pay");
    } else {
        sql.push_str(",\n            0 AS auto_pay");
    }
    sql.push_str("\n         FROM mandatory_expenses");
    if filter_by_id {
        sql.push_str("\n         WHERE id = ?1");
    }
    sql.push_str("\n         ORDER BY id");
    Ok(sql)
}

fn mandatory_expense_row_dicts(
    conn: &Connection,
    sql: &str,
    params: &[&dyn rusqlite::ToSql],
) -> StorageResult<Vec<MandatoryExpenseRow>> {
    let mut stmt = conn.prepare(sql).map_err(sqlite_err)?;
    let rows = stmt
        .query_map(params, |row| {
            Ok(MandatoryExpenseRow {
                id: row.get(0)?,
                wallet_id: row.get(1)?,
                amount_original: money_value_from_sql_row(row, 2, 3)?,
                currency: row.get(4)?,
                rate_at_operation: rate_value_from_sql_row(row, 5, 6)?,
                amount_base: money_value_from_sql_row(row, 7, 8)?,
                category: row.get(9)?,
                description: row.get(10)?,
                period: row.get(11)?,
                date: row.get::<_, Option<String>>(12)?.unwrap_or_default(),
                auto_pay: row.get::<_, i64>(13)? != 0,
            })
        })
        .map_err(sqlite_err)?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(sqlite_err)?);
    }
    Ok(result)
}

pub fn mandatory_expense_rows(db_path: &str) -> StorageResult<Vec<MandatoryExpenseRow>> {
    let conn = open_sqlite_connection(db_path)?;
    let sql = mandatory_expense_select_sql(&conn, false)?;
    mandatory_expense_row_dicts(&conn, &sql, &[])
}

pub fn mandatory_expense_row(
    db_path: &str,
    expense_id: i64,
) -> StorageResult<Option<MandatoryExpenseRow>> {
    let conn = open_sqlite_connection(db_path)?;
    let sql = mandatory_expense_select_sql(&conn, true)?;
    let mut rows = mandatory_expense_row_dicts(&conn, &sql, &[&expense_id])?;
    Ok(rows.pop())
}

fn record_row_dicts(
    conn: &Connection,
    sql: &str,
    params: &[&dyn rusqlite::ToSql],
) -> StorageResult<Vec<RecordRow>> {
    let mut tags_by_record: HashMap<i64, Vec<String>> = HashMap::new();
    let mut tag_stmt = conn
        .prepare(
            "SELECT rt.record_id, t.name
             FROM record_tags AS rt
             JOIN tags AS t ON t.id = rt.tag_id
             ORDER BY rt.record_id, t.name COLLATE NOCASE, t.name",
        )
        .map_err(sqlite_err)?;
    let tag_rows = tag_stmt
        .query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(sqlite_err)?;
    for row in tag_rows {
        let (record_id, tag_name) = row.map_err(sqlite_err)?;
        tags_by_record.entry(record_id).or_default().push(tag_name);
    }

    let mut stmt = conn.prepare(sql).map_err(sqlite_err)?;
    let rows = stmt
        .query_map(params, |row| {
            let record_id: i64 = row.get(0)?;
            Ok(RecordRow {
                id: record_id,
                record_type: row.get(1)?,
                date: row.get(2)?,
                wallet_id: row.get(3)?,
                transfer_id: row.get(4)?,
                related_debt_id: row.get(5)?,
                amount_original: money_value_from_sql_row(row, 6, 7)?,
                currency: row.get(8)?,
                rate_at_operation: rate_value_from_sql_row(row, 9, 10)?,
                amount_base: money_value_from_sql_row(row, 11, 12)?,
                category: row.get(13)?,
                description: row.get(14)?,
                period: row.get(15)?,
                tags: tags_by_record.remove(&record_id).unwrap_or_default(),
            })
        })
        .map_err(sqlite_err)?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(sqlite_err)?);
    }
    Ok(result)
}

const RECORD_SELECT: &str = "SELECT
    id,
    type,
    date,
    wallet_id,
    transfer_id,
    related_debt_id,
    amount_original,
    amount_original_minor,
    currency,
    rate_at_operation,
    rate_at_operation_text,
    amount_base,
    amount_base_minor,
    category,
    description,
    period
 FROM records";

pub fn record_list_rows(db_path: &str) -> StorageResult<Vec<RecordRow>> {
    let conn = open_sqlite_connection(db_path)?;
    record_row_dicts(&conn, &format!("{RECORD_SELECT} ORDER BY id"), &[])
}

pub fn record_get_row(db_path: &str, record_id: i64) -> StorageResult<Option<RecordRow>> {
    let conn = open_sqlite_connection(db_path)?;
    let mut rows = record_row_dicts(
        &conn,
        &format!("{RECORD_SELECT} WHERE id = ?1"),
        &[&record_id],
    )?;
    Ok(rows.pop())
}

pub fn record_rows_by_tag(db_path: &str, tag_name: &str) -> StorageResult<Vec<RecordRow>> {
    let conn = open_sqlite_connection(db_path)?;
    record_row_dicts(
        &conn,
        &format!(
            "{RECORD_SELECT}
         WHERE EXISTS (
            SELECT 1
            FROM record_tags AS rt
            JOIN tags AS t ON t.id = rt.tag_id
            WHERE rt.record_id = records.id
              AND lower(t.name) = lower(?1)
         )
         ORDER BY id"
        ),
        &[&tag_name],
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn create_balance_test_db() -> String {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("ledgera_storage_test_{unique}.db"));
        let conn = Connection::open(&path).unwrap();
        conn.execute_batch(
            "
            CREATE TABLE wallets (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                currency TEXT NOT NULL,
                initial_balance REAL NOT NULL DEFAULT 0,
                initial_balance_minor INTEGER DEFAULT NULL,
                system INTEGER NOT NULL DEFAULT 0,
                allow_negative INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE transfers (
                id INTEGER PRIMARY KEY,
                from_wallet_id INTEGER NOT NULL,
                to_wallet_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount_original REAL NOT NULL,
                amount_original_minor INTEGER DEFAULT NULL,
                currency TEXT NOT NULL,
                rate_at_operation REAL NOT NULL,
                rate_at_operation_text TEXT DEFAULT NULL,
                amount_base REAL NOT NULL,
                amount_base_minor INTEGER DEFAULT NULL,
                description TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE mandatory_expenses (
                id INTEGER PRIMARY KEY,
                wallet_id INTEGER NOT NULL,
                amount_original REAL NOT NULL,
                amount_original_minor INTEGER DEFAULT NULL,
                currency TEXT NOT NULL,
                rate_at_operation REAL NOT NULL,
                rate_at_operation_text TEXT DEFAULT NULL,
                amount_base REAL NOT NULL,
                amount_base_minor INTEGER DEFAULT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                period TEXT DEFAULT NULL,
                date TEXT DEFAULT NULL,
                auto_pay INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE records (
                id INTEGER PRIMARY KEY,
                type TEXT NOT NULL,
                date TEXT NOT NULL,
                wallet_id INTEGER NOT NULL,
                transfer_id INTEGER DEFAULT NULL,
                related_debt_id INTEGER DEFAULT NULL,
                amount_original REAL NOT NULL DEFAULT 0,
                amount_original_minor INTEGER DEFAULT NULL,
                currency TEXT NOT NULL DEFAULT 'KZT',
                rate_at_operation REAL NOT NULL DEFAULT 1,
                rate_at_operation_text TEXT DEFAULT NULL,
                amount_base REAL NOT NULL,
                amount_base_minor INTEGER DEFAULT NULL,
                category TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                period TEXT DEFAULT NULL
            );
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE record_tags (
                record_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL
            );
            ",
        )
        .unwrap();
        conn.execute(
            "INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor, system, allow_negative, is_active
             ) VALUES (1, 'Cash', 'KZT', 1000.0, 100000, 1, 0, 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor, system, allow_negative, is_active
             ) VALUES (2, 'Card', 'KZT', 500.0, 50000, 0, 1, 1)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor, system, allow_negative, is_active
             ) VALUES (3, 'Inactive', 'KZT', 999.0, 99900, 0, 0, 0)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO transfers (
                id, from_wallet_id, to_wallet_id, date, amount_original, amount_original_minor,
                currency, rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor, description
             ) VALUES (
                1, 1, 2, '2026-01-04', 300.0, 30000,
                'KZT', 1.0, '1.000000', 300.0, 30000, 'Move to card'
             )",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO mandatory_expenses (
                id, wallet_id, amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor,
                category, description, period, date, auto_pay
             ) VALUES (
                1, 1, 40.0, 4000, 'KZT',
                1.0, '1.000000', 40.0, 4000,
                'Rent', 'Monthly rent', 'monthly', '2026-01-15', 1
             )",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (id, type, date, wallet_id, transfer_id, amount_original, amount_original_minor, amount_base, amount_base_minor, category, description)
             VALUES (1, 'income', '2026-01-01', 1, NULL, 200.0, 20000, 200.0, 20000, 'Salary', 'January')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (id, type, date, wallet_id, transfer_id, amount_original, amount_original_minor, amount_base, amount_base_minor, category, description)
             VALUES (2, 'expense', '2026-01-02', 1, NULL, 50.0, 5000, 50.0, 5000, 'Food', 'Groceries')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (id, type, date, wallet_id, transfer_id, amount_original, amount_original_minor, amount_base, amount_base_minor, category, description)
             VALUES (3, 'mandatory_expense', '2026-01-03', 2, NULL, 25.0, 2500, 25.0, 2500, 'Rent', 'Monthly')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (id, type, date, wallet_id, transfer_id, amount_original, amount_original_minor, amount_base, amount_base_minor)
             VALUES (4, 'expense', '2026-01-04', 1, 1, 300.0, 30000, 300.0, 30000)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (id, type, date, wallet_id, transfer_id, amount_original, amount_original_minor, amount_base, amount_base_minor)
             VALUES (5, 'income', '2026-01-04', 2, 1, 300.0, 30000, 300.0, 30000)",
            [],
        )
        .unwrap();
        conn.execute("INSERT INTO tags (id, name) VALUES (1, 'food')", [])
            .unwrap();
        conn.execute(
            "INSERT INTO record_tags (record_id, tag_id) VALUES (2, 1)",
            [],
        )
        .unwrap();
        path.to_string_lossy().into_owned()
    }

    fn remove_test_db(path: &str) {
        let _ = fs::remove_file(PathBuf::from(path));
    }

    #[test]
    fn balance_rows_return_active_wallets_only() {
        let db_path = create_balance_test_db();
        let rows = wallet_balance_rows(&db_path, Some("2026-01-03")).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(
            rows[0],
            (1, "Cash".to_owned(), "KZT".to_owned(), 1000.0, 150.0)
        );
        assert_eq!(
            rows[1],
            (2, "Card".to_owned(), "KZT".to_owned(), 500.0, -25.0)
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn cashflow_excludes_transfer_linked_records() {
        let db_path = create_balance_test_db();
        assert_eq!(
            cashflow_sum(&db_path, "income", "2026-01-01", "2026-01-31").unwrap(),
            200.0
        );
        assert_eq!(
            cashflow_sum(&db_path, "expense", "2026-01-01", "2026-01-31").unwrap(),
            75.0
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn read_rows_preserve_contract() {
        let db_path = create_balance_test_db();
        assert_eq!(
            wallet_list_rows(&db_path).unwrap()[0].initial_balance,
            1000.0
        );
        assert_eq!(
            transfer_list_rows(&db_path).unwrap()[0].amount_original,
            300.0
        );
        assert_eq!(transfer_id_by_record_index(&db_path, 3).unwrap(), Some(1));
        assert_eq!(
            mandatory_expense_rows(&db_path).unwrap()[0].category,
            "Rent"
        );
        assert_eq!(record_rows_by_tag(&db_path, "food").unwrap()[0].id, 2);
        assert_eq!(
            record_get_row(&db_path, 1).unwrap().unwrap().category,
            "Salary"
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn metrics_helpers_match_python_semantics() {
        let db_path = create_balance_test_db();
        assert_eq!(
            metrics_savings_rate(&db_path, "2026-01-01", "2026-01-31").unwrap(),
            62.5
        );
        assert_eq!(
            metrics_burn_rate(&db_path, "2026-01-01", "2026-01-31", 31).unwrap(),
            2.42
        );
        assert_eq!(
            metrics_spending_by_category(&db_path, "2026-01-01", "2026-01-31", Some(1)).unwrap()[0],
            CategoryMetricRow {
                category: "Food".to_owned(),
                total_base: 50.0,
                record_count: 1,
            }
        );
        assert_eq!(
            metrics_income_by_category(&db_path, "2026-01-01", "2026-01-31", None).unwrap()[0]
                .category,
            "Salary"
        );
        assert_eq!(
            metrics_spending_by_tag(&db_path, "2026-01-01", "2026-01-31", None).unwrap()[0],
            TagMetricRow {
                tag: "food".to_owned(),
                color: "".to_owned(),
                total_base: 50.0,
                record_count: 1,
            }
        );
        assert_eq!(
            metrics_tag_coverage(&db_path, "2026-01-01", "2026-01-31").unwrap(),
            TagCoverageRow {
                tagged_count: 1,
                total_count: 2,
                coverage_pct: 50.0,
            }
        );
        assert_eq!(
            metrics_monthly_summary(&db_path, None, None).unwrap()[0],
            MonthlySummaryRow {
                month: "2026-01".to_owned(),
                income: 200.0,
                expenses: 75.0,
                cashflow: 125.0,
                savings_rate: 62.5,
            }
        );
        let snapshot =
            metrics_period_snapshot(&db_path, "2026-01-01", "2026-01-31", 31, Some(1), Some(1))
                .unwrap();
        assert_eq!(snapshot.savings_rate, 62.5);
        assert_eq!(snapshot.burn_rate, 2.42);
        assert_eq!(snapshot.spending_by_category.len(), 1);
        assert_eq!(snapshot.income_by_category[0].category, "Salary");
        assert_eq!(snapshot.spending_by_tag[0].tag, "food");
        assert_eq!(snapshot.tag_coverage.coverage_pct, 50.0);
        assert_eq!(snapshot.monthly_summary[0].cashflow, 125.0);
        assert_eq!(snapshot.monthly_cashflow[0].cashflow, 125.0);
        remove_test_db(&db_path);
    }

    #[test]
    fn timeline_helpers_match_python_semantics() {
        let db_path = create_balance_test_db();
        assert_eq!(
            timeline_monthly_cashflow(&db_path, None, None).unwrap()[0],
            MonthlyCashflowRow {
                month: "2026-01".to_owned(),
                income: 200.0,
                expenses: 75.0,
                cashflow: 125.0,
            }
        );
        assert_eq!(
            timeline_cumulative_income_expense(&db_path).unwrap()[0],
            MonthlyCumulativeRow {
                month: "2026-01".to_owned(),
                cumulative_income: 200.0,
                cumulative_expenses: 75.0,
            }
        );
        assert_eq!(
            timeline_net_worth_monthly_deltas(&db_path).unwrap()[0],
            NetWorthDeltaRow {
                month: "2026-01".to_owned(),
                running_delta: 125.0,
            }
        );
        remove_test_db(&db_path);
    }
}
