mod csv;
mod excel;
mod tag_palette;

use calamine::{Data, Reader, open_workbook_auto};
use csv::{normalize_tabular_key, read_csv_rows, write_csv_rows};
use excel::StyledWorksheet;
use ledgera_engine_core::{
    minor_to_money_value, quantize_money_text, quantize_rate_text, rate_float_from_text,
    to_minor_units,
};
use rusqlite::{Connection, OptionalExtension};
use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
pub use tag_palette::{NO_COLOR, TAG_PALETTE, is_valid_tag_color};
#[cfg(windows)]
use windows_sys::Win32::Storage::FileSystem::{
    MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
};
#[cfg(windows)]
use windows_sys::Win32::{Foundation::SYSTEMTIME, System::SystemInformation::GetLocalTime};

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
pub struct WalletDeleteResult {
    pub wallet_id: i64,
    pub action: String,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct OperationDeleteResult {
    pub deleted_records: i64,
    pub deleted_transfers: i64,
    pub deleted_debt_linked_records: i64,
    pub skipped_records: i64,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct OperationImportResult {
    pub imported: i64,
    pub skipped: i64,
    pub errors: Vec<String>,
    pub dry_run: bool,
    pub blocking_errors: bool,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct OperationExportResult {
    pub exported_rows: i64,
    pub path: String,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct MandatoryImportResult {
    pub imported: i64,
    pub skipped: i64,
    pub errors: Vec<String>,
    pub dry_run: bool,
    pub blocking_errors: bool,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct MandatoryExportResult {
    pub exported_rows: i64,
    pub path: String,
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
pub struct MandatoryTemplateCreatePayload {
    pub wallet_id: i64,
    pub amount_original: String,
    pub currency: String,
    pub rate_at_operation: String,
    pub amount_base: String,
    pub category: String,
    pub description: String,
    pub period: String,
    pub date: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MandatoryTemplateUpdatePayload {
    pub wallet_id: i64,
    pub amount_base: String,
    pub period: String,
    pub date: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MandatoryAddToRecordsPayload {
    pub template_id: i64,
    pub date: String,
    pub wallet_id: i64,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct MandatoryAutoPayResult {
    pub created_records: Vec<RecordRow>,
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

#[derive(Debug, Clone, Default, PartialEq)]
pub struct RecordFilterPayload {
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub wallet_id: Option<i64>,
    pub record_type: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TagColorAssignment {
    pub name: String,
    pub color: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TagColorRow {
    pub name: String,
    pub color: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StandaloneRecordCreatePayload {
    pub record_type: String,
    pub date: String,
    pub wallet_id: i64,
    pub amount_original: String,
    pub currency: String,
    pub rate_at_operation: String,
    pub amount_base: String,
    pub category: String,
    pub description: String,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct StandaloneRecordUpdatePayload {
    pub record_type: String,
    pub date: String,
    pub wallet_id: i64,
    pub amount_original: String,
    pub currency: String,
    pub rate_at_operation: String,
    pub amount_base: String,
    pub category: String,
    pub description: String,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TransferCreatePayload {
    pub from_wallet_id: i64,
    pub to_wallet_id: i64,
    pub date: String,
    pub amount: String,
    pub currency: String,
    pub description: String,
    pub commission_amount: String,
    pub commission_currency: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TransferUpdatePayload {
    pub from_wallet_id: i64,
    pub to_wallet_id: i64,
    pub date: String,
    pub amount: String,
    pub currency: String,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletCreatePayload {
    pub name: String,
    pub currency: String,
    pub initial_balance: String,
    pub allow_negative: bool,
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

mod audit;
mod metrics;
mod planning;
mod reporting;
mod timeline;

pub use audit::{AuditFindingRow, audit_run, audit_run_for_date};
pub use metrics::{
    metrics_burn_rate, metrics_income_by_category, metrics_monthly_summary,
    metrics_period_snapshot, metrics_refresh_snapshot, metrics_savings_rate,
    metrics_spending_by_category, metrics_spending_by_tag, metrics_tag_coverage,
};
pub use planning::{
    BudgetCreatePayload, BudgetPayload, BudgetResultPayload, DebtCreatePayload, DebtPayload,
    DebtPaymentPayload, DebtPaymentRequestPayload, DebtRecalculatePayload, DebtRecordPayload,
    DistributionItemPayload, DistributionMonthlyPayload, DistributionSubitemPayload,
    DistributionValidationRow, FrozenDistributionPayload, budget_batch_spent_minor, budget_create,
    budget_delete, budget_overlap_exists, budget_replace_rows, budget_results, budget_rows,
    budget_spent_minor, budget_update_limit, debt_close_validated, debt_create,
    debt_create_obligation, debt_delete, debt_delete_payment, debt_payment_rows,
    debt_payment_total_minor, debt_recalculate_payload, debt_register_payment,
    debt_register_payment_validated, debt_register_write_off_validated, debt_replace_rows,
    debt_rows, debt_validate_payment_amount, distribution_available_months,
    distribution_create_item, distribution_create_subitem, distribution_delete_item,
    distribution_delete_subitem, distribution_frozen_rows, distribution_history_months,
    distribution_is_month_auto_fixed, distribution_is_month_fixed, distribution_item_rows,
    distribution_monthly_payload, distribution_net_income_for_period,
    distribution_replace_frozen_rows, distribution_replace_structure, distribution_subitem_rows,
    distribution_unfreeze_month, distribution_update_item_name, distribution_update_item_order,
    distribution_update_item_pct, distribution_update_subitem_name,
    distribution_update_subitem_order, distribution_update_subitem_pct,
    distribution_validate_structure, distribution_write_frozen_row,
};
pub use reporting::{
    ReportCategoryRow, ReportDebtRow, ReportExportResult, ReportFilters, ReportMonthlyRow,
    ReportOperationRow, ReportResult, ReportSummary, ReportTagRow, report_export_csv,
    report_export_pdf, report_export_xlsx, report_generate,
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

pub fn wallet_balance_row(
    db_path: &str,
    wallet_id: i64,
) -> StorageResult<Option<WalletBalanceRow>> {
    if wallet_id <= 0 {
        return Ok(None);
    }
    let conn = open_sqlite_connection(db_path)?;
    let signed_expr = signed_minor_amount_expr("r.amount_base", "r.type");
    let sql = format!(
        "SELECT \
            w.id, \
            w.name, \
            w.currency, \
            COALESCE(w.initial_balance_minor, CAST(ROUND(w.initial_balance * 100.0) AS INTEGER), 0) AS initial_minor, \
            COALESCE(SUM({signed_expr}), 0) AS delta_minor \
         FROM wallets AS w \
         LEFT JOIN records AS r ON r.wallet_id = w.id \
         WHERE w.is_active = 1 AND w.id = ?1 \
         GROUP BY w.id, w.name, w.currency, initial_minor"
    );
    conn.query_row(&sql, [wallet_id], |row| {
        let initial_minor: i64 = row.get(3)?;
        let delta_minor: i64 = row.get(4)?;
        Ok((
            row.get(0)?,
            row.get(1)?,
            row.get(2)?,
            minor_to_money_value(initial_minor),
            minor_to_money_value(delta_minor),
        ))
    })
    .optional()
    .map_err(sqlite_err)
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

pub fn create_wallet(db_path: &str, payload: &WalletCreatePayload) -> StorageResult<WalletRow> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    let name = payload.name.trim();
    if name.is_empty() {
        return Err("Wallet name is required".to_owned());
    }
    if wallet_name_exists_in_tx(&tx, name)? {
        return Err(format!("Wallet name already exists: {name}"));
    }
    let currency = payload.currency.trim().to_uppercase();
    validate_currency_code(&currency)?;
    let base_currency = base_currency_code_in_tx(&tx)?;
    validate_wallet_base_currency_only(&currency, &base_currency)?;

    let initial_balance_minor = to_minor_units(&payload.initial_balance)?;
    if initial_balance_minor < 0 {
        return Err("Initial balance must be zero or a positive number".to_owned());
    }
    let initial_balance = quantize_money_text(&payload.initial_balance)?
        .parse::<f64>()
        .map_err(|_| "invalid initial_balance".to_owned())?;
    let is_first_wallet = tx
        .query_row("SELECT COUNT(*) FROM wallets", [], |row| {
            row.get::<_, i64>(0)
        })
        .map_err(sqlite_err)?
        == 0;

    tx.execute(
        "INSERT INTO wallets (
            name,
            currency,
            initial_balance,
            initial_balance_minor,
            system,
            allow_negative,
            is_active
        )
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1)",
        (
            name,
            currency.as_str(),
            initial_balance,
            initial_balance_minor,
            i64::from(is_first_wallet),
            i64::from(payload.allow_negative),
        ),
    )
    .map_err(sqlite_err)?;
    let wallet_id = tx.last_insert_rowid();
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    wallet_list_rows(db_path)?
        .into_iter()
        .find(|row| row.id == wallet_id)
        .ok_or_else(|| format!("Wallet not found: {wallet_id}"))
}

fn wallet_name_exists_in_tx(tx: &rusqlite::Transaction<'_>, name: &str) -> StorageResult<bool> {
    tx.query_row(
        "SELECT 1 FROM wallets WHERE LOWER(TRIM(name)) = LOWER(?1) LIMIT 1",
        [name],
        |_| Ok(()),
    )
    .optional()
    .map(|row| row.is_some())
    .map_err(sqlite_err)
}

pub fn delete_wallet(db_path: &str, wallet_id: i64) -> StorageResult<WalletDeleteResult> {
    if wallet_id <= 0 {
        return Err("Wallet id is required".to_owned());
    }
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    let wallet = tx
        .query_row(
            "SELECT system, is_active FROM wallets WHERE id = ?1",
            [wallet_id],
            |row| Ok((row.get::<_, i64>(0)? != 0, row.get::<_, i64>(1)? != 0)),
        )
        .optional()
        .map_err(sqlite_err)?;
    let Some((system, active)) = wallet else {
        return Err(format!("Wallet not found: {wallet_id}"));
    };
    if system {
        return Err("System wallet cannot be deleted".to_owned());
    }
    if !active {
        return Err(format!("Wallet already inactive: {wallet_id}"));
    }

    let balance_minor = wallet_balance_minor_in_tx(&tx, wallet_id)?;
    if balance_minor != 0 {
        return Err("Wallet with non-zero balance cannot be deleted".to_owned());
    }

    let history_count = wallet_history_count_in_tx(&tx, wallet_id)?;
    let action = if history_count == 0 {
        tx.execute("DELETE FROM wallets WHERE id = ?1", [wallet_id])
            .map_err(sqlite_err)?;
        reset_sqlite_sequence_to_max_id_in_tx(&tx, "wallets")?;
        "hard_deleted"
    } else {
        tx.execute(
            "UPDATE wallets SET is_active = 0 WHERE id = ?1",
            [wallet_id],
        )
        .map_err(sqlite_err)?;
        "soft_deleted"
    };

    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(WalletDeleteResult {
        wallet_id,
        action: action.to_owned(),
    })
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

pub fn transfer_get_row(db_path: &str, transfer_id: i64) -> StorageResult<Option<TransferRow>> {
    if transfer_id <= 0 {
        return Ok(None);
    }
    Ok(transfer_list_rows(db_path)?
        .into_iter()
        .find(|row| row.id == transfer_id))
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

pub fn create_transfer(
    db_path: &str,
    payload: &TransferCreatePayload,
) -> StorageResult<TransferRow> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    if payload.from_wallet_id <= 0 || payload.to_wallet_id <= 0 {
        return Err("Transfer wallets are required".to_owned());
    }
    if payload.from_wallet_id == payload.to_wallet_id {
        return Err("Transfer wallets must be different".to_owned());
    }
    if payload.date.trim().is_empty() {
        return Err("Transfer date is required".to_owned());
    }
    validate_ymd_date(payload.date.trim())?;

    let from_wallet = active_wallet_in_tx(&tx, payload.from_wallet_id, "source")?;
    active_wallet_in_tx(&tx, payload.to_wallet_id, "target")?;

    let base_currency = base_currency_code_in_tx(&tx)?;
    let currency = payload.currency.trim().to_uppercase();
    validate_currency_code(&currency)?;
    validate_transfer_base_currency_only(&currency, &base_currency)?;
    let commission_currency = if payload.commission_currency.trim().is_empty() {
        base_currency.clone()
    } else {
        payload.commission_currency.trim().to_uppercase()
    };
    validate_currency_code(&commission_currency)?;
    validate_transfer_base_currency_only(&commission_currency, &base_currency)?;

    let amount_minor = to_minor_units(&payload.amount)?;
    if amount_minor <= 0 {
        return Err("Transfer amount must be positive".to_owned());
    }
    let commission_text = payload.commission_amount.trim();
    let commission_minor = if commission_text.is_empty() {
        0
    } else {
        to_minor_units(commission_text)?
    };
    if commission_minor < 0 {
        return Err("Commission amount must be non-negative".to_owned());
    }
    if !from_wallet.allow_negative {
        let balance_minor = wallet_balance_minor_in_tx(&tx, payload.from_wallet_id)?;
        if balance_minor - amount_minor - commission_minor < 0 {
            return Err("Insufficient funds in source wallet".to_owned());
        }
    }

    let amount_text = quantize_money_text(&payload.amount)?;
    let amount_value = amount_text
        .parse::<f64>()
        .map_err(|_| "invalid transfer amount".to_owned())?;
    let commission_value = if commission_minor > 0 {
        quantize_money_text(commission_text)?
            .parse::<f64>()
            .map_err(|_| "invalid commission amount".to_owned())?
    } else {
        0.0
    };
    let rate_text = quantize_rate_text("1")?;
    let rate_value = rate_text
        .parse::<f64>()
        .map_err(|_| "invalid transfer rate".to_owned())?;
    let description = payload.description.trim();

    tx.execute(
        "INSERT INTO transfers (
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
        )
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
        (
            payload.from_wallet_id,
            payload.to_wallet_id,
            payload.date.trim(),
            amount_value,
            amount_minor,
            currency.as_str(),
            rate_value,
            rate_text.as_str(),
            amount_value,
            amount_minor,
            description,
        ),
    )
    .map_err(sqlite_err)?;
    let transfer_id = tx.last_insert_rowid();

    insert_transfer_record_in_tx(
        &tx,
        "expense",
        payload.date.trim(),
        payload.from_wallet_id,
        Some(transfer_id),
        amount_value,
        amount_minor,
        currency.as_str(),
        rate_value,
        rate_text.as_str(),
        "Transfer",
        description,
    )?;
    insert_transfer_record_in_tx(
        &tx,
        "income",
        payload.date.trim(),
        payload.to_wallet_id,
        Some(transfer_id),
        amount_value,
        amount_minor,
        currency.as_str(),
        rate_value,
        rate_text.as_str(),
        "Transfer",
        description,
    )?;
    if commission_minor > 0 {
        insert_transfer_record_in_tx(
            &tx,
            "expense",
            payload.date.trim(),
            payload.from_wallet_id,
            None,
            commission_value,
            commission_minor,
            commission_currency.as_str(),
            rate_value,
            rate_text.as_str(),
            "Commission",
            &format!("[transfer:{transfer_id}]"),
        )?;
    }
    let transfer_id_map = normalize_transfer_ids_in_tx(&tx)?;
    let normalized_transfer_id = transfer_id_map
        .get(&transfer_id)
        .copied()
        .unwrap_or(transfer_id);
    normalize_record_ids_in_tx(&tx)?;

    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    transfer_list_rows(db_path)?
        .into_iter()
        .find(|row| row.id == normalized_transfer_id)
        .ok_or_else(|| format!("Transfer not found: {normalized_transfer_id}"))
}

pub fn update_transfer(
    db_path: &str,
    transfer_id: i64,
    payload: &TransferUpdatePayload,
) -> StorageResult<TransferRow> {
    if transfer_id <= 0 {
        return Err("Transfer id is required".to_owned());
    }
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    if payload.from_wallet_id <= 0 || payload.to_wallet_id <= 0 {
        return Err("Transfer wallets are required".to_owned());
    }
    if payload.from_wallet_id == payload.to_wallet_id {
        return Err("Transfer wallets must be different".to_owned());
    }
    if payload.date.trim().is_empty() {
        return Err("Transfer date is required".to_owned());
    }
    validate_ymd_date(payload.date.trim())?;

    let from_wallet = active_wallet_in_tx(&tx, payload.from_wallet_id, "source")?;
    active_wallet_in_tx(&tx, payload.to_wallet_id, "target")?;

    let base_currency = base_currency_code_in_tx(&tx)?;
    let currency = payload.currency.trim().to_uppercase();
    validate_currency_code(&currency)?;
    validate_transfer_base_currency_only(&currency, &base_currency)?;

    let amount_minor = to_minor_units(&payload.amount)?;
    if amount_minor <= 0 {
        return Err("Transfer amount must be positive".to_owned());
    }
    let amount_text = quantize_money_text(&payload.amount)?;
    let amount_value = amount_text
        .parse::<f64>()
        .map_err(|_| "invalid transfer amount".to_owned())?;
    let rate_text = quantize_rate_text("1")?;
    let rate_value = rate_text
        .parse::<f64>()
        .map_err(|_| "invalid transfer rate".to_owned())?;
    let description = payload.description.trim();

    let existing = tx
        .query_row(
            "SELECT id FROM transfers WHERE id = ?1",
            [transfer_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .map_err(sqlite_err)?;
    if existing.is_none() {
        return Err(format!("Transfer not found: {transfer_id}"));
    }

    let linked = transfer_linked_record_ids_in_tx(&tx, transfer_id)?;
    let commission_marker = format!("[transfer:{transfer_id}]");
    let commission_minor = tx
        .query_row(
            "SELECT COALESCE(SUM(COALESCE(amount_base_minor, CAST(ROUND(amount_base * 100.0) AS INTEGER))), 0)
             FROM records
             WHERE transfer_id IS NULL
               AND description = ?1",
            [commission_marker.as_str()],
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)?;

    if !from_wallet.allow_negative {
        let balance_minor = wallet_balance_minor_excluding_transfer_in_tx(
            &tx,
            payload.from_wallet_id,
            transfer_id,
        )?;
        if balance_minor - amount_minor - commission_minor < 0 {
            return Err("Insufficient funds in source wallet".to_owned());
        }
    }

    tx.execute(
        "UPDATE transfers
         SET from_wallet_id = ?1,
             to_wallet_id = ?2,
             date = ?3,
             amount_original = ?4,
             amount_original_minor = ?5,
             currency = ?6,
             rate_at_operation = ?7,
             rate_at_operation_text = ?8,
             amount_base = ?9,
             amount_base_minor = ?10,
             description = ?11
         WHERE id = ?12",
        (
            payload.from_wallet_id,
            payload.to_wallet_id,
            payload.date.trim(),
            amount_value,
            amount_minor,
            currency.as_str(),
            rate_value,
            rate_text.as_str(),
            amount_value,
            amount_minor,
            description,
            transfer_id,
        ),
    )
    .map_err(sqlite_err)?;

    tx.execute(
        "UPDATE records
         SET date = ?1,
             wallet_id = ?2,
             amount_original = ?3,
             amount_original_minor = ?4,
             currency = ?5,
             rate_at_operation = ?6,
             rate_at_operation_text = ?7,
             amount_base = ?8,
             amount_base_minor = ?9,
             category = 'Transfer',
             description = ?10
         WHERE id = ?11",
        (
            payload.date.trim(),
            payload.from_wallet_id,
            amount_value,
            amount_minor,
            currency.as_str(),
            rate_value,
            rate_text.as_str(),
            amount_value,
            amount_minor,
            description,
            linked.expense_record_id,
        ),
    )
    .map_err(sqlite_err)?;

    tx.execute(
        "UPDATE records
         SET date = ?1,
             wallet_id = ?2,
             amount_original = ?3,
             amount_original_minor = ?4,
             currency = ?5,
             rate_at_operation = ?6,
             rate_at_operation_text = ?7,
             amount_base = ?8,
             amount_base_minor = ?9,
             category = 'Transfer',
             description = ?10
         WHERE id = ?11",
        (
            payload.date.trim(),
            payload.to_wallet_id,
            amount_value,
            amount_minor,
            currency.as_str(),
            rate_value,
            rate_text.as_str(),
            amount_value,
            amount_minor,
            description,
            linked.income_record_id,
        ),
    )
    .map_err(sqlite_err)?;

    tx.execute(
        "UPDATE records
         SET date = ?1,
             wallet_id = ?2
         WHERE transfer_id IS NULL
           AND description = ?3",
        (
            payload.date.trim(),
            payload.from_wallet_id,
            commission_marker.as_str(),
        ),
    )
    .map_err(sqlite_err)?;

    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    transfer_get_row(db_path, transfer_id)?
        .ok_or_else(|| format!("Transfer not found: {transfer_id}"))
}

pub fn delete_transfer(db_path: &str, transfer_id: i64) -> StorageResult<bool> {
    if transfer_id <= 0 {
        return Err("Transfer id is required".to_owned());
    }
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    let existing = tx
        .query_row(
            "SELECT id FROM transfers WHERE id = ?1",
            [transfer_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .map_err(sqlite_err)?;
    if existing.is_none() {
        return Err(format!("Transfer not found: {transfer_id}"));
    }
    delete_operations_in_tx(&tx, &[], &[], &[transfer_id], 0)?;
    normalize_record_ids_in_tx(&tx)?;

    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(true)
}

pub fn delete_all_operations(db_path: &str) -> StorageResult<OperationDeleteResult> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    let transfer_ids = all_transfer_ids_in_tx(&tx)?;
    let standalone_record_ids = deletable_standalone_record_ids_in_tx(&tx, &transfer_ids)?;
    let debt_linked_record_ids = deletable_debt_linked_record_ids_in_tx(&tx)?;
    let skipped_records = skipped_operation_record_count_in_tx(&tx, &transfer_ids)?;
    let result = delete_operations_in_tx(
        &tx,
        &standalone_record_ids,
        &debt_linked_record_ids,
        &transfer_ids,
        skipped_records,
    )?;
    normalize_record_ids_in_tx(&tx)?;

    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(result)
}

pub fn delete_operations_selection(
    db_path: &str,
    record_ids: &[i64],
    transfer_ids: &[i64],
) -> StorageResult<OperationDeleteResult> {
    if record_ids.is_empty() && transfer_ids.is_empty() {
        return Err("Select at least one operation or transfer".to_owned());
    }
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    let selected_transfer_ids = normalize_positive_ids(transfer_ids, "Transfer")?;
    for transfer_id in &selected_transfer_ids {
        ensure_transfer_exists_in_tx(&tx, *transfer_id)?;
        transfer_linked_record_ids_in_tx(&tx, *transfer_id)?;
    }
    let selected_record_ids =
        validate_selected_operation_record_ids_in_tx(&tx, record_ids, &selected_transfer_ids)?;
    let (standalone_record_ids, debt_linked_record_ids) =
        partition_operation_record_ids_in_tx(&tx, &selected_record_ids)?;
    let result = delete_operations_in_tx(
        &tx,
        &standalone_record_ids,
        &debt_linked_record_ids,
        &selected_transfer_ids,
        0,
    )?;
    normalize_record_ids_in_tx(&tx)?;

    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(result)
}

const OPERATION_TABULAR_HEADERS: [&str; 16] = [
    "date",
    "type",
    "wallet_id",
    "category",
    "amount_original",
    "currency",
    "rate_at_operation",
    "amount_base",
    "description",
    "tags",
    "period",
    "record_id",
    "related_debt_id",
    "transfer_id",
    "from_wallet_id",
    "to_wallet_id",
];
const OPERATION_XLSX_AMOUNT_COLUMNS: [usize; 3] = [4, 6, 7];
const OPERATION_XLSX_INTEGER_COLUMNS: [usize; 6] = [2, 11, 12, 13, 14, 15];
const MAX_OPERATION_CSV_FILE_SIZE: u64 = 10 * 1024 * 1024;
const MAX_OPERATION_CSV_ROWS: usize = 200_000;
const MANDATORY_TABULAR_HEADERS: [&str; 10] = [
    "type",
    "date",
    "wallet_id",
    "category",
    "amount_original",
    "currency",
    "rate_at_operation",
    "amount_base",
    "description",
    "period",
];
const MANDATORY_XLSX_AMOUNT_COLUMNS: [usize; 3] = [4, 6, 7];
const MANDATORY_XLSX_INTEGER_COLUMNS: [usize; 1] = [2];
const MAX_MANDATORY_IMPORT_FILE_SIZE: u64 = 10 * 1024 * 1024;
const MAX_MANDATORY_IMPORT_ROWS: usize = 200_000;

#[derive(Debug, Clone)]
struct ParsedOperationCsvRecord {
    source_record_id: Option<i64>,
    related_debt_id: Option<i64>,
    debt_link_kind: Option<DebtLinkImportKind>,
    record_type: String,
    date: String,
    wallet_id: i64,
    amount_original: f64,
    amount_original_minor: i64,
    currency: String,
    rate_text: String,
    rate: f64,
    amount_base: f64,
    amount_base_minor: i64,
    category: String,
    description: String,
    period: Option<String>,
    tags: Vec<String>,
}

#[derive(Debug, Clone)]
struct ParsedOperationCsvTransfer {
    logical_id: i64,
    from_wallet_id: i64,
    to_wallet_id: i64,
    date: String,
    amount: f64,
    amount_minor: i64,
    currency: String,
    rate_text: String,
    rate: f64,
    description: String,
}

#[derive(Debug, Clone, Default)]
struct OperationCsvPlan {
    rows: Vec<ParsedOperationCsvRow>,
    imported: i64,
    skipped: i64,
    errors: Vec<String>,
    has_blocking_errors: bool,
}

#[derive(Debug, Clone)]
struct ParsedMandatoryTemplate {
    wallet_id: i64,
    amount_original: f64,
    amount_original_minor: i64,
    currency: String,
    rate_text: String,
    rate: f64,
    amount_base: f64,
    amount_base_minor: i64,
    category: String,
    description: String,
    period: String,
    date: String,
}

#[derive(Debug, Clone, Default)]
struct MandatoryImportPlan {
    templates: Vec<ParsedMandatoryTemplate>,
    imported: i64,
    skipped: i64,
    errors: Vec<String>,
    has_blocking_errors: bool,
}

pub fn preview_import_records_csv(
    db_path: &str,
    path: &str,
) -> StorageResult<OperationImportResult> {
    let conn = open_sqlite_connection(db_path)?;
    let plan = parse_operation_csv_import(&conn, path)?;
    Ok(OperationImportResult {
        imported: plan.imported,
        skipped: plan.skipped,
        errors: plan.errors,
        dry_run: true,
        blocking_errors: plan.has_blocking_errors,
    })
}

pub fn preview_import_records_xlsx(
    db_path: &str,
    path: &str,
) -> StorageResult<OperationImportResult> {
    let conn = open_sqlite_connection(db_path)?;
    let plan = parse_operation_xlsx_import(&conn, path)?;
    Ok(OperationImportResult {
        imported: plan.imported,
        skipped: plan.skipped,
        errors: plan.errors,
        dry_run: true,
        blocking_errors: plan.has_blocking_errors,
    })
}

pub fn import_records_csv(db_path: &str, path: &str) -> StorageResult<OperationImportResult> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let plan = parse_operation_csv_import(&conn, path)?;
    import_operation_plan(&mut conn, plan)
}

pub fn import_records_xlsx(db_path: &str, path: &str) -> StorageResult<OperationImportResult> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let plan = parse_operation_xlsx_import(&conn, path)?;
    import_operation_plan(&mut conn, plan)
}

fn import_operation_plan(
    conn: &mut Connection,
    plan: OperationCsvPlan,
) -> StorageResult<OperationImportResult> {
    if plan.imported == 0 {
        if plan.has_blocking_errors {
            let message = plan
                .errors
                .first()
                .cloned()
                .unwrap_or_else(|| "Operations import contains validation errors".to_owned());
            return Err(format!(
                "Operations import contains validation errors: {message}"
            ));
        }
        return Ok(OperationImportResult {
            imported: 0,
            skipped: plan.skipped,
            errors: plan.errors,
            dry_run: false,
            blocking_errors: plan.has_blocking_errors,
        });
    }
    if plan.has_blocking_errors {
        let message = plan
            .errors
            .first()
            .cloned()
            .unwrap_or_else(|| "Operations import contains validation errors".to_owned());
        return Err(format!(
            "Operations import contains validation errors: {message}"
        ));
    }

    let tx = conn.transaction().map_err(sqlite_err)?;
    normalize_tag_colors_in_tx(&tx)?;
    let preserved_tag_colors = tag_color_assignments_in_tx(&tx)?;
    let existing_transfer_ids = all_transfer_ids_in_tx(&tx)?;
    let existing_record_ids = import_replace_record_ids_in_tx(&tx, &existing_transfer_ids)?;
    let skipped_existing = skipped_operation_record_count_in_tx(&tx, &existing_transfer_ids)?;
    delete_operations_in_tx(
        &tx,
        &existing_record_ids,
        &[],
        &existing_transfer_ids,
        skipped_existing,
    )?;

    let mut transfer_id_map: HashMap<i64, i64> = HashMap::new();
    let mut imported_records: Vec<(i64, String)> = Vec::new();
    let mut debt_record_remaps = Vec::new();
    for row in &plan.rows {
        match row {
            ParsedOperationCsvRow::Transfer(transfer) => {
                tx.execute(
                    "INSERT INTO transfers (
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
                    )
                    VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
                    (
                        transfer.from_wallet_id,
                        transfer.to_wallet_id,
                        transfer.date.as_str(),
                        transfer.amount,
                        transfer.amount_minor,
                        transfer.currency.as_str(),
                        transfer.rate,
                        transfer.rate_text.as_str(),
                        transfer.amount,
                        transfer.amount_minor,
                        transfer.description.as_str(),
                    ),
                )
                .map_err(sqlite_err)?;
                let new_transfer_id = tx.last_insert_rowid();
                transfer_id_map.insert(transfer.logical_id, new_transfer_id);
                insert_transfer_record_in_tx(
                    &tx,
                    "expense",
                    &transfer.date,
                    transfer.from_wallet_id,
                    Some(new_transfer_id),
                    transfer.amount,
                    transfer.amount_minor,
                    &transfer.currency,
                    transfer.rate,
                    &transfer.rate_text,
                    "Transfer",
                    &transfer.description,
                )?;
                insert_transfer_record_in_tx(
                    &tx,
                    "income",
                    &transfer.date,
                    transfer.to_wallet_id,
                    Some(new_transfer_id),
                    transfer.amount,
                    transfer.amount_minor,
                    &transfer.currency,
                    transfer.rate,
                    &transfer.rate_text,
                    "Transfer",
                    &transfer.description,
                )?;
            }
            ParsedOperationCsvRow::Record(record) => {
                let record_id = insert_import_record_in_tx(&tx, record, &record.description)?;
                replace_record_tags_in_tx(&tx, record_id, &record.tags, &preserved_tag_colors)?;
                imported_records.push((record_id, record.description.clone()));
                if let Some(debt_id) = record.related_debt_id
                    && let Some(source_record_id) = record.source_record_id
                    && record.debt_link_kind.is_some()
                {
                    debt_record_remaps.push(DebtRecordRemap {
                        old_record_id: Some(source_record_id),
                        new_record_id: record_id,
                        debt_id,
                        kind: record
                            .debt_link_kind
                            .clone()
                            .unwrap_or(DebtLinkImportKind::Opening),
                        principal_paid_minor: record.amount_base_minor,
                        payment_date: record.date.clone(),
                    });
                }
            }
        }
    }

    replace_debt_linked_records_in_tx(&tx, &debt_record_remaps)?;

    if !transfer_id_map.is_empty() {
        let normalized_ids = normalize_transfer_ids_in_tx(&tx)?;
        for mapped_transfer_id in transfer_id_map.values_mut() {
            if let Some(normalized_transfer_id) = normalized_ids.get(mapped_transfer_id) {
                *mapped_transfer_id = *normalized_transfer_id;
            }
        }
        for (record_id, original_description) in &imported_records {
            let description =
                remap_transfer_marker_description(original_description, &transfer_id_map);
            if description != *original_description {
                tx.execute(
                    "UPDATE records SET description = ?1 WHERE id = ?2",
                    (description.as_str(), record_id),
                )
                .map_err(sqlite_err)?;
            }
        }
    }
    normalize_record_ids_in_tx(&tx)?;
    refresh_tag_metrics_in_tx(&tx)?;
    prune_orphan_tags_in_tx(&tx)?;
    normalize_record_ids_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();

    Ok(OperationImportResult {
        imported: plan.imported,
        skipped: plan.skipped,
        errors: plan.errors,
        dry_run: false,
        blocking_errors: plan.has_blocking_errors,
    })
}

pub fn export_records_csv(db_path: &str, path: &str) -> StorageResult<OperationExportResult> {
    let conn = open_sqlite_connection(db_path)?;
    let rows = operation_export_rows(&conn)?;
    let temp_path = export_temp_path(path)?;
    let exported_rows =
        match write_csv_rows(path_text(&temp_path)?, &OPERATION_TABULAR_HEADERS, &rows) {
            Ok(exported_rows) => exported_rows,
            Err(error) => {
                let _ = fs::remove_file(&temp_path);
                return Err(error);
            }
        };
    replace_export_file(&temp_path, Path::new(path))?;
    Ok(OperationExportResult {
        exported_rows,
        path: path.to_owned(),
    })
}

fn operation_export_rows(conn: &Connection) -> StorageResult<Vec<Vec<String>>> {
    let records = record_row_dicts(&conn, &format!("{RECORD_SELECT} ORDER BY id"), &[])?;
    let transfers = transfer_list_rows_from_conn(&conn)?;
    let transfer_map: HashMap<i64, TransferRow> = transfers
        .into_iter()
        .map(|transfer| (transfer.id, transfer))
        .collect();
    let mut exported_transfer_ids = HashSet::new();
    let mut rows = Vec::new();

    for record in records {
        if let Some(transfer_id) = record.transfer_id {
            if exported_transfer_ids.insert(transfer_id)
                && let Some(transfer) = transfer_map.get(&transfer_id)
            {
                rows.push(operation_transfer_csv_row(transfer));
            }
            continue;
        }
        if record.record_type != "income"
            && record.record_type != "expense"
            && record.record_type != "mandatory_expense"
        {
            continue;
        }
        rows.push(operation_record_csv_row(&record));
    }
    Ok(rows)
}

pub fn export_records_xlsx(db_path: &str, path: &str) -> StorageResult<OperationExportResult> {
    let conn = open_sqlite_connection(db_path)?;
    let rows = operation_export_rows(&conn)?;
    let temp_path = export_temp_path(path)?;
    let mut worksheet = StyledWorksheet::new_records_sheet(
        "Data",
        &OPERATION_TABULAR_HEADERS,
        &OPERATION_XLSX_AMOUNT_COLUMNS,
        &OPERATION_XLSX_INTEGER_COLUMNS,
    )
    .map_err(|error| error.to_string())?;
    for row in &rows {
        worksheet
            .append_row(row)
            .map_err(|error| error.to_string())?;
    }
    if let Err(error) = worksheet.save(path_text(&temp_path)?) {
        let _ = fs::remove_file(&temp_path);
        return Err(error.to_string());
    }
    replace_export_file(&temp_path, Path::new(path))?;
    Ok(OperationExportResult {
        exported_rows: i64::try_from(rows.len()).unwrap_or(i64::MAX),
        path: path.to_owned(),
    })
}

pub fn preview_import_mandatory_csv(
    db_path: &str,
    path: &str,
) -> StorageResult<MandatoryImportResult> {
    let conn = open_sqlite_connection(db_path)?;
    let plan = parse_mandatory_csv_import(&conn, path)?;
    Ok(MandatoryImportResult {
        imported: plan.imported,
        skipped: plan.skipped,
        errors: plan.errors,
        dry_run: true,
        blocking_errors: plan.has_blocking_errors,
    })
}

pub fn preview_import_mandatory_xlsx(
    db_path: &str,
    path: &str,
) -> StorageResult<MandatoryImportResult> {
    let conn = open_sqlite_connection(db_path)?;
    let plan = parse_mandatory_xlsx_import(&conn, path)?;
    Ok(MandatoryImportResult {
        imported: plan.imported,
        skipped: plan.skipped,
        errors: plan.errors,
        dry_run: true,
        blocking_errors: plan.has_blocking_errors,
    })
}

pub fn import_mandatory_csv(db_path: &str, path: &str) -> StorageResult<MandatoryImportResult> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let plan = parse_mandatory_csv_import(&conn, path)?;
    import_mandatory_plan(&mut conn, plan)
}

pub fn import_mandatory_xlsx(db_path: &str, path: &str) -> StorageResult<MandatoryImportResult> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let plan = parse_mandatory_xlsx_import(&conn, path)?;
    import_mandatory_plan(&mut conn, plan)
}

pub fn export_mandatory_csv(db_path: &str, path: &str) -> StorageResult<MandatoryExportResult> {
    let conn = open_sqlite_connection(db_path)?;
    let rows = mandatory_export_rows(&conn)?;
    let temp_path = export_temp_path(path)?;
    let exported_rows =
        match write_csv_rows(path_text(&temp_path)?, &MANDATORY_TABULAR_HEADERS, &rows) {
            Ok(exported_rows) => exported_rows,
            Err(error) => {
                let _ = fs::remove_file(&temp_path);
                return Err(error);
            }
        };
    replace_export_file(&temp_path, Path::new(path))?;
    Ok(MandatoryExportResult {
        exported_rows,
        path: path.to_owned(),
    })
}

pub fn export_mandatory_xlsx(db_path: &str, path: &str) -> StorageResult<MandatoryExportResult> {
    let conn = open_sqlite_connection(db_path)?;
    let rows = mandatory_export_rows(&conn)?;
    let temp_path = export_temp_path(path)?;
    let mut worksheet = StyledWorksheet::new_records_sheet(
        "Mandatory",
        &MANDATORY_TABULAR_HEADERS,
        &MANDATORY_XLSX_AMOUNT_COLUMNS,
        &MANDATORY_XLSX_INTEGER_COLUMNS,
    )
    .map_err(|error| error.to_string())?;
    for row in &rows {
        worksheet
            .append_row(row)
            .map_err(|error| error.to_string())?;
    }
    if let Err(error) = worksheet.save(path_text(&temp_path)?) {
        let _ = fs::remove_file(&temp_path);
        return Err(error.to_string());
    }
    replace_export_file(&temp_path, Path::new(path))?;
    Ok(MandatoryExportResult {
        exported_rows: i64::try_from(rows.len()).unwrap_or(i64::MAX),
        path: path.to_owned(),
    })
}

fn import_mandatory_plan(
    conn: &mut Connection,
    plan: MandatoryImportPlan,
) -> StorageResult<MandatoryImportResult> {
    if plan.has_blocking_errors {
        let message = plan
            .errors
            .first()
            .cloned()
            .unwrap_or_else(|| "Mandatory import contains validation errors".to_owned());
        return Err(format!(
            "Mandatory import contains validation errors: {message}"
        ));
    }
    if plan.templates.is_empty() {
        return Err("Mandatory import contains no templates".to_owned());
    }

    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute("DELETE FROM mandatory_expenses", [])
        .map_err(sqlite_err)?;
    reset_sqlite_sequence_to_max_id_in_tx(&tx, "mandatory_expenses")?;
    for template in &plan.templates {
        insert_import_mandatory_template_in_tx(&tx, template)?;
    }
    normalize_mandatory_template_ids_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();

    Ok(MandatoryImportResult {
        imported: plan.imported,
        skipped: plan.skipped,
        errors: plan.errors,
        dry_run: false,
        blocking_errors: false,
    })
}

fn mandatory_export_rows(conn: &Connection) -> StorageResult<Vec<Vec<String>>> {
    let mut stmt = conn
        .prepare(
            "SELECT
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
                period,
                COALESCE(date, '')
             FROM mandatory_expenses
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(MandatoryExpenseRow {
                id: 0,
                wallet_id: row.get(0)?,
                amount_original: money_value_from_sql_row(row, 1, 2)?,
                currency: row.get(3)?,
                rate_at_operation: rate_value_from_sql_row(row, 4, 5)?,
                amount_base: money_value_from_sql_row(row, 6, 7)?,
                category: row.get(8)?,
                description: row.get(9)?,
                period: row.get(10)?,
                date: row.get::<_, Option<String>>(11)?.unwrap_or_default(),
                auto_pay: false,
            })
        })
        .map_err(sqlite_err)?
        .collect::<Result<Vec<_>, _>>()
        .map_err(sqlite_err)?;
    Ok(rows
        .into_iter()
        .map(|row| {
            vec![
                "mandatory_expense".to_owned(),
                row.date,
                row.wallet_id.to_string(),
                row.category,
                format_money_export(row.amount_original),
                row.currency,
                format_rate_export(row.rate_at_operation),
                format_money_export(row.amount_base),
                row.description,
                row.period,
            ]
        })
        .collect())
}

fn export_temp_path(path: &str) -> StorageResult<PathBuf> {
    let target = Path::new(path);
    let parent = target.parent().unwrap_or_else(|| Path::new("."));
    let file_name = target
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| "Export path must include a file name".to_owned())?;
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_nanos();
    Ok(parent.join(format!(".{file_name}.{unique}.tmp")))
}

fn path_text(path: &Path) -> StorageResult<&str> {
    path.to_str()
        .ok_or_else(|| "Export path must be valid UTF-8".to_owned())
}

#[cfg(not(windows))]
fn replace_export_file(temp_path: &Path, target_path: &Path) -> StorageResult<()> {
    fs::rename(temp_path, target_path).map_err(|error| error.to_string())
}

#[cfg(windows)]
fn replace_export_file(temp_path: &Path, target_path: &Path) -> StorageResult<()> {
    use std::os::windows::ffi::OsStrExt;

    let temp_wide = temp_path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let target_wide = target_path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let result = unsafe {
        MoveFileExW(
            temp_wide.as_ptr(),
            target_wide.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if result == 0 {
        let error = std::io::Error::last_os_error().to_string();
        let _ = fs::remove_file(temp_path);
        return Err(error);
    }
    Ok(())
}

fn parse_operation_csv_import(conn: &Connection, path: &str) -> StorageResult<OperationCsvPlan> {
    let rows = read_csv_rows(
        path,
        MAX_OPERATION_CSV_FILE_SIZE,
        MAX_OPERATION_CSV_ROWS,
        "CSV import",
    )?;
    parse_operation_tabular_import(conn, rows)
}

fn parse_operation_xlsx_import(conn: &Connection, path: &str) -> StorageResult<OperationCsvPlan> {
    let metadata = fs::metadata(path).map_err(|error| error.to_string())?;
    if metadata.len() > MAX_OPERATION_CSV_FILE_SIZE {
        return Err(format!(
            "XLSX import file is too large: {} bytes",
            metadata.len()
        ));
    }
    let mut workbook = open_workbook_auto(path).map_err(|error| error.to_string())?;
    let Some(sheet_name) = workbook.sheet_names().first().cloned() else {
        return Ok(OperationCsvPlan::default());
    };
    let range = workbook
        .worksheet_range(&sheet_name)
        .map_err(|error| error.to_string())?;
    let mut rows_iter = range.rows();
    let Some(header_row) = rows_iter.next() else {
        return Ok(OperationCsvPlan::default());
    };
    let headers = header_row
        .iter()
        .map(xlsx_cell_to_string)
        .map(|value| normalize_tabular_key(&value))
        .collect::<Vec<_>>();
    let mut rows = Vec::new();
    for (index, row) in rows_iter.enumerate() {
        if index >= MAX_OPERATION_CSV_ROWS {
            return Err(format!(
                "XLSX import exceeded row limit ({MAX_OPERATION_CSV_ROWS})"
            ));
        }
        rows.push((index + 2, xlsx_row_values(&headers, row)));
    }
    parse_operation_tabular_import(conn, rows)
}

fn parse_mandatory_csv_import(conn: &Connection, path: &str) -> StorageResult<MandatoryImportPlan> {
    let rows = read_csv_rows(
        path,
        MAX_MANDATORY_IMPORT_FILE_SIZE,
        MAX_MANDATORY_IMPORT_ROWS,
        "Mandatory CSV import",
    )?;
    parse_mandatory_tabular_import(conn, rows)
}

fn parse_mandatory_xlsx_import(
    conn: &Connection,
    path: &str,
) -> StorageResult<MandatoryImportPlan> {
    let metadata = fs::metadata(path).map_err(|error| error.to_string())?;
    if metadata.len() > MAX_MANDATORY_IMPORT_FILE_SIZE {
        return Err(format!(
            "Mandatory XLSX import file is too large: {} bytes",
            metadata.len()
        ));
    }
    let mut workbook = open_workbook_auto(path).map_err(|error| error.to_string())?;
    let Some(sheet_name) = workbook.sheet_names().first().cloned() else {
        return Ok(empty_mandatory_import_plan());
    };
    let range = workbook
        .worksheet_range(&sheet_name)
        .map_err(|error| error.to_string())?;
    let mut rows_iter = range.rows();
    let Some(header_row) = rows_iter.next() else {
        return Ok(empty_mandatory_import_plan());
    };
    let headers = header_row
        .iter()
        .map(xlsx_cell_to_string)
        .map(|value| normalize_tabular_key(&value))
        .collect::<Vec<_>>();
    let mut rows = Vec::new();
    for (index, row) in rows_iter.enumerate() {
        if index >= MAX_MANDATORY_IMPORT_ROWS {
            return Err(format!(
                "Mandatory XLSX import exceeded row limit ({MAX_MANDATORY_IMPORT_ROWS})"
            ));
        }
        rows.push((index + 2, xlsx_row_values(&headers, row)));
    }
    parse_mandatory_tabular_import(conn, rows)
}

fn parse_mandatory_tabular_import(
    conn: &Connection,
    rows: Vec<(usize, HashMap<String, String>)>,
) -> StorageResult<MandatoryImportPlan> {
    let base_currency = base_currency_code_in_conn(conn)?;
    let wallet_ids = active_wallet_ids_in_conn(conn)?;
    let mut plan = MandatoryImportPlan::default();
    for (row_number, values) in rows {
        let row_label = format!("row {row_number}");
        if values.values().all(|value| value.trim().is_empty()) {
            continue;
        }
        match parse_mandatory_template_row(&values, &row_label, &base_currency, &wallet_ids) {
            Ok(template) => {
                plan.templates.push(template);
                plan.imported += 1;
            }
            Err(error) => {
                plan.skipped += 1;
                plan.errors.push(error);
                plan.has_blocking_errors = true;
            }
        }
    }
    if plan.imported == 0 && plan.skipped == 0 {
        plan = empty_mandatory_import_plan();
    }
    Ok(plan)
}

fn empty_mandatory_import_plan() -> MandatoryImportPlan {
    let mut plan = MandatoryImportPlan::default();
    plan.has_blocking_errors = true;
    plan.errors
        .push("Mandatory import contains no templates".to_owned());
    plan
}

fn parse_mandatory_template_row(
    values: &HashMap<String, String>,
    row_label: &str,
    base_currency: &str,
    wallet_ids: &HashSet<i64>,
) -> StorageResult<ParsedMandatoryTemplate> {
    let row_type = required_csv_value(values, "type", row_label)?
        .trim()
        .to_lowercase();
    if row_type != "mandatory_expense" {
        return Err(format!("{row_label}: unsupported type '{row_type}'"));
    }
    let date = csv_value(values, "date").trim().to_owned();
    if !date.is_empty() {
        validate_ymd_syntax(&date)?;
    }
    let wallet_id = parse_required_positive_i64(values, "wallet_id", row_label)?;
    if !wallet_ids.contains(&wallet_id) {
        return Err(format!("{row_label}: wallet not found ({wallet_id})"));
    }
    let category = required_csv_value(values, "category", row_label)?;
    let description = csv_value(values, "description");
    let period = csv_value(values, "period").trim().to_lowercase();
    validate_mandatory_period(&period)?;
    let currency = required_csv_value(values, "currency", row_label)?.to_uppercase();
    validate_currency_code(&currency)?;
    validate_mandatory_base_currency_only(&currency, base_currency)?;
    let (_amount_original_text, amount_original, amount_original_minor) =
        parse_abs_positive_money(values, "amount_original", row_label)?;
    let (_amount_base_text, amount_base, amount_base_minor) =
        parse_abs_positive_money(values, "amount_base", row_label)?;
    let (rate_text, rate) = parse_positive_rate(values, "rate_at_operation", row_label)?;
    Ok(ParsedMandatoryTemplate {
        wallet_id,
        amount_original,
        amount_original_minor,
        currency,
        rate_text,
        rate,
        amount_base,
        amount_base_minor,
        description: normalize_mandatory_description(&description, &category),
        category,
        period,
        date,
    })
}

fn parse_operation_tabular_import(
    conn: &Connection,
    rows: Vec<(usize, HashMap<String, String>)>,
) -> StorageResult<OperationCsvPlan> {
    let base_currency = base_currency_code_in_conn(conn)?;
    let wallet_ids = active_wallet_ids_in_conn(conn)?;
    let debt_ids = debt_ids_in_conn(conn)?;
    let mut plan = OperationCsvPlan::default();
    let mut logical_transfer_ids = HashSet::new();
    let mut debt_source_record_ids = HashSet::new();
    let mut next_implicit_transfer_id = -1_i64;
    for (row_number, values) in rows {
        let row_label = format!("row {row_number}");
        if values.values().all(|value| value.trim().is_empty()) {
            continue;
        }
        let debt_linked_row = !csv_value(&values, "related_debt_id").trim().is_empty();
        let row = parse_operation_csv_row(
            conn,
            &values,
            &row_label,
            &base_currency,
            &wallet_ids,
            &debt_ids,
            &mut logical_transfer_ids,
            &mut next_implicit_transfer_id,
        );
        match row {
            Ok(row) => {
                if let ParsedOperationCsvRow::Record(record) = &row
                    && record.related_debt_id.is_some()
                    && let Some(source_record_id) = record.source_record_id
                    && !debt_source_record_ids.insert(source_record_id)
                {
                    plan.skipped += 1;
                    plan.errors.push(format!(
                        "{row_label}: duplicate debt-linked record_id {source_record_id}"
                    ));
                    plan.has_blocking_errors = true;
                    continue;
                }
                plan.rows.push(row);
                plan.imported += 1;
            }
            Err(error) => {
                if debt_linked_row {
                    plan.has_blocking_errors = true;
                }
                plan.skipped += 1;
                plan.errors.push(error);
            }
        }
    }
    Ok(plan)
}

#[derive(Debug, Clone)]
enum ParsedOperationCsvRow {
    Record(ParsedOperationCsvRecord),
    Transfer(ParsedOperationCsvTransfer),
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DebtLinkImportKind {
    Opening,
    RemapPayment {
        payment_id: i64,
        previous_record_id: Option<i64>,
    },
    RecreateDeletedPayment {
        operation_type: String,
    },
}

struct DebtRecordRemap {
    old_record_id: Option<i64>,
    new_record_id: i64,
    debt_id: i64,
    kind: DebtLinkImportKind,
    principal_paid_minor: i64,
    payment_date: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct DebtPaymentImportMatch {
    payment_id: i64,
    previous_record_id: Option<i64>,
}

fn parse_operation_csv_row(
    conn: &Connection,
    values: &HashMap<String, String>,
    row_label: &str,
    base_currency: &str,
    wallet_ids: &HashSet<i64>,
    debt_ids: &HashSet<i64>,
    logical_transfer_ids: &mut HashSet<i64>,
    next_implicit_transfer_id: &mut i64,
) -> StorageResult<ParsedOperationCsvRow> {
    let row_type = csv_value(values, "type").trim().to_lowercase();
    if row_type == "transfer" {
        return parse_operation_csv_transfer(
            values,
            row_label,
            base_currency,
            wallet_ids,
            next_implicit_transfer_id,
        )
        .and_then(|transfer| {
            if !logical_transfer_ids.insert(transfer.logical_id) {
                return Err(format!(
                    "{row_label}: duplicate transfer_id {}",
                    transfer.logical_id
                ));
            }
            Ok(ParsedOperationCsvRow::Transfer(transfer))
        });
    }
    if row_type != "income" && row_type != "expense" && row_type != "mandatory_expense" {
        return Err(format!("{row_label}: unsupported type '{row_type}'"));
    }
    let transfer_id = csv_value(values, "transfer_id");
    if !transfer_id.trim().is_empty() {
        return Err(format!(
            "{row_label}: transfer-linked child rows are not supported; use aggregate transfer rows"
        ));
    }
    let period_value = csv_value(values, "period").trim().to_lowercase();
    let period = if row_type == "mandatory_expense" {
        if period_value.is_empty() {
            return Err(format!("{row_label}: mandatory_expense requires period"));
        }
        validate_mandatory_period(&period_value)
            .map_err(|error| format!("{row_label}: {error}"))?;
        Some(period_value)
    } else if !period_value.is_empty() {
        return Err(format!(
            "{row_label}: period is only supported for mandatory_expense rows"
        ));
    } else {
        None
    };
    if row_type == "mandatory_expense"
        && (!csv_value(values, "from_wallet_id").trim().is_empty()
            || !csv_value(values, "to_wallet_id").trim().is_empty())
    {
        return Err(format!(
            "{row_label}: mandatory_expense rows cannot include transfer wallet fields"
        ));
    }
    let source_record_id = parse_optional_positive_i64(values, "record_id", row_label)?;
    let related_debt_id = parse_optional_positive_i64(values, "related_debt_id", row_label)?;
    if row_type == "mandatory_expense" && related_debt_id.is_some() {
        return Err(format!(
            "{row_label}: mandatory_expense rows cannot be debt-linked"
        ));
    }
    if let Some(debt_id) = related_debt_id
        && !debt_ids.contains(&debt_id)
    {
        return Err(format!("{row_label}: debt not found ({debt_id})"));
    }
    if related_debt_id.is_some() && source_record_id.is_none() {
        return Err(format!(
            "{row_label}: debt-linked rows require record_id for payment remap"
        ));
    }
    let date = required_csv_value(values, "date", row_label)?;
    validate_ymd_date(&date)?;
    let wallet_id = parse_required_positive_i64(values, "wallet_id", row_label)?;
    if !wallet_ids.contains(&wallet_id) {
        return Err(format!("{row_label}: wallet not found ({wallet_id})"));
    }
    let category = required_csv_value(values, "category", row_label)?;
    let description = csv_value(values, "description");
    if let Some(marker_transfer_id) = transfer_marker_id(&description) {
        return Err(format!(
            "{row_label}: transfer commission marker [transfer:{marker_transfer_id}] requires an aggregate transfer row"
        ));
    }
    let currency = required_csv_value(values, "currency", row_label)?.to_uppercase();
    validate_currency_code(&currency)?;
    validate_base_currency_only(&currency, base_currency)?;
    let (_amount_original_text, amount_original, amount_original_minor) =
        parse_positive_money(values, "amount_original", row_label)?;
    let (_amount_base_text, amount_base, amount_base_minor) =
        parse_positive_money(values, "amount_base", row_label)?;
    let (rate_text, rate) = parse_positive_rate(values, "rate_at_operation", row_label)?;
    let debt_link_kind = match (related_debt_id, source_record_id) {
        (Some(debt_id), Some(record_id)) => Some(validate_debt_linked_import_source_in_conn(
            conn,
            row_label,
            record_id,
            debt_id,
            &row_type,
            &date,
            amount_base_minor,
        )?),
        _ => None,
    };
    Ok(ParsedOperationCsvRow::Record(ParsedOperationCsvRecord {
        source_record_id,
        related_debt_id,
        debt_link_kind,
        record_type: row_type,
        date,
        wallet_id,
        amount_original,
        amount_original_minor,
        currency,
        rate_text,
        rate,
        amount_base,
        amount_base_minor,
        category,
        description,
        period,
        tags: parse_csv_tags(&csv_value(values, "tags")),
    }))
}

fn validate_debt_linked_import_source_in_conn(
    conn: &Connection,
    row_label: &str,
    source_record_id: i64,
    debt_id: i64,
    imported_record_type: &str,
    imported_date: &str,
    imported_amount_base_minor: i64,
) -> StorageResult<DebtLinkImportKind> {
    let debt = conn
        .query_row(
            "SELECT kind, total_amount_minor, remaining_amount_minor, created_at
             FROM debts
             WHERE id = ?1",
            [debt_id],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                ))
            },
        )
        .optional()
        .map_err(sqlite_err)?
        .ok_or_else(|| format!("{row_label}: debt not found ({debt_id})"))?;
    let old_record = conn
        .query_row(
            "SELECT type, transfer_id, related_debt_id
             FROM records
             WHERE id = ?1",
            [source_record_id],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, Option<i64>>(1)?,
                    row.get::<_, Option<i64>>(2)?,
                ))
            },
        )
        .optional()
        .map_err(sqlite_err)?;
    let (kind, total_amount_minor, remaining_amount_minor, created_at) = debt;
    let expected_opening_type = debt_opening_record_type(&kind)?;
    let expected_payment_type = debt_payment_record_type_for_kind(&kind)?;
    let expected_payment_operation = debt_payment_operation_type_for_kind(&kind)?;
    let Some((source_record_type, transfer_id, related_debt_id)) = old_record else {
        let payments = debt_payment_rows_for_source_record(conn, debt_id, source_record_id)?;
        return match payments.as_slice() {
            [(payment_id, operation_type, principal_paid_minor, is_write_off, payment_date)] => {
                if *is_write_off != 0 {
                    return Err(format!(
                        "{row_label}: write-off payments cannot be imported as debt-linked operation rows"
                    ));
                }
                if imported_record_type
                    != debt_payment_record_type(operation_type).unwrap_or(expected_payment_type)
                    || imported_date != payment_date
                    || imported_amount_base_minor != *principal_paid_minor
                {
                    return Err(format!(
                        "{row_label}: debt-linked payment record does not match payment history for debt {debt_id}"
                    ));
                }
                Ok(DebtLinkImportKind::RemapPayment {
                    payment_id: *payment_id,
                    previous_record_id: Some(source_record_id),
                })
            }
            [] if imported_record_type == expected_opening_type
                && imported_date == created_at
                && imported_amount_base_minor == total_amount_minor =>
            {
                Ok(DebtLinkImportKind::Opening)
            }
            [] if imported_record_type == expected_payment_type => {
                if let Some(payment) = matching_debt_payment_for_import(
                    conn,
                    debt_id,
                    expected_payment_operation,
                    imported_date,
                    imported_amount_base_minor,
                    row_label,
                )? {
                    return validate_semantic_debt_payment_match(
                        conn,
                        row_label,
                        debt_id,
                        source_record_id,
                        payment,
                    );
                }
                if imported_amount_base_minor > remaining_amount_minor {
                    return Err(format!(
                        "{row_label}: debt-linked payment exceeds remaining amount for debt {debt_id}"
                    ));
                }
                Ok(DebtLinkImportKind::RecreateDeletedPayment {
                    operation_type: expected_payment_operation.to_owned(),
                })
            }
            [] => Err(format!(
                "{row_label}: debt-linked source record not found ({source_record_id})"
            )),
            _ => Err(format!(
                "{row_label}: debt-linked source record {source_record_id} has multiple matching debt payments"
            )),
        };
    };
    if transfer_id.is_some()
        || related_debt_id != Some(debt_id)
        || (source_record_type != "income" && source_record_type != "expense")
    {
        return Err(format!(
            "{row_label}: debt-linked source record {source_record_id} does not belong to debt {debt_id}"
        ));
    }

    let payments = debt_payment_rows_for_source_record(conn, debt_id, source_record_id)?;
    match payments.as_slice() {
        [] => {
            if imported_record_type == expected_opening_type
                && imported_date == created_at
                && imported_amount_base_minor == total_amount_minor
            {
                return Ok(DebtLinkImportKind::Opening);
            }
            if imported_record_type == expected_payment_type {
                if let Some(payment) = matching_debt_payment_for_import(
                    conn,
                    debt_id,
                    expected_payment_operation,
                    imported_date,
                    imported_amount_base_minor,
                    row_label,
                )? {
                    return validate_semantic_debt_payment_match(
                        conn,
                        row_label,
                        debt_id,
                        source_record_id,
                        payment,
                    );
                }
                return Err(format!(
                    "{row_label}: debt-linked source record {source_record_id} is not linked to payment history for debt {debt_id}"
                ));
            }
            Err(format!(
                "{row_label}: debt-linked opening record does not match debt {debt_id}"
            ))
        }
        [(payment_id, operation_type, principal_paid_minor, is_write_off, payment_date)] => {
            if *is_write_off != 0 {
                return Err(format!(
                    "{row_label}: write-off payments cannot be imported as debt-linked operation rows"
                ));
            }
            let expected_type =
                debt_payment_record_type(operation_type).unwrap_or(source_record_type.as_str());
            if imported_record_type != expected_type
                || imported_date != payment_date
                || imported_amount_base_minor != *principal_paid_minor
            {
                return Err(format!(
                    "{row_label}: debt-linked payment record does not match payment history for debt {debt_id}"
                ));
            }
            Ok(DebtLinkImportKind::RemapPayment {
                payment_id: *payment_id,
                previous_record_id: Some(source_record_id),
            })
        }
        _ => Err(format!(
            "{row_label}: debt-linked source record {source_record_id} has multiple matching debt payments"
        )),
    }
}

fn debt_opening_record_type(kind: &str) -> StorageResult<&'static str> {
    match kind {
        "debt" => Ok("income"),
        "loan" => Ok("expense"),
        _ => Err(format!("Unsupported debt kind: {kind}")),
    }
}

fn debt_payment_record_type(operation_type: &str) -> Option<&'static str> {
    match operation_type {
        "debt_repay" => Some("expense"),
        "loan_collect" => Some("income"),
        _ => None,
    }
}

fn debt_payment_record_type_for_kind(kind: &str) -> StorageResult<&'static str> {
    match kind {
        "debt" => Ok("expense"),
        "loan" => Ok("income"),
        _ => Err(format!("Unsupported debt kind: {kind}")),
    }
}

fn debt_payment_operation_type_for_kind(kind: &str) -> StorageResult<&'static str> {
    match kind {
        "debt" => Ok("debt_repay"),
        "loan" => Ok("loan_collect"),
        _ => Err(format!("Unsupported debt kind: {kind}")),
    }
}

fn debt_payment_rows_for_source_record(
    conn: &Connection,
    debt_id: i64,
    source_record_id: i64,
) -> StorageResult<Vec<(i64, String, i64, i64, String)>> {
    let mut stmt = conn
        .prepare(
            "SELECT id, operation_type, principal_paid_minor, is_write_off, payment_date
             FROM debt_payments
             WHERE debt_id = ?1 AND record_id = ?2
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    stmt.query_map((debt_id, source_record_id), |row| {
        Ok((
            row.get::<_, i64>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, i64>(2)?,
            row.get::<_, i64>(3)?,
            row.get::<_, String>(4)?,
        ))
    })
    .map_err(sqlite_err)?
    .collect::<Result<Vec<_>, _>>()
    .map_err(sqlite_err)
}

fn matching_debt_payment_for_import(
    conn: &Connection,
    debt_id: i64,
    expected_operation_type: &str,
    imported_date: &str,
    imported_amount_base_minor: i64,
    row_label: &str,
) -> StorageResult<Option<DebtPaymentImportMatch>> {
    let mut stmt = conn
        .prepare(
            "SELECT id, record_id
             FROM debt_payments
             WHERE debt_id = ?1
               AND operation_type = ?2
               AND principal_paid_minor = ?3
               AND is_write_off = 0
               AND payment_date = ?4
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let matches = stmt
        .query_map(
            (
                debt_id,
                expected_operation_type,
                imported_amount_base_minor,
                imported_date,
            ),
            |row| {
                Ok(DebtPaymentImportMatch {
                    payment_id: row.get(0)?,
                    previous_record_id: row.get(1)?,
                })
            },
        )
        .map_err(sqlite_err)?
        .collect::<Result<Vec<_>, _>>()
        .map_err(sqlite_err)?;
    match matches.as_slice() {
        [] => Ok(None),
        [payment] => Ok(Some(*payment)),
        _ => Err(format!(
            "{row_label}: debt-linked payment row matches multiple debt history entries for debt {debt_id}"
        )),
    }
}

fn record_exists_for_import(conn: &Connection, record_id: i64) -> StorageResult<bool> {
    conn.query_row("SELECT 1 FROM records WHERE id = ?1", [record_id], |_row| {
        Ok(())
    })
    .optional()
    .map(|value| value.is_some())
    .map_err(sqlite_err)
}

fn validate_semantic_debt_payment_match(
    conn: &Connection,
    row_label: &str,
    debt_id: i64,
    source_record_id: i64,
    payment: DebtPaymentImportMatch,
) -> StorageResult<DebtLinkImportKind> {
    if let Some(previous_record_id) = payment.previous_record_id
        && previous_record_id != source_record_id
        && record_exists_for_import(conn, previous_record_id)?
    {
        return Err(format!(
            "{row_label}: debt payment {} is already linked to existing record {} for debt {}",
            payment.payment_id, previous_record_id, debt_id
        ));
    }
    Ok(DebtLinkImportKind::RemapPayment {
        payment_id: payment.payment_id,
        previous_record_id: payment.previous_record_id,
    })
}

fn parse_operation_csv_transfer(
    values: &HashMap<String, String>,
    row_label: &str,
    base_currency: &str,
    wallet_ids: &HashSet<i64>,
    next_implicit_transfer_id: &mut i64,
) -> StorageResult<ParsedOperationCsvTransfer> {
    if !csv_value(values, "record_id").trim().is_empty()
        || !csv_value(values, "related_debt_id").trim().is_empty()
    {
        return Err(format!(
            "{row_label}: transfer aggregate rows cannot include record_id or related_debt_id"
        ));
    }
    let date = required_csv_value(values, "date", row_label)?;
    validate_ymd_date(&date)?;
    let from_wallet_id = parse_required_positive_i64(values, "from_wallet_id", row_label)?;
    let to_wallet_id = parse_required_positive_i64(values, "to_wallet_id", row_label)?;
    if from_wallet_id == to_wallet_id {
        return Err(format!("{row_label}: transfer wallets must be different"));
    }
    if !wallet_ids.contains(&from_wallet_id) {
        return Err(format!("{row_label}: wallet not found ({from_wallet_id})"));
    }
    if !wallet_ids.contains(&to_wallet_id) {
        return Err(format!("{row_label}: wallet not found ({to_wallet_id})"));
    }
    let logical_id = match parse_optional_positive_i64(values, "transfer_id", row_label)? {
        Some(value) => value,
        None => {
            let value = *next_implicit_transfer_id;
            *next_implicit_transfer_id -= 1;
            value
        }
    };
    let currency = required_csv_value(values, "currency", row_label)?.to_uppercase();
    validate_currency_code(&currency)?;
    validate_transfer_base_currency_only(&currency, base_currency)?;
    let (_amount_text, amount, amount_minor) =
        parse_positive_money(values, "amount_original", row_label)?;
    let (_amount_base_text, _amount_base, amount_base_minor) =
        parse_positive_money(values, "amount_base", row_label)?;
    if amount_minor != amount_base_minor {
        return Err(format!(
            "{row_label}: base-currency transfer amount_base must equal amount_original"
        ));
    }
    let (rate_text, rate) = parse_positive_rate(values, "rate_at_operation", row_label)?;
    if rate_text != "1.000000" && (rate - 1.0).abs() > f64::EPSILON {
        return Err(format!(
            "{row_label}: base-currency transfer rate must be 1"
        ));
    }
    Ok(ParsedOperationCsvTransfer {
        logical_id,
        from_wallet_id,
        to_wallet_id,
        date,
        amount,
        amount_minor,
        currency,
        rate_text,
        rate,
        description: csv_value(values, "description"),
    })
}

fn xlsx_row_values(headers: &[String], row: &[Data]) -> HashMap<String, String> {
    let mut values = HashMap::new();
    for (index, header) in headers.iter().enumerate() {
        let value = row.get(index).map(xlsx_cell_to_string).unwrap_or_default();
        values.insert(header.clone(), value.trim().to_owned());
    }
    values
}

fn xlsx_cell_to_string(cell: &Data) -> String {
    match cell {
        Data::Empty => String::new(),
        Data::String(value) => value.trim().to_owned(),
        Data::Float(value) => decimal_text(*value),
        Data::Int(value) => value.to_string(),
        Data::Bool(value) => value.to_string(),
        Data::DateTime(value) => excel_serial_to_date_text(value.as_f64()),
        Data::DateTimeIso(value) => value
            .split(['T', ' '])
            .next()
            .unwrap_or(value)
            .trim()
            .to_owned(),
        Data::DurationIso(value) => value.trim().to_owned(),
        Data::Error(error) => format!("ERROR:{error:?}"),
    }
}

fn decimal_text(value: f64) -> String {
    if value.fract().abs() < f64::EPSILON {
        return format!("{value:.0}");
    }
    let text = format!("{value:.15}");
    text.trim_end_matches('0').trim_end_matches('.').to_owned()
}

fn format_money_export(value: f64) -> String {
    format!("{value:.2}")
}

fn format_rate_export(value: f64) -> String {
    let text = format!("{value:.6}");
    text.trim_end_matches('0').trim_end_matches('.').to_owned()
}

fn excel_serial_to_date_text(serial: f64) -> String {
    let days = serial.floor() as i64;
    let (year, month, day) = civil_from_days(days - 25_569);
    format!("{year:04}-{month:02}-{day:02}")
}

fn csv_value(values: &HashMap<String, String>, key: &str) -> String {
    values.get(key).cloned().unwrap_or_default()
}

fn required_csv_value(
    values: &HashMap<String, String>,
    key: &str,
    row_label: &str,
) -> StorageResult<String> {
    let value = csv_value(values, key);
    if value.trim().is_empty() {
        Err(format!("{row_label}: missing required field '{key}'"))
    } else {
        Ok(value.trim().to_owned())
    }
}

fn parse_required_positive_i64(
    values: &HashMap<String, String>,
    key: &str,
    row_label: &str,
) -> StorageResult<i64> {
    parse_optional_positive_i64(values, key, row_label)?
        .ok_or_else(|| format!("{row_label}: missing required field '{key}'"))
}

fn parse_optional_positive_i64(
    values: &HashMap<String, String>,
    key: &str,
    row_label: &str,
) -> StorageResult<Option<i64>> {
    let value = csv_value(values, key);
    if value.trim().is_empty() {
        return Ok(None);
    }
    let parsed = value
        .trim()
        .parse::<i64>()
        .map_err(|_| format!("{row_label}: invalid {key} '{value}'"))?;
    if parsed <= 0 {
        return Err(format!("{row_label}: invalid {key} '{value}'"));
    }
    Ok(Some(parsed))
}

fn parse_positive_money(
    values: &HashMap<String, String>,
    key: &str,
    row_label: &str,
) -> StorageResult<(String, f64, i64)> {
    let raw = required_csv_value(values, key, row_label)?;
    let text = quantize_money_text(&raw).map_err(|error| format!("{row_label}: {key}: {error}"))?;
    let minor = to_minor_units(&text).map_err(|error| format!("{row_label}: {key}: {error}"))?;
    if minor <= 0 {
        return Err(format!("{row_label}: {key} must be positive"));
    }
    let value = text
        .parse::<f64>()
        .map_err(|_| format!("{row_label}: invalid {key}"))?;
    Ok((text, value, minor))
}

fn parse_abs_positive_money(
    values: &HashMap<String, String>,
    key: &str,
    row_label: &str,
) -> StorageResult<(String, f64, i64)> {
    let raw = required_csv_value(values, key, row_label)?;
    let text = quantize_money_text(&raw).map_err(|error| format!("{row_label}: {key}: {error}"))?;
    let minor = to_minor_units(&text).map_err(|error| format!("{row_label}: {key}: {error}"))?;
    let abs_minor = minor.abs();
    if abs_minor <= 0 {
        return Err(format!("{row_label}: {key} must be positive"));
    }
    let value = minor_to_money_value(abs_minor);
    Ok((format_money_export(value), value, abs_minor))
}

fn parse_positive_rate(
    values: &HashMap<String, String>,
    key: &str,
    row_label: &str,
) -> StorageResult<(String, f64)> {
    let raw = required_csv_value(values, key, row_label)?;
    let text = quantize_rate_text(&raw).map_err(|error| format!("{row_label}: {key}: {error}"))?;
    let value = text
        .parse::<f64>()
        .map_err(|_| format!("{row_label}: invalid {key}"))?;
    if value <= 0.0 {
        return Err(format!("{row_label}: {key} must be positive"));
    }
    Ok((text, value))
}

fn parse_csv_tags(value: &str) -> Vec<String> {
    value
        .split([',', ';'])
        .map(str::trim)
        .filter(|tag| !tag.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn active_wallet_ids_in_conn(conn: &Connection) -> StorageResult<HashSet<i64>> {
    let mut stmt = conn
        .prepare("SELECT id FROM wallets WHERE is_active = 1 ORDER BY id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    rows.collect::<Result<HashSet<_>, _>>().map_err(sqlite_err)
}

fn debt_ids_in_conn(conn: &Connection) -> StorageResult<HashSet<i64>> {
    let has_debts = conn
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'debts'",
            [],
            |_| Ok(()),
        )
        .optional()
        .map_err(sqlite_err)?
        .is_some();
    if !has_debts {
        return Ok(HashSet::new());
    }
    let mut stmt = conn
        .prepare("SELECT id FROM debts ORDER BY id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    rows.collect::<Result<HashSet<_>, _>>().map_err(sqlite_err)
}

fn remap_transfer_marker_description(
    description: &str,
    transfer_id_map: &HashMap<i64, i64>,
) -> String {
    let Some(old_transfer_id) = transfer_marker_id(description) else {
        return description.to_owned();
    };
    match transfer_id_map.get(&old_transfer_id) {
        Some(new_transfer_id) => format!("[transfer:{new_transfer_id}]"),
        None => description.to_owned(),
    }
}

fn replace_debt_linked_records_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_id_map: &[DebtRecordRemap],
) -> StorageResult<()> {
    for remap in record_id_map {
        if remap.old_record_id == Some(remap.new_record_id)
            && matches!(remap.kind, DebtLinkImportKind::Opening)
        {
            continue;
        }
        if remap.old_record_id != Some(remap.new_record_id)
            && let Some(old_record_id) = remap.old_record_id
        {
            let old_record = tx
                .query_row(
                    "SELECT type, transfer_id, related_debt_id
                     FROM records
                     WHERE id = ?1",
                    [old_record_id],
                    |row| {
                        Ok((
                            row.get::<_, String>(0)?,
                            row.get::<_, Option<i64>>(1)?,
                            row.get::<_, Option<i64>>(2)?,
                        ))
                    },
                )
                .optional()
                .map_err(sqlite_err)?;
            if let Some((record_type, transfer_id, related_debt_id)) = old_record {
                if transfer_id.is_some()
                    || related_debt_id != Some(remap.debt_id)
                    || (record_type != "income" && record_type != "expense")
                {
                    return Err(format!(
                        "Debt-linked source record {old_record_id} does not belong to debt {}",
                        remap.debt_id
                    ));
                }
                tx.execute(
                    "DELETE FROM record_tags WHERE record_id = ?1",
                    [old_record_id],
                )
                .map_err(sqlite_err)?;
                let deleted = tx
                    .execute(
                        "DELETE FROM records
                         WHERE id = ?1
                           AND transfer_id IS NULL
                           AND related_debt_id = ?2
                           AND type IN ('income', 'expense')",
                        (old_record_id, remap.debt_id),
                    )
                    .map_err(sqlite_err)?;
                if deleted != 1 {
                    return Err(format!(
                        "Debt-linked source record delete failed: {old_record_id}"
                    ));
                }
            }
        }
        match &remap.kind {
            DebtLinkImportKind::Opening => {}
            DebtLinkImportKind::RemapPayment { payment_id, .. } => {
                let updated = tx
                    .execute(
                        "UPDATE debt_payments
                         SET record_id = ?1
                         WHERE id = ?2 AND debt_id = ?3",
                        (remap.new_record_id, payment_id, remap.debt_id),
                    )
                    .map_err(sqlite_err)?;
                if updated != 1 {
                    return Err(format!(
                        "Debt payment remap failed for payment {payment_id}"
                    ));
                }
            }
            DebtLinkImportKind::RecreateDeletedPayment { operation_type } => {
                recreate_debt_payment_for_import_in_tx(tx, remap, operation_type)?;
            }
        }
    }
    Ok(())
}

fn recreate_debt_payment_for_import_in_tx(
    tx: &rusqlite::Transaction<'_>,
    remap: &DebtRecordRemap,
    operation_type: &str,
) -> StorageResult<()> {
    let (total_amount_minor, remaining_amount_minor) = tx
        .query_row(
            "SELECT total_amount_minor, remaining_amount_minor
             FROM debts
             WHERE id = ?1",
            [remap.debt_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?)),
        )
        .optional()
        .map_err(sqlite_err)?
        .ok_or_else(|| format!("Debt not found: {}", remap.debt_id))?;
    if remap.principal_paid_minor <= 0 || remap.principal_paid_minor > remaining_amount_minor {
        return Err(format!(
            "Debt-linked payment exceeds remaining amount for debt {}",
            remap.debt_id
        ));
    }
    tx.execute(
        "INSERT INTO debt_payments (
            debt_id, record_id, operation_type,
            principal_paid_minor, is_write_off, payment_date
         )
         VALUES (?1, ?2, ?3, ?4, 0, ?5)",
        (
            remap.debt_id,
            remap.new_record_id,
            operation_type,
            remap.principal_paid_minor,
            remap.payment_date.as_str(),
        ),
    )
    .map_err(sqlite_err)?;
    let restored_remaining = remaining_amount_minor - remap.principal_paid_minor;
    let closed_at = if restored_remaining == 0 {
        Some(remap.payment_date.as_str())
    } else {
        None
    };
    tx.execute(
        "UPDATE debts
         SET remaining_amount_minor = ?1,
             status = ?2,
             closed_at = ?3
         WHERE id = ?4",
        (
            restored_remaining.max(0).min(total_amount_minor),
            if restored_remaining == 0 {
                "closed"
            } else {
                "open"
            },
            closed_at,
            remap.debt_id,
        ),
    )
    .map_err(sqlite_err)?;
    Ok(())
}

fn insert_import_record_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record: &ParsedOperationCsvRecord,
    description: &str,
) -> StorageResult<i64> {
    tx.execute(
        "INSERT INTO records (
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
        )
        VALUES (?1, ?2, ?3, NULL, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
        (
            record.record_type.as_str(),
            record.date.as_str(),
            record.wallet_id,
            record.related_debt_id,
            record.amount_original,
            record.amount_original_minor,
            record.currency.as_str(),
            record.rate,
            record.rate_text.as_str(),
            record.amount_base,
            record.amount_base_minor,
            record.category.as_str(),
            description,
            record.period.as_deref(),
        ),
    )
    .map_err(sqlite_err)?;
    Ok(tx.last_insert_rowid())
}

fn transfer_list_rows_from_conn(conn: &Connection) -> StorageResult<Vec<TransferRow>> {
    let mut stmt = conn
        .prepare(
            "SELECT id, from_wallet_id, to_wallet_id, date,
                    amount_original, amount_original_minor, currency,
                    rate_at_operation, rate_at_operation_text,
                    amount_base, amount_base_minor, description
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
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn operation_record_csv_row(record: &RecordRow) -> Vec<String> {
    vec![
        record.date.clone(),
        record.record_type.clone(),
        record.wallet_id.to_string(),
        record.category.clone(),
        money_csv_text(record.amount_original),
        record.currency.clone(),
        rate_csv_text(record.rate_at_operation),
        money_csv_text(record.amount_base),
        record.description.clone(),
        record.tags.join(", "),
        if record.record_type == "mandatory_expense" {
            record
                .period
                .clone()
                .filter(|period| !period.trim().is_empty())
                .unwrap_or_else(|| "monthly".to_owned())
        } else {
            String::new()
        },
        record.id.to_string(),
        record
            .related_debt_id
            .map(|value| value.to_string())
            .unwrap_or_default(),
        String::new(),
        String::new(),
        String::new(),
    ]
}

fn operation_transfer_csv_row(transfer: &TransferRow) -> Vec<String> {
    vec![
        transfer.date.clone(),
        "transfer".to_owned(),
        String::new(),
        "Transfer".to_owned(),
        money_csv_text(transfer.amount_original),
        transfer.currency.clone(),
        rate_csv_text(transfer.rate_at_operation),
        money_csv_text(transfer.amount_base),
        transfer.description.clone(),
        String::new(),
        String::new(),
        String::new(),
        String::new(),
        transfer.id.to_string(),
        transfer.from_wallet_id.to_string(),
        transfer.to_wallet_id.to_string(),
    ]
}

fn money_csv_text(value: f64) -> String {
    quantize_money_text(&value.to_string()).unwrap_or_else(|_| format!("{value:.2}"))
}

fn rate_csv_text(value: f64) -> String {
    quantize_rate_text(&value.to_string()).unwrap_or_else(|_| value.to_string())
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

pub fn mandatory_template_create(
    db_path: &str,
    payload: &MandatoryTemplateCreatePayload,
) -> StorageResult<MandatoryExpenseRow> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    validate_mandatory_template_create_payload_in_tx(&tx, payload)?;
    let currency = payload.currency.trim().to_uppercase();
    let amount_original_minor = to_minor_units(&payload.amount_original)?;
    let amount_base_minor = to_minor_units(&payload.amount_base)?;
    let amount_original = quantize_money_text(&payload.amount_original)?
        .parse::<f64>()
        .map_err(|_| "invalid mandatory amount_original".to_owned())?;
    let amount_base = quantize_money_text(&payload.amount_base)?
        .parse::<f64>()
        .map_err(|_| "invalid mandatory amount_base".to_owned())?;
    let rate_text = quantize_rate_text(&payload.rate_at_operation)?;
    let rate_value = rate_text
        .parse::<f64>()
        .map_err(|_| "invalid mandatory rate_at_operation".to_owned())?;
    let normalized_date = payload.date.trim();
    let auto_pay = !normalized_date.is_empty();
    let category = payload.category.trim();
    let description = payload.description.trim();
    let period = payload.period.trim().to_lowercase();

    tx.execute(
        "INSERT INTO mandatory_expenses (
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
            period,
            date,
            auto_pay
        )
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
        (
            payload.wallet_id,
            amount_original,
            amount_original_minor,
            currency.as_str(),
            rate_value,
            rate_text.as_str(),
            amount_base,
            amount_base_minor,
            category,
            description,
            period.as_str(),
            normalized_date,
            i64::from(auto_pay),
        ),
    )
    .map_err(sqlite_err)?;
    let template_id = tx.last_insert_rowid();
    reset_sqlite_sequence_to_max_id_in_tx(&tx, "mandatory_expenses")?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    mandatory_expense_row(db_path, template_id)?
        .ok_or_else(|| format!("Mandatory template not found: {template_id}"))
}

pub fn mandatory_template_update(
    db_path: &str,
    template_id: i64,
    payload: &MandatoryTemplateUpdatePayload,
) -> StorageResult<MandatoryExpenseRow> {
    if template_id <= 0 {
        return Err("Mandatory template id is required".to_owned());
    }
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    ensure_mandatory_template_exists_in_tx(&tx, template_id)?;
    validate_mandatory_template_update_payload_in_tx(&tx, payload)?;
    let amount_base_minor = to_minor_units(&payload.amount_base)?;
    let amount_base = quantize_money_text(&payload.amount_base)?
        .parse::<f64>()
        .map_err(|_| "invalid mandatory amount_base".to_owned())?;
    let normalized_date = payload.date.trim();
    let auto_pay = !normalized_date.is_empty();
    let period = payload.period.trim().to_lowercase();

    tx.execute(
        "UPDATE mandatory_expenses
         SET wallet_id = ?1,
             amount_base = ?2,
             amount_base_minor = ?3,
             period = ?4,
             date = ?5,
             auto_pay = ?6
         WHERE id = ?7",
        (
            payload.wallet_id,
            amount_base,
            amount_base_minor,
            period.as_str(),
            normalized_date,
            i64::from(auto_pay),
            template_id,
        ),
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    mandatory_expense_row(db_path, template_id)?
        .ok_or_else(|| format!("Mandatory template not found: {template_id}"))
}

pub fn mandatory_template_delete(db_path: &str, template_id: i64) -> StorageResult<bool> {
    if template_id <= 0 {
        return Err("Mandatory template id is required".to_owned());
    }
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    ensure_mandatory_template_exists_in_tx(&tx, template_id)?;
    let deleted = tx
        .execute(
            "DELETE FROM mandatory_expenses WHERE id = ?1",
            [template_id],
        )
        .map_err(sqlite_err)?;
    if deleted != 1 {
        return Err(format!(
            "Failed to delete mandatory template: {template_id}"
        ));
    }
    normalize_mandatory_template_ids_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(true)
}

pub fn mandatory_template_delete_all(db_path: &str) -> StorageResult<i64> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let deleted = tx
        .execute("DELETE FROM mandatory_expenses", [])
        .map_err(sqlite_err)?;
    reset_sqlite_sequence_to_max_id_in_tx(&tx, "mandatory_expenses")?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(i64::try_from(deleted).unwrap_or(i64::MAX))
}

pub fn mandatory_add_to_records(
    db_path: &str,
    payload: &MandatoryAddToRecordsPayload,
) -> StorageResult<RecordRow> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;

    if payload.template_id <= 0 {
        return Err("Mandatory template id is required".to_owned());
    }
    let template = mandatory_template_in_tx(&tx, payload.template_id)?;
    insert_mandatory_record_from_template_in_tx(
        &tx,
        &template,
        payload.date.trim(),
        payload.wallet_id,
        true,
    )?;
    let record_id = tx.last_insert_rowid();
    let record_id_map = normalize_record_ids_in_tx(&tx)?;
    let normalized_record_id = record_id_map.get(&record_id).copied().unwrap_or(record_id);
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    record_get_row(db_path, normalized_record_id)?
        .ok_or_else(|| format!("Record not found: {normalized_record_id}"))
}

pub fn mandatory_apply_auto_payments(
    db_path: &str,
    today: &str,
) -> StorageResult<MandatoryAutoPayResult> {
    validate_ymd_syntax(today)
        .map_err(|error| format!("auto-pay service date is invalid ({today}): {error}"))?;
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let today_parts = parse_ymd_parts(today)?;
    let templates = mandatory_templates_in_tx(&tx)?;
    let mut inserted_record_ids = Vec::new();

    for template in templates {
        if !template.auto_pay {
            continue;
        }
        let anchor_raw = template.date.trim();
        if anchor_raw.is_empty() {
            continue;
        }
        let anchor = parse_ymd_parts(anchor_raw).map_err(|error| {
            format!(
                "auto-pay template {} has invalid anchor date ({}): {}",
                template.id, anchor_raw, error
            )
        })?;
        if today_parts < anchor {
            continue;
        }
        let Some(target_date) =
            mandatory_auto_pay_target_date(&template.period, anchor, today_parts)
        else {
            continue;
        };
        if target_date < anchor {
            continue;
        }
        if target_date > today_parts {
            continue;
        }
        let target_date_text = ymd_text(target_date);
        if mandatory_generated_record_exists_in_tx(&tx, &template, &target_date_text)? {
            continue;
        }
        insert_mandatory_record_from_template_in_tx(
            &tx,
            &template,
            &target_date_text,
            template.wallet_id,
            false,
        )
        .map_err(|error| {
            format!(
                "auto-pay failed for template {} anchor={} target={} today={}: {}",
                template.id, anchor_raw, target_date_text, today, error
            )
        })?;
        inserted_record_ids.push(tx.last_insert_rowid());
    }

    let record_id_map = normalize_record_ids_in_tx(&tx)?;
    let normalized_ids: Vec<i64> = inserted_record_ids
        .into_iter()
        .map(|id| record_id_map.get(&id).copied().unwrap_or(id))
        .collect();
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();

    let mut created_records = Vec::new();
    for record_id in normalized_ids {
        if let Some(row) = record_get_row(db_path, record_id)? {
            created_records.push(row);
        }
    }
    Ok(MandatoryAutoPayResult { created_records })
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

pub fn filtered_record_list_rows(
    db_path: &str,
    filter: &RecordFilterPayload,
) -> StorageResult<Vec<RecordRow>> {
    let conn = open_sqlite_connection(db_path)?;
    let mut sql = String::from(RECORD_SELECT);
    let mut clauses: Vec<String> = Vec::new();
    let mut params: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();

    if let Some(start_date) = filter
        .start_date
        .as_deref()
        .filter(|value| !value.is_empty())
    {
        clauses.push("date >= ?".to_owned());
        params.push(Box::new(start_date.to_owned()));
    }
    if let Some(end_date) = filter.end_date.as_deref().filter(|value| !value.is_empty()) {
        clauses.push("date <= ?".to_owned());
        params.push(Box::new(end_date.to_owned()));
    }
    if let Some(wallet_id) = filter.wallet_id {
        clauses.push("wallet_id = ?".to_owned());
        params.push(Box::new(wallet_id));
    }
    if let Some(record_type) = filter
        .record_type
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        clauses.push("type = ?".to_owned());
        params.push(Box::new(record_type.to_owned()));
    }

    if !clauses.is_empty() {
        sql.push_str(" WHERE ");
        sql.push_str(&clauses.join(" AND "));
    }
    sql.push_str(" ORDER BY date DESC, id DESC");

    let param_refs: Vec<&dyn rusqlite::ToSql> = params
        .iter()
        .map(|param| param.as_ref() as &dyn rusqlite::ToSql)
        .collect();
    record_row_dicts(&conn, &sql, &param_refs)
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

pub fn standalone_record_get_row(
    db_path: &str,
    record_id: i64,
) -> StorageResult<Option<RecordRow>> {
    let row = record_get_row(db_path, record_id)?;
    match row {
        Some(record) if record.transfer_id.is_none() && record.related_debt_id.is_none() => {
            Ok(Some(record))
        }
        Some(_) => Err("Only standalone records can be edited from Kotlin Operations".to_owned()),
        None => Ok(None),
    }
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

pub fn create_standalone_record(
    db_path: &str,
    payload: &StandaloneRecordCreatePayload,
) -> StorageResult<RecordRow> {
    create_standalone_record_with_tag_colors(db_path, payload, &[])
}

pub fn create_standalone_record_with_tag_colors(
    db_path: &str,
    payload: &StandaloneRecordCreatePayload,
    tag_colors: &[TagColorAssignment],
) -> StorageResult<RecordRow> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    normalize_tag_colors_in_tx(&tx)?;

    let record_type = payload.record_type.trim().to_lowercase();
    if record_type != "income" && record_type != "expense" {
        return Err("Unsupported record type for Kotlin Operations MVP".to_owned());
    }
    if payload.date.trim().is_empty() {
        return Err("Record date is required".to_owned());
    }
    validate_ymd_date(payload.date.trim())?;
    if payload.wallet_id <= 0 {
        return Err("wallet_id must be positive".to_owned());
    }
    let category = payload.category.trim();
    if category.is_empty() {
        return Err("Category is required".to_owned());
    }
    let currency = payload.currency.trim().to_uppercase();
    validate_currency_code(&currency)?;
    let base_currency = base_currency_code_in_tx(&tx)?;
    validate_base_currency_only(&currency, &base_currency)?;

    let wallet_exists = tx
        .query_row(
            "SELECT 1 FROM wallets WHERE id = ?1",
            [payload.wallet_id],
            |_row| Ok(()),
        )
        .optional()
        .map_err(sqlite_err)?
        .is_some();
    if !wallet_exists {
        return Err(format!("Wallet not found: {}", payload.wallet_id));
    }

    let amount_original_minor = to_minor_units(&payload.amount_original)?;
    let amount_base_minor = to_minor_units(&payload.amount_base)?;
    if amount_original_minor <= 0 || amount_base_minor <= 0 {
        return Err("Record amount must be positive".to_owned());
    }
    let amount_original = quantize_money_text(&payload.amount_original)?
        .parse::<f64>()
        .map_err(|_| "invalid amount_original".to_owned())?;
    let amount_base = quantize_money_text(&payload.amount_base)?
        .parse::<f64>()
        .map_err(|_| "invalid amount_base".to_owned())?;
    let rate_at_operation_text = quantize_rate_text(&payload.rate_at_operation)?;
    let rate_at_operation = rate_at_operation_text
        .parse::<f64>()
        .map_err(|_| "invalid rate_at_operation".to_owned())?;
    if rate_at_operation <= 0.0 {
        return Err("rate_at_operation must be positive".to_owned());
    }

    let cursor = tx
        .execute(
            "INSERT INTO records (
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
            )
            VALUES (?1, ?2, ?3, NULL, NULL, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, NULL)",
            (
                record_type.as_str(),
                payload.date.trim(),
                payload.wallet_id,
                amount_original,
                amount_original_minor,
                currency.as_str(),
                rate_at_operation,
                rate_at_operation_text.as_str(),
                amount_base,
                amount_base_minor,
                category,
                payload.description.as_str(),
            ),
        )
        .map_err(sqlite_err)?;
    if cursor != 1 {
        return Err("Failed to insert record".to_owned());
    }
    let record_id = tx.last_insert_rowid();
    replace_record_tags_in_tx(&tx, record_id, &payload.tags, tag_colors)?;
    let record_id_map = normalize_record_ids_in_tx(&tx)?;
    let normalized_record_id = record_id_map.get(&record_id).copied().unwrap_or(record_id);
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    record_get_row(db_path, normalized_record_id)?
        .ok_or_else(|| format!("Record not found: {normalized_record_id}"))
}

pub fn update_standalone_record(
    db_path: &str,
    record_id: i64,
    payload: &StandaloneRecordUpdatePayload,
) -> StorageResult<RecordRow> {
    update_standalone_record_with_tag_colors(db_path, record_id, payload, &[])
}

pub fn update_standalone_record_with_tag_colors(
    db_path: &str,
    record_id: i64,
    payload: &StandaloneRecordUpdatePayload,
    tag_colors: &[TagColorAssignment],
) -> StorageResult<RecordRow> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    normalize_tag_colors_in_tx(&tx)?;
    ensure_standalone_record_exists_in_tx(&tx, record_id)?;
    if let Some(marker) = transfer_commission_marker_in_tx(&tx, record_id)? {
        validate_transfer_commission_update(&marker, payload)?;
    }

    let record_type = payload.record_type.trim().to_lowercase();
    if record_type != "income" && record_type != "expense" {
        return Err("Unsupported record type for Kotlin Operations".to_owned());
    }
    if payload.date.trim().is_empty() {
        return Err("Record date is required".to_owned());
    }
    validate_ymd_date(payload.date.trim())?;
    if payload.wallet_id <= 0 {
        return Err("wallet_id must be positive".to_owned());
    }
    let category = payload.category.trim();
    if category.is_empty() {
        return Err("Category is required".to_owned());
    }
    let currency = payload.currency.trim().to_uppercase();
    validate_currency_code(&currency)?;
    let base_currency = base_currency_code_in_tx(&tx)?;
    validate_base_currency_only(&currency, &base_currency)?;
    let wallet_exists = tx
        .query_row(
            "SELECT 1 FROM wallets WHERE id = ?1",
            [payload.wallet_id],
            |_row| Ok(()),
        )
        .optional()
        .map_err(sqlite_err)?
        .is_some();
    if !wallet_exists {
        return Err(format!("Wallet not found: {}", payload.wallet_id));
    }

    let amount_original_minor = to_minor_units(&payload.amount_original)?;
    let amount_base_minor = to_minor_units(&payload.amount_base)?;
    if amount_original_minor <= 0 || amount_base_minor <= 0 {
        return Err("Record amount must be positive".to_owned());
    }
    let amount_original = quantize_money_text(&payload.amount_original)?
        .parse::<f64>()
        .map_err(|_| "invalid amount_original".to_owned())?;
    let amount_base = quantize_money_text(&payload.amount_base)?
        .parse::<f64>()
        .map_err(|_| "invalid amount_base".to_owned())?;
    let rate_at_operation_text = quantize_rate_text(&payload.rate_at_operation)?;
    let rate_at_operation = rate_at_operation_text
        .parse::<f64>()
        .map_err(|_| "invalid rate_at_operation".to_owned())?;
    if rate_at_operation <= 0.0 {
        return Err("rate_at_operation must be positive".to_owned());
    }

    let updated = tx
        .execute(
            "UPDATE records
             SET type = ?1,
                 date = ?2,
                 wallet_id = ?3,
                 amount_original = ?4,
                 amount_original_minor = ?5,
                 currency = ?6,
                 rate_at_operation = ?7,
                 rate_at_operation_text = ?8,
                 amount_base = ?9,
                 amount_base_minor = ?10,
                 category = ?11,
                 description = ?12
             WHERE id = ?13
               AND transfer_id IS NULL
               AND related_debt_id IS NULL",
            (
                record_type.as_str(),
                payload.date.trim(),
                payload.wallet_id,
                amount_original,
                amount_original_minor,
                currency.as_str(),
                rate_at_operation,
                rate_at_operation_text.as_str(),
                amount_base,
                amount_base_minor,
                category,
                payload.description.as_str(),
                record_id,
            ),
        )
        .map_err(sqlite_err)?;
    if updated != 1 {
        return Err(format!("Record not found: {record_id}"));
    }
    replace_record_tags_in_tx(&tx, record_id, &payload.tags, tag_colors)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    record_get_row(db_path, record_id)?.ok_or_else(|| format!("Record not found: {record_id}"))
}

pub fn delete_standalone_record(db_path: &str, record_id: i64) -> StorageResult<bool> {
    let mut conn = open_sqlite_connection(db_path)?;
    conn.pragma_update(None, "foreign_keys", "ON")
        .map_err(sqlite_err)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let deleted = delete_operation_record_in_tx(&tx, record_id)?;
    refresh_tag_metrics_in_tx(&tx)?;
    prune_orphan_tags_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    if deleted > 0 {
        storage_clear_read_connection_cache();
    }
    Ok(deleted > 0)
}

pub fn base_currency_code(db_path: &str) -> StorageResult<String> {
    let conn = open_sqlite_connection(db_path)?;
    base_currency_code_in_conn(&conn)
}

pub fn tag_names(db_path: &str) -> StorageResult<Vec<String>> {
    let conn = open_sqlite_connection(db_path)?;
    let mut stmt = conn
        .prepare("SELECT name FROM tags ORDER BY usage_count DESC, name COLLATE NOCASE, name")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

pub fn tag_color_rows(db_path: &str) -> StorageResult<Vec<TagColorRow>> {
    let conn = open_sqlite_connection(db_path)?;
    let mut stmt = conn
        .prepare(
            "SELECT name, COALESCE(color, '')
             FROM tags
             ORDER BY usage_count DESC, name COLLATE NOCASE, name",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(TagColorRow {
                name: row.get(0)?,
                color: row.get(1)?,
            })
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn tag_color_assignments_in_tx(
    tx: &rusqlite::Transaction<'_>,
) -> StorageResult<Vec<TagColorAssignment>> {
    let mut stmt = tx
        .prepare("SELECT name, COALESCE(color, '') FROM tags ORDER BY id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok(TagColorAssignment {
                name: row.get(0)?,
                color: row.get(1)?,
            })
        })
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

pub fn tag_color_palette() -> Vec<String> {
    TAG_PALETTE
        .iter()
        .map(|color| (*color).to_owned())
        .collect()
}

pub fn normalize_tag_colors(db_path: &str) -> StorageResult<()> {
    let mut conn = open_sqlite_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    normalize_tag_colors_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn distinct_record_categories(db_path: &str, record_type: &str) -> StorageResult<Vec<String>> {
    let conn = open_sqlite_connection(db_path)?;
    let normalized_type = record_type.trim().to_lowercase();
    if normalized_type != "income"
        && normalized_type != "expense"
        && normalized_type != "mandatory_expense"
    {
        return Err("record_type must be income, expense, or mandatory_expense".to_owned());
    }
    let mut stmt = conn
        .prepare(
            "SELECT DISTINCT TRIM(category) AS category
             FROM records
             WHERE type = ?1
               AND TRIM(category) <> ''
               AND transfer_id IS NULL
               AND related_debt_id IS NULL
             ORDER BY category COLLATE NOCASE, category",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([normalized_type.as_str()], |row| row.get::<_, String>(0))
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OperationSuggestions {
    pub tags: Vec<String>,
    pub income_categories: Vec<String>,
    pub expense_categories: Vec<String>,
    pub descriptions: Vec<String>,
    pub income_descriptions: Vec<String>,
    pub expense_descriptions: Vec<String>,
}

pub fn operation_suggestions(db_path: &str) -> StorageResult<OperationSuggestions> {
    Ok(OperationSuggestions {
        tags: tag_names(db_path)?,
        income_categories: distinct_record_categories(db_path, "income")?,
        expense_categories: distinct_record_categories(db_path, "expense")?,
        descriptions: distinct_record_descriptions(db_path, None)?,
        income_descriptions: distinct_record_descriptions(db_path, Some("income"))?,
        expense_descriptions: distinct_record_descriptions(db_path, Some("expense"))?,
    })
}

pub fn distinct_record_descriptions(
    db_path: &str,
    record_type: Option<&str>,
) -> StorageResult<Vec<String>> {
    let conn = open_sqlite_connection(db_path)?;
    let normalized_type = record_type
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_lowercase);
    if let Some(record_type) = normalized_type.as_deref() {
        if record_type != "income" && record_type != "expense" {
            return Err("record_type must be income or expense".to_owned());
        }
    }

    let sql = if normalized_type.is_some() {
        "SELECT DISTINCT TRIM(description) AS description
         FROM records
         WHERE type = ?1
           AND transfer_id IS NULL
           AND related_debt_id IS NULL
           AND TRIM(description) <> ''
           AND TRIM(description) NOT GLOB '[[]transfer:[0-9]*]'
         ORDER BY description COLLATE NOCASE, description
         LIMIT 200"
    } else {
        "SELECT DISTINCT TRIM(description) AS description
         FROM records
         WHERE type IN ('income', 'expense')
           AND transfer_id IS NULL
           AND related_debt_id IS NULL
           AND TRIM(description) <> ''
           AND TRIM(description) NOT GLOB '[[]transfer:[0-9]*]'
         ORDER BY description COLLATE NOCASE, description
         LIMIT 200"
    };

    let mut stmt = conn.prepare(sql).map_err(sqlite_err)?;
    let rows = if let Some(record_type) = normalized_type.as_deref() {
        stmt.query_map([record_type], |row| row.get::<_, String>(0))
            .map_err(sqlite_err)?
            .collect::<Result<Vec<_>, _>>()
    } else {
        stmt.query_map([], |row| row.get::<_, String>(0))
            .map_err(sqlite_err)?
            .collect::<Result<Vec<_>, _>>()
    };
    rows.map_err(sqlite_err)
}

fn ensure_standalone_record_exists_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_id: i64,
) -> StorageResult<()> {
    let row = tx
        .query_row(
            "SELECT transfer_id, related_debt_id FROM records WHERE id = ?1",
            [record_id],
            |row| Ok((row.get::<_, Option<i64>>(0)?, row.get::<_, Option<i64>>(1)?)),
        )
        .optional()
        .map_err(sqlite_err)?;
    match row {
        Some((None, None)) => Ok(()),
        Some(_) => Err("Only standalone records can be edited from Kotlin Operations".to_owned()),
        None => Err(format!("Record not found: {record_id}")),
    }
}

#[derive(Debug, Clone, PartialEq)]
struct TransferWallet {
    id: i64,
    allow_negative: bool,
}

#[derive(Debug, Clone, PartialEq)]
struct TransferLinkedRecordIds {
    expense_record_id: i64,
    income_record_id: i64,
}

fn transfer_linked_record_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
    transfer_id: i64,
) -> StorageResult<TransferLinkedRecordIds> {
    let mut stmt = tx
        .prepare("SELECT id, type FROM records WHERE transfer_id = ?1 ORDER BY id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([transfer_id], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(sqlite_err)?;
    let mut linked = Vec::new();
    for row in rows {
        linked.push(row.map_err(sqlite_err)?);
    }
    if linked.len() != 2 {
        return Err(format!(
            "Transfer integrity violated for #{transfer_id}: expected 2 linked records, got {}",
            linked.len()
        ));
    }
    let expense_record_id = linked
        .iter()
        .find_map(|(id, record_type)| (record_type == "expense").then_some(*id))
        .ok_or_else(|| {
            format!("Transfer integrity violated for #{transfer_id}: requires one expense and one income")
        })?;
    let income_record_id = linked
        .iter()
        .find_map(|(id, record_type)| (record_type == "income").then_some(*id))
        .ok_or_else(|| {
            format!("Transfer integrity violated for #{transfer_id}: requires one expense and one income")
        })?;
    Ok(TransferLinkedRecordIds {
        expense_record_id,
        income_record_id,
    })
}

fn ensure_transfer_exists_in_tx(
    tx: &rusqlite::Transaction<'_>,
    transfer_id: i64,
) -> StorageResult<()> {
    let exists = tx
        .query_row(
            "SELECT 1 FROM transfers WHERE id = ?1",
            [transfer_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()
        .map_err(sqlite_err)?;
    if exists.is_some() {
        Ok(())
    } else {
        Err(format!("Transfer not found: {transfer_id}"))
    }
}

fn normalize_positive_ids(ids: &[i64], label: &str) -> StorageResult<Vec<i64>> {
    let mut unique = HashSet::new();
    let mut normalized = Vec::new();
    for id in ids {
        if *id <= 0 {
            return Err(format!("{label} id is required"));
        }
        if unique.insert(*id) {
            normalized.push(*id);
        }
    }
    normalized.sort_unstable();
    Ok(normalized)
}

fn all_transfer_ids_in_tx(tx: &rusqlite::Transaction<'_>) -> StorageResult<Vec<i64>> {
    let mut stmt = tx
        .prepare("SELECT id FROM transfers ORDER BY id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn normalize_transfer_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
) -> StorageResult<HashMap<i64, i64>> {
    let mut stmt = tx
        .prepare("SELECT id FROM transfers ORDER BY date, id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    let ordered_ids = rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)?;
    let transfer_id_map: HashMap<i64, i64> = ordered_ids
        .iter()
        .enumerate()
        .map(|(index, old_id)| (*old_id, i64::try_from(index + 1).unwrap_or(i64::MAX)))
        .collect();
    if transfer_id_map
        .iter()
        .all(|(old_id, new_id)| old_id == new_id)
    {
        return Ok(transfer_id_map);
    }

    for (old_id, new_id) in &transfer_id_map {
        let temp_id = -*new_id;
        tx.execute(
            "UPDATE transfers SET id = ?1 WHERE id = ?2",
            (temp_id, old_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE records SET transfer_id = ?1 WHERE transfer_id = ?2",
            (temp_id, old_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE records
             SET description = ?1
             WHERE transfer_id IS NULL
               AND related_debt_id IS NULL
               AND description = ?2",
            (
                format!("[transfer:{temp_id}]"),
                format!("[transfer:{old_id}]"),
            ),
        )
        .map_err(sqlite_err)?;
    }

    for new_id in transfer_id_map.values() {
        let temp_id = -*new_id;
        tx.execute(
            "UPDATE transfers SET id = ?1 WHERE id = ?2",
            (new_id, temp_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE records SET transfer_id = ?1 WHERE transfer_id = ?2",
            (new_id, temp_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE records
             SET description = ?1
             WHERE transfer_id IS NULL
               AND related_debt_id IS NULL
               AND description = ?2",
            (
                format!("[transfer:{new_id}]"),
                format!("[transfer:{temp_id}]"),
            ),
        )
        .map_err(sqlite_err)?;
    }

    let max_id = i64::try_from(ordered_ids.len()).unwrap_or(0);
    let has_sequence = tx
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'",
            [],
            |_row| Ok(()),
        )
        .optional()
        .map_err(sqlite_err)?
        .is_some();
    if has_sequence {
        tx.execute(
            "UPDATE sqlite_sequence SET seq = ?1 WHERE name = 'transfers'",
            [max_id],
        )
        .map_err(sqlite_err)?;
    }
    Ok(transfer_id_map)
}

pub(crate) fn normalize_record_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
) -> StorageResult<HashMap<i64, i64>> {
    let mut stmt = tx
        .prepare("SELECT id FROM records ORDER BY date, id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    let ordered_ids = rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)?;
    let record_id_map: HashMap<i64, i64> = ordered_ids
        .iter()
        .enumerate()
        .map(|(index, old_id)| (*old_id, i64::try_from(index + 1).unwrap_or(i64::MAX)))
        .collect();
    if record_id_map
        .iter()
        .all(|(old_id, new_id)| old_id == new_id)
    {
        return Ok(record_id_map);
    }

    for (old_id, new_id) in &record_id_map {
        let temp_id = -*new_id;
        tx.execute(
            "UPDATE records SET id = ?1 WHERE id = ?2",
            (temp_id, old_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE record_tags SET record_id = ?1 WHERE record_id = ?2",
            (temp_id, old_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE debt_payments SET record_id = ?1 WHERE record_id = ?2",
            (temp_id, old_id),
        )
        .map_err(sqlite_err)?;
    }

    for new_id in record_id_map.values() {
        let temp_id = -*new_id;
        tx.execute(
            "UPDATE records SET id = ?1 WHERE id = ?2",
            (new_id, temp_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE record_tags SET record_id = ?1 WHERE record_id = ?2",
            (new_id, temp_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE debt_payments SET record_id = ?1 WHERE record_id = ?2",
            (new_id, temp_id),
        )
        .map_err(sqlite_err)?;
    }

    reset_sqlite_sequence_to_max_id_in_tx(tx, "records")?;
    Ok(record_id_map)
}

fn deletable_standalone_record_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
    transfer_ids: &[i64],
) -> StorageResult<Vec<i64>> {
    let selected_transfers: HashSet<i64> = transfer_ids.iter().copied().collect();
    let mut stmt = tx
        .prepare(
            "SELECT id, description
             FROM records
             WHERE transfer_id IS NULL
               AND related_debt_id IS NULL
               AND type IN ('income', 'expense', 'mandatory_expense')
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(sqlite_err)?;
    let mut ids = Vec::new();
    for row in rows {
        let (record_id, description) = row.map_err(sqlite_err)?;
        if transfer_marker_id(&description)
            .is_some_and(|transfer_id| selected_transfers.contains(&transfer_id))
        {
            continue;
        }
        if transfer_marker_id(&description).is_some() {
            continue;
        }
        ids.push(record_id);
    }
    Ok(ids)
}

fn import_replace_record_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
    transfer_ids: &[i64],
) -> StorageResult<Vec<i64>> {
    let selected_transfers: HashSet<i64> = transfer_ids.iter().copied().collect();
    let mut stmt = tx
        .prepare(
            "SELECT id, description
             FROM records
             WHERE transfer_id IS NULL
               AND related_debt_id IS NULL
               AND type IN ('income', 'expense', 'mandatory_expense')
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(sqlite_err)?;
    let mut ids = Vec::new();
    for row in rows {
        let (record_id, description) = row.map_err(sqlite_err)?;
        if transfer_marker_id(&description)
            .is_some_and(|transfer_id| selected_transfers.contains(&transfer_id))
        {
            continue;
        }
        if transfer_marker_id(&description).is_some() {
            continue;
        }
        ids.push(record_id);
    }
    Ok(ids)
}

fn deletable_debt_linked_record_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
) -> StorageResult<Vec<i64>> {
    let mut stmt = tx
        .prepare(
            "SELECT id
             FROM records
             WHERE transfer_id IS NULL
               AND related_debt_id IS NOT NULL
               AND type IN ('income', 'expense')
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn skipped_operation_record_count_in_tx(
    tx: &rusqlite::Transaction<'_>,
    transfer_ids: &[i64],
) -> StorageResult<i64> {
    let selected_transfers: HashSet<i64> = transfer_ids.iter().copied().collect();
    let mut stmt = tx
        .prepare("SELECT type, transfer_id, description FROM records")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<i64>>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(sqlite_err)?;
    let mut skipped = 0_i64;
    for row in rows {
        let (record_type, transfer_id, description) = row.map_err(sqlite_err)?;
        if let Some(transfer_id) = transfer_id {
            if !selected_transfers.contains(&transfer_id) {
                skipped += 1;
            }
            continue;
        }
        if transfer_marker_id(&description)
            .is_some_and(|marker_transfer_id| !selected_transfers.contains(&marker_transfer_id))
        {
            skipped += 1;
            continue;
        }
        if record_type != "income" && record_type != "expense" && record_type != "mandatory_expense"
        {
            skipped += 1;
        }
    }
    Ok(skipped)
}

fn validate_selected_operation_record_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_ids: &[i64],
    selected_transfer_ids: &[i64],
) -> StorageResult<Vec<i64>> {
    let selected_transfers: HashSet<i64> = selected_transfer_ids.iter().copied().collect();
    let normalized = normalize_positive_ids(record_ids, "Record")?;
    let mut selected_records = Vec::new();
    for record_id in normalized {
        let row = tx
            .query_row(
                "SELECT type, transfer_id, related_debt_id, description
                 FROM records
                 WHERE id = ?1",
                [record_id],
                |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, Option<i64>>(1)?,
                        row.get::<_, Option<i64>>(2)?,
                        row.get::<_, String>(3)?,
                    ))
                },
            )
            .optional()
            .map_err(sqlite_err)?;
        let Some((record_type, transfer_id, related_debt_id, description)) = row else {
            return Err(format!("Record not found: {record_id}"));
        };
        if let Some(transfer_id) = transfer_id {
            return Err(format!(
                "Select transfer #{transfer_id} instead of linked record #{record_id}"
            ));
        }
        if record_type != "income" && record_type != "expense" && record_type != "mandatory_expense"
        {
            return Err(
                "Only income, expense, and mandatory_expense records can be bulk deleted from Operations".to_owned(),
            );
        }
        if let Some(debt_id) = related_debt_id {
            debt_payment_for_record_in_tx(tx, debt_id, record_id)?;
        }
        if let Some(marker_transfer_id) = transfer_marker_id(&description) {
            if selected_transfers.contains(&marker_transfer_id) {
                continue;
            }
            return Err("Transfer commission must be deleted with its transfer".to_owned());
        }
        selected_records.push(record_id);
    }
    Ok(selected_records)
}

fn partition_operation_record_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_ids: &[i64],
) -> StorageResult<(Vec<i64>, Vec<i64>)> {
    let mut standalone_record_ids = Vec::new();
    let mut debt_linked_record_ids = Vec::new();
    for record_id in record_ids {
        let related_debt_id = tx
            .query_row(
                "SELECT related_debt_id FROM records WHERE id = ?1",
                [record_id],
                |row| row.get::<_, Option<i64>>(0),
            )
            .optional()
            .map_err(sqlite_err)?
            .ok_or_else(|| format!("Record not found: {record_id}"))?;
        if related_debt_id.is_some() {
            debt_linked_record_ids.push(*record_id);
        } else {
            standalone_record_ids.push(*record_id);
        }
    }
    Ok((standalone_record_ids, debt_linked_record_ids))
}

fn delete_operations_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_ids: &[i64],
    debt_linked_record_ids: &[i64],
    transfer_ids: &[i64],
    skipped_records: i64,
) -> StorageResult<OperationDeleteResult> {
    for transfer_id in transfer_ids {
        ensure_transfer_exists_in_tx(tx, *transfer_id)?;
        transfer_linked_record_ids_in_tx(tx, *transfer_id)?;
    }

    let mut deleted_records = 0_i64;
    for record_id in record_ids {
        deleted_records += delete_operation_record_in_tx(tx, *record_id)? as i64;
    }

    let mut deleted_debt_linked_records = 0_i64;
    for record_id in debt_linked_record_ids {
        deleted_debt_linked_records += delete_operation_record_in_tx(tx, *record_id)? as i64;
    }

    let mut deleted_transfers = 0_i64;
    for transfer_id in transfer_ids {
        let commission_marker = format!("[transfer:{transfer_id}]");
        tx.execute(
            "DELETE FROM record_tags
             WHERE record_id IN (
                 SELECT id FROM records
                 WHERE transfer_id = ?1
                    OR (
                        transfer_id IS NULL
                        AND related_debt_id IS NULL
                        AND category = 'Commission'
                        AND description = ?2
                    )
             )",
            (transfer_id, commission_marker.as_str()),
        )
        .map_err(sqlite_err)?;
        tx.execute("DELETE FROM records WHERE transfer_id = ?1", [transfer_id])
            .map_err(sqlite_err)?;
        tx.execute(
            "DELETE FROM records
             WHERE transfer_id IS NULL
               AND related_debt_id IS NULL
               AND category = 'Commission'
               AND description = ?1",
            [commission_marker.as_str()],
        )
        .map_err(sqlite_err)?;
        deleted_transfers += tx
            .execute("DELETE FROM transfers WHERE id = ?1", [transfer_id])
            .map_err(sqlite_err)? as i64;
    }

    refresh_tag_metrics_in_tx(tx)?;
    prune_orphan_tags_in_tx(tx)?;
    Ok(OperationDeleteResult {
        deleted_records,
        deleted_transfers,
        deleted_debt_linked_records,
        skipped_records,
    })
}

fn delete_operation_record_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_id: i64,
) -> StorageResult<usize> {
    let row = tx
        .query_row(
            "SELECT type, transfer_id, related_debt_id, description
             FROM records
             WHERE id = ?1",
            [record_id],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, Option<i64>>(1)?,
                    row.get::<_, Option<i64>>(2)?,
                    row.get::<_, String>(3)?,
                ))
            },
        )
        .optional()
        .map_err(sqlite_err)?;
    let Some((record_type, transfer_id, related_debt_id, description)) = row else {
        return Err(format!("Record not found: {record_id}"));
    };
    if let Some(transfer_id) = transfer_id {
        return Err(format!(
            "Select transfer #{transfer_id} instead of linked record #{record_id}"
        ));
    }
    if record_type != "income" && record_type != "expense" && record_type != "mandatory_expense" {
        return Err(
            "Only income, expense, and mandatory_expense records can be deleted from Operations"
                .to_owned(),
        );
    }
    if related_debt_id.is_none() && transfer_marker_id(&description).is_some() {
        return Err("Transfer commission must be deleted with its transfer".to_owned());
    }

    match related_debt_id {
        Some(debt_id) => delete_debt_linked_operation_record_in_tx(tx, record_id, debt_id),
        None => {
            tx.execute("DELETE FROM record_tags WHERE record_id = ?1", [record_id])
                .map_err(sqlite_err)?;
            tx.execute("DELETE FROM records WHERE id = ?1", [record_id])
                .map_err(sqlite_err)
        }
    }
}

fn debt_payment_for_record_in_tx(
    tx: &rusqlite::Transaction<'_>,
    debt_id: i64,
    record_id: i64,
) -> StorageResult<Option<i64>> {
    let mut stmt = tx
        .prepare(
            "SELECT id
             FROM debt_payments
             WHERE debt_id = ?1
               AND record_id = ?2
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map((debt_id, record_id), |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    let mut payment_ids = Vec::new();
    for row in rows {
        payment_ids.push(row.map_err(sqlite_err)?);
    }
    match payment_ids.as_slice() {
        [payment_id] => Ok(Some(*payment_id)),
        [] => Ok(None),
        _ => Err(format!(
            "Debt-linked record #{record_id} has multiple matching debt payments"
        )),
    }
}

fn delete_debt_linked_operation_record_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_id: i64,
    debt_id: i64,
) -> StorageResult<usize> {
    let Some(payment_id) = debt_payment_for_record_in_tx(tx, debt_id, record_id)? else {
        tx.execute("DELETE FROM record_tags WHERE record_id = ?1", [record_id])
            .map_err(sqlite_err)?;
        return tx
            .execute("DELETE FROM records WHERE id = ?1", [record_id])
            .map_err(sqlite_err);
    };
    let principal_paid_minor: i64 = tx
        .query_row(
            "SELECT principal_paid_minor
             FROM debt_payments
             WHERE id = ?1",
            [payment_id],
            |row| row.get(0),
        )
        .map_err(sqlite_err)?;
    let debt_row = tx
        .query_row(
            "SELECT total_amount_minor, remaining_amount_minor, status, closed_at
             FROM debts
             WHERE id = ?1",
            [debt_id],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, Option<String>>(3)?,
                ))
            },
        )
        .optional()
        .map_err(sqlite_err)?;
    let Some((total_amount_minor, remaining_amount_minor, status, closed_at)) = debt_row else {
        return Err(format!("Debt not found: {debt_id}"));
    };

    tx.execute("DELETE FROM record_tags WHERE record_id = ?1", [record_id])
        .map_err(sqlite_err)?;
    let deleted = tx
        .execute("DELETE FROM records WHERE id = ?1", [record_id])
        .map_err(sqlite_err)?;
    tx.execute("DELETE FROM debt_payments WHERE id = ?1", [payment_id])
        .map_err(sqlite_err)?;
    let restored_remaining =
        (remaining_amount_minor + principal_paid_minor).min(total_amount_minor);
    let next_status = if restored_remaining > 0 {
        "open".to_owned()
    } else {
        status
    };
    let next_closed_at = if restored_remaining > 0 {
        None
    } else {
        closed_at
    };
    tx.execute(
        "UPDATE debts
         SET remaining_amount_minor = ?1,
             status = ?2,
             closed_at = ?3
         WHERE id = ?4",
        (
            restored_remaining,
            next_status.as_str(),
            next_closed_at.as_deref(),
            debt_id,
        ),
    )
    .map_err(sqlite_err)?;
    Ok(deleted)
}

struct TransferCommissionMarker {
    record_type: String,
    date: String,
    wallet_id: i64,
    category: String,
    description: String,
}

fn transfer_commission_marker_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_id: i64,
) -> StorageResult<Option<TransferCommissionMarker>> {
    let row = tx
        .query_row(
            "SELECT type, date, wallet_id, category, description
             FROM records
             WHERE id = ?1
               AND transfer_id IS NULL
               AND related_debt_id IS NULL",
            [record_id],
            |row| {
                Ok(TransferCommissionMarker {
                    record_type: row.get(0)?,
                    date: row.get(1)?,
                    wallet_id: row.get(2)?,
                    category: row.get(3)?,
                    description: row.get(4)?,
                })
            },
        )
        .optional()
        .map_err(sqlite_err)?;
    Ok(row.filter(|row| transfer_marker_id(&row.description).is_some()))
}

fn transfer_marker_id(description: &str) -> Option<i64> {
    let marker = description.trim();
    let id_text = marker
        .strip_prefix("[transfer:")
        .and_then(|value| value.strip_suffix(']'))?;
    let id = id_text.parse::<i64>().ok()?;
    (id > 0).then_some(id)
}

fn validate_transfer_commission_update(
    marker: &TransferCommissionMarker,
    payload: &StandaloneRecordUpdatePayload,
) -> StorageResult<()> {
    if payload.record_type.trim().to_lowercase() != marker.record_type
        || payload.date.trim() != marker.date
        || payload.wallet_id != marker.wallet_id
        || payload.category.trim() != marker.category
        || payload.description.trim() != marker.description
    {
        return Err(
            "Transfer commission date, wallet, type, category, and marker description are controlled by the transfer"
                .to_owned(),
        );
    }
    Ok(())
}

fn validate_mandatory_template_create_payload_in_tx(
    tx: &rusqlite::Transaction<'_>,
    payload: &MandatoryTemplateCreatePayload,
) -> StorageResult<()> {
    validate_active_wallet_for_mandatory_in_tx(tx, payload.wallet_id)?;
    let category = payload.category.trim();
    if category.is_empty() {
        return Err("Mandatory category is required".to_owned());
    }
    let description = payload.description.trim();
    if description.is_empty() {
        return Err("Mandatory description is required".to_owned());
    }
    validate_mandatory_period(&payload.period)?;
    let date = payload.date.trim();
    if !date.is_empty() {
        validate_ymd_syntax(date)?;
    }
    let currency = payload.currency.trim().to_uppercase();
    validate_currency_code(&currency)?;
    let base_currency = base_currency_code_in_tx(tx)?;
    validate_mandatory_base_currency_only(&currency, &base_currency)?;
    let amount_original_minor = to_minor_units(&payload.amount_original)?;
    let amount_base_minor = to_minor_units(&payload.amount_base)?;
    if amount_original_minor <= 0 || amount_base_minor <= 0 {
        return Err("Mandatory amount must be positive".to_owned());
    }
    let rate_text = quantize_rate_text(&payload.rate_at_operation)?;
    let rate = rate_text
        .parse::<f64>()
        .map_err(|_| "invalid mandatory rate_at_operation".to_owned())?;
    if rate <= 0.0 {
        return Err("Mandatory rate_at_operation must be positive".to_owned());
    }
    Ok(())
}

fn validate_mandatory_template_update_payload_in_tx(
    tx: &rusqlite::Transaction<'_>,
    payload: &MandatoryTemplateUpdatePayload,
) -> StorageResult<()> {
    validate_active_wallet_for_mandatory_in_tx(tx, payload.wallet_id)?;
    validate_mandatory_period(&payload.period)?;
    let date = payload.date.trim();
    if !date.is_empty() {
        validate_ymd_syntax(date)?;
    }
    let amount_base_minor = to_minor_units(&payload.amount_base)?;
    if amount_base_minor <= 0 {
        return Err("Mandatory amount must be positive".to_owned());
    }
    Ok(())
}

fn insert_import_mandatory_template_in_tx(
    tx: &rusqlite::Transaction<'_>,
    template: &ParsedMandatoryTemplate,
) -> StorageResult<()> {
    tx.execute(
        "INSERT INTO mandatory_expenses (
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
            period,
            date,
            auto_pay
        )
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
        (
            template.wallet_id,
            template.amount_original,
            template.amount_original_minor,
            template.currency.as_str(),
            template.rate,
            template.rate_text.as_str(),
            template.amount_base,
            template.amount_base_minor,
            template.category.as_str(),
            template.description.as_str(),
            template.period.as_str(),
            template.date.as_str(),
            i64::from(!template.date.trim().is_empty()),
        ),
    )
    .map_err(sqlite_err)?;
    Ok(())
}

fn normalize_mandatory_description(description: &str, category: &str) -> String {
    let trimmed = description.trim();
    if trimmed.is_empty() {
        category.to_owned()
    } else {
        trimmed.to_owned()
    }
}

fn validate_active_wallet_for_mandatory_in_tx(
    tx: &rusqlite::Transaction<'_>,
    wallet_id: i64,
) -> StorageResult<TransferWallet> {
    if wallet_id <= 0 {
        return Err("Mandatory wallet is required".to_owned());
    }
    let wallet = tx
        .query_row(
            "SELECT id, allow_negative, is_active FROM wallets WHERE id = ?1",
            [wallet_id],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, i64>(1)? != 0,
                    row.get::<_, i64>(2)? != 0,
                ))
            },
        )
        .optional()
        .map_err(sqlite_err)?;
    let Some((id, allow_negative, is_active)) = wallet else {
        return Err(format!("Mandatory wallet not found: {wallet_id}"));
    };
    if !is_active {
        return Err("Mandatory wallet is inactive".to_owned());
    }
    Ok(TransferWallet { id, allow_negative })
}

fn validate_mandatory_period(value: &str) -> StorageResult<()> {
    match value.trim().to_lowercase().as_str() {
        "daily" | "weekly" | "monthly" | "yearly" => Ok(()),
        _ => Err("Invalid mandatory period".to_owned()),
    }
}

fn mandatory_template_in_tx(
    tx: &rusqlite::Transaction<'_>,
    template_id: i64,
) -> StorageResult<MandatoryExpenseRow> {
    tx.query_row(
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
            period,
            COALESCE(date, ''),
            auto_pay
         FROM mandatory_expenses
         WHERE id = ?1",
        [template_id],
        |row| {
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
        },
    )
    .optional()
    .map_err(sqlite_err)?
    .ok_or_else(|| format!("Mandatory template not found: {template_id}"))
}

fn mandatory_templates_in_tx(
    tx: &rusqlite::Transaction<'_>,
) -> StorageResult<Vec<MandatoryExpenseRow>> {
    let mut stmt = tx
        .prepare(
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
                period,
                COALESCE(date, ''),
                auto_pay
             FROM mandatory_expenses
             ORDER BY id",
        )
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| {
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
    rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
}

fn ensure_mandatory_template_exists_in_tx(
    tx: &rusqlite::Transaction<'_>,
    template_id: i64,
) -> StorageResult<()> {
    mandatory_template_in_tx(tx, template_id).map(|_| ())
}

fn insert_mandatory_record_from_template_in_tx(
    tx: &rusqlite::Transaction<'_>,
    template: &MandatoryExpenseRow,
    date: &str,
    wallet_id: i64,
    enforce_balance: bool,
) -> StorageResult<()> {
    let date = date.trim();
    if date.is_empty() {
        return Err("Mandatory record date is required".to_owned());
    }
    validate_ymd_date(date)?;
    let wallet = validate_active_wallet_for_mandatory_in_tx(tx, wallet_id)?;
    let amount_minor = to_minor_units(&template.amount_base.to_string())?;
    if amount_minor <= 0 {
        return Err("Mandatory amount must be positive".to_owned());
    }
    if enforce_balance && !wallet.allow_negative {
        let balance_minor = wallet_balance_minor_in_tx(tx, wallet.id)?;
        if balance_minor - amount_minor < 0 {
            return Err("Insufficient funds in wallet".to_owned());
        }
    }
    let amount_original_minor = to_minor_units(&template.amount_original.to_string())?;
    let rate_text = quantize_rate_text(&template.rate_at_operation.to_string())?;
    let rate_value = rate_text
        .parse::<f64>()
        .map_err(|_| "invalid mandatory rate_at_operation".to_owned())?;
    tx.execute(
        "INSERT INTO records (
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
        )
        VALUES ('mandatory_expense', ?1, ?2, NULL, NULL, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
        (
            date,
            wallet_id,
            template.amount_original,
            amount_original_minor,
            template.currency.as_str(),
            rate_value,
            rate_text.as_str(),
            template.amount_base,
            amount_minor,
            template.category.as_str(),
            template.description.as_str(),
            template.period.as_str(),
        ),
    )
    .map_err(sqlite_err)?;
    Ok(())
}

fn mandatory_generated_record_exists_in_tx(
    tx: &rusqlite::Transaction<'_>,
    template: &MandatoryExpenseRow,
    date: &str,
) -> StorageResult<bool> {
    tx.query_row(
        "SELECT 1
         FROM records
         WHERE type = 'mandatory_expense'
           AND wallet_id = ?1
           AND category = ?2
           AND description = ?3
           AND period = ?4
           AND date = ?5
         LIMIT 1",
        (
            template.wallet_id,
            template.category.as_str(),
            template.description.as_str(),
            template.period.as_str(),
            date,
        ),
        |_| Ok(()),
    )
    .optional()
    .map(|row| row.is_some())
    .map_err(sqlite_err)
}

fn normalize_mandatory_template_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
) -> StorageResult<HashMap<i64, i64>> {
    let mut stmt = tx
        .prepare("SELECT id FROM mandatory_expenses ORDER BY id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    let ordered_ids = rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)?;
    let id_map: HashMap<i64, i64> = ordered_ids
        .iter()
        .enumerate()
        .map(|(index, old_id)| (*old_id, i64::try_from(index + 1).unwrap_or(i64::MAX)))
        .collect();
    if id_map.iter().all(|(old_id, new_id)| old_id == new_id) {
        reset_sqlite_sequence_to_max_id_in_tx(tx, "mandatory_expenses")?;
        return Ok(id_map);
    }
    for (old_id, new_id) in &id_map {
        tx.execute(
            "UPDATE mandatory_expenses SET id = ?1 WHERE id = ?2",
            (-*new_id, old_id),
        )
        .map_err(sqlite_err)?;
    }
    for new_id in id_map.values() {
        tx.execute(
            "UPDATE mandatory_expenses SET id = ?1 WHERE id = ?2",
            (new_id, -*new_id),
        )
        .map_err(sqlite_err)?;
    }
    reset_sqlite_sequence_to_max_id_in_tx(tx, "mandatory_expenses")?;
    Ok(id_map)
}

fn active_wallet_in_tx(
    tx: &rusqlite::Transaction<'_>,
    wallet_id: i64,
    role: &str,
) -> StorageResult<TransferWallet> {
    let wallet = tx
        .query_row(
            "SELECT id, allow_negative, is_active FROM wallets WHERE id = ?1",
            [wallet_id],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, i64>(1)? != 0,
                    row.get::<_, i64>(2)? != 0,
                ))
            },
        )
        .optional()
        .map_err(sqlite_err)?;
    let Some((id, allow_negative, is_active)) = wallet else {
        return Err(format!("Transfer {role} wallet not found"));
    };
    if !is_active {
        return Err(format!("Transfer {role} wallet is inactive"));
    }
    Ok(TransferWallet { id, allow_negative })
}

fn wallet_balance_minor_in_tx(
    tx: &rusqlite::Transaction<'_>,
    wallet_id: i64,
) -> StorageResult<i64> {
    let initial_minor = tx
        .query_row(
            "SELECT COALESCE(initial_balance_minor, CAST(ROUND(initial_balance * 100.0) AS INTEGER), 0)
             FROM wallets
             WHERE id = ?1 AND is_active = 1",
            [wallet_id],
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)?;
    let signed_expr = signed_minor_amount_expr("amount_base", "type");
    let sql = format!("SELECT COALESCE(SUM({signed_expr}), 0) FROM records WHERE wallet_id = ?1");
    let delta_minor = tx
        .query_row(&sql, [wallet_id], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    Ok(initial_minor + delta_minor)
}

fn wallet_history_count_in_tx(
    tx: &rusqlite::Transaction<'_>,
    wallet_id: i64,
) -> StorageResult<i64> {
    let records_count = tx
        .query_row(
            "SELECT COUNT(*) FROM records WHERE wallet_id = ?1",
            [wallet_id],
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)?;
    let transfer_count = tx
        .query_row(
            "SELECT COUNT(*) FROM transfers WHERE from_wallet_id = ?1 OR to_wallet_id = ?1",
            [wallet_id],
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)?;
    let mandatory_count = tx
        .query_row(
            "SELECT COUNT(*) FROM mandatory_expenses WHERE wallet_id = ?1",
            [wallet_id],
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)?;
    Ok(records_count + transfer_count + mandatory_count)
}

fn reset_sqlite_sequence_to_max_id_in_tx(
    tx: &rusqlite::Transaction<'_>,
    table: &str,
) -> StorageResult<()> {
    let has_sequence = tx
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'",
            [],
            |_row| Ok(()),
        )
        .optional()
        .map_err(sqlite_err)?
        .is_some();
    if !has_sequence {
        return Ok(());
    }
    let max_id_sql = format!("SELECT COALESCE(MAX(id), 0) FROM {table}");
    let max_id = tx
        .query_row(&max_id_sql, [], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    tx.execute("DELETE FROM sqlite_sequence WHERE name = ?1", [table])
        .map_err(sqlite_err)?;
    if max_id > 0 {
        tx.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES(?1, ?2)",
            (table, max_id),
        )
        .map_err(sqlite_err)?;
    }
    Ok(())
}

fn wallet_balance_minor_excluding_transfer_in_tx(
    tx: &rusqlite::Transaction<'_>,
    wallet_id: i64,
    transfer_id: i64,
) -> StorageResult<i64> {
    let initial_minor = tx
        .query_row(
            "SELECT COALESCE(initial_balance_minor, CAST(ROUND(initial_balance * 100.0) AS INTEGER), 0)
             FROM wallets
             WHERE id = ?1 AND is_active = 1",
            [wallet_id],
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)?;
    let signed_expr = signed_minor_amount_expr("amount_base", "type");
    let marker = format!("[transfer:{transfer_id}]");
    let sql = format!(
        "SELECT COALESCE(SUM({signed_expr}), 0)
         FROM records
         WHERE wallet_id = ?1
           AND (transfer_id IS NULL OR transfer_id != ?2)
          AND NOT (transfer_id IS NULL AND description = ?3)"
    );
    let delta_minor = tx
        .query_row(&sql, (wallet_id, transfer_id, marker.as_str()), |row| {
            row.get::<_, i64>(0)
        })
        .map_err(sqlite_err)?;
    Ok(initial_minor + delta_minor)
}

#[allow(clippy::too_many_arguments)]
fn insert_transfer_record_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_type: &str,
    date: &str,
    wallet_id: i64,
    transfer_id: Option<i64>,
    amount_value: f64,
    amount_minor: i64,
    currency: &str,
    rate_value: f64,
    rate_text: &str,
    category: &str,
    description: &str,
) -> StorageResult<()> {
    tx.execute(
        "INSERT INTO records (
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
        )
        VALUES (?1, ?2, ?3, ?4, NULL, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, NULL)",
        (
            record_type,
            date,
            wallet_id,
            transfer_id,
            amount_value,
            amount_minor,
            currency,
            rate_value,
            rate_text,
            amount_value,
            amount_minor,
            category,
            description,
        ),
    )
    .map_err(sqlite_err)?;
    Ok(())
}

fn base_currency_code_in_tx(tx: &rusqlite::Transaction<'_>) -> StorageResult<String> {
    let has_schema_meta = tx
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'",
            [],
            |_row| Ok(()),
        )
        .optional()
        .map_err(sqlite_err)?
        .is_some();
    if !has_schema_meta {
        return Ok("KZT".to_owned());
    }
    let value = tx
        .query_row(
            "SELECT value FROM schema_meta WHERE key = 'base_currency' LIMIT 1",
            [],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(sqlite_err)?
        .unwrap_or_else(|| "KZT".to_owned());
    normalize_base_currency_code(&value)
}

fn base_currency_code_in_conn(conn: &Connection) -> StorageResult<String> {
    let has_schema_meta = conn
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'",
            [],
            |_row| Ok(()),
        )
        .optional()
        .map_err(sqlite_err)?
        .is_some();
    if !has_schema_meta {
        return Ok("KZT".to_owned());
    }
    let value = conn
        .query_row(
            "SELECT value FROM schema_meta WHERE key = 'base_currency' LIMIT 1",
            [],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(sqlite_err)?
        .unwrap_or_else(|| "KZT".to_owned());
    normalize_base_currency_code(&value)
}

fn normalize_base_currency_code(value: &str) -> StorageResult<String> {
    let normalized = value.trim().to_uppercase();
    if normalized.is_empty() {
        return Ok("KZT".to_owned());
    }
    validate_currency_code(&normalized)?;
    Ok(normalized)
}

fn validate_base_currency_only(currency: &str, base_currency: &str) -> StorageResult<()> {
    if currency.eq_ignore_ascii_case(base_currency) {
        Ok(())
    } else {
        Err(format!(
            "Standalone Operations currently supports base-currency records only ({base_currency})"
        ))
    }
}

fn validate_transfer_base_currency_only(currency: &str, base_currency: &str) -> StorageResult<()> {
    if currency.eq_ignore_ascii_case(base_currency) {
        Ok(())
    } else {
        Err(format!(
            "Transfer flow currently supports base-currency transfers only ({base_currency})"
        ))
    }
}

fn validate_mandatory_base_currency_only(currency: &str, base_currency: &str) -> StorageResult<()> {
    if currency.eq_ignore_ascii_case(base_currency) {
        Ok(())
    } else {
        Err(format!(
            "Kotlin Mandatory currently supports base-currency templates only ({base_currency})"
        ))
    }
}

fn validate_wallet_base_currency_only(currency: &str, base_currency: &str) -> StorageResult<()> {
    if currency.eq_ignore_ascii_case(base_currency) {
        Ok(())
    } else {
        Err(format!(
            "Kotlin Settings currently supports base-currency wallets only ({base_currency})"
        ))
    }
}

fn validate_ymd_date(value: &str) -> StorageResult<()> {
    let (year, month, day) = parse_ymd_parts(value)?;
    if (year, month, day) > current_local_date() {
        return Err("Date cannot be in the future".to_owned());
    }
    Ok(())
}

fn validate_ymd_syntax(value: &str) -> StorageResult<()> {
    parse_ymd_parts(value).map(|_| ())
}

fn parse_ymd_parts(value: &str) -> StorageResult<(i32, i32, i32)> {
    let bytes = value.as_bytes();
    if bytes.len() != 10 || bytes[4] != b'-' || bytes[7] != b'-' {
        return Err("Date must use YYYY-MM-DD format".to_owned());
    }
    let year = parse_date_part(value, 0, 4, "year")?;
    let month = parse_date_part(value, 5, 7, "month")?;
    let day = parse_date_part(value, 8, 10, "day")?;
    if !(1..=12).contains(&month) {
        return Err("Date month must be between 01 and 12".to_owned());
    }
    let max_day = days_in_month(year, month);
    if day < 1 || day > max_day {
        return Err(format!("Date day must be between 01 and {max_day:02}"));
    }
    Ok((year, month, day))
}

fn parse_date_part(value: &str, start: usize, end: usize, name: &str) -> StorageResult<i32> {
    let part = &value[start..end];
    if !part.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(format!("Date {name} must contain digits only"));
    }
    part.parse::<i32>()
        .map_err(|_| format!("Date {name} is invalid"))
}

fn days_in_month(year: i32, month: i32) -> i32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap_year(year) => 29,
        2 => 28,
        _ => 0,
    }
}

fn ymd_text(date: (i32, i32, i32)) -> String {
    format!("{:04}-{:02}-{:02}", date.0, date.1, date.2)
}

fn mandatory_auto_pay_target_date(
    period: &str,
    anchor: (i32, i32, i32),
    today: (i32, i32, i32),
) -> Option<(i32, i32, i32)> {
    match period.trim().to_lowercase().as_str() {
        "daily" => Some(today),
        "weekly" => {
            let anchor_weekday = weekday_index(anchor)?;
            let today_weekday = weekday_index(today)?;
            let delta_days = (today_weekday - anchor_weekday).rem_euclid(7);
            add_days(today, -delta_days)
        }
        "monthly" => {
            let day = anchor.2.min(days_in_month(today.0, today.1));
            Some((today.0, today.1, day))
        }
        "yearly" => {
            let day = anchor.2.min(days_in_month(today.0, anchor.1));
            Some((today.0, anchor.1, day))
        }
        _ => None,
    }
}

fn weekday_index(date: (i32, i32, i32)) -> Option<i32> {
    let (mut year, mut month, day) = date;
    if month < 3 {
        month += 12;
        year -= 1;
    }
    let k = year % 100;
    let j = year / 100;
    let h = (day + ((13 * (month + 1)) / 5) + k + (k / 4) + (j / 4) + (5 * j)) % 7;
    Some((h + 5) % 7)
}

fn add_days(date: (i32, i32, i32), delta: i32) -> Option<(i32, i32, i32)> {
    let mut year = date.0;
    let mut month = date.1;
    let mut day = date.2 + delta;
    while day < 1 {
        month -= 1;
        if month < 1 {
            month = 12;
            year -= 1;
        }
        day += days_in_month(year, month);
    }
    while day > days_in_month(year, month) {
        day -= days_in_month(year, month);
        month += 1;
        if month > 12 {
            month = 1;
            year += 1;
        }
    }
    Some((year, month, day))
}

fn is_leap_year(year: i32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn validate_currency_code(value: &str) -> StorageResult<()> {
    if value.len() != 3 || !value.bytes().all(|byte| byte.is_ascii_alphabetic()) {
        return Err("Currency code must contain 3 letters".to_owned());
    }
    if !is_supported_currency(value) {
        return Err("Unsupported currency".to_owned());
    }
    Ok(())
}

fn is_supported_currency(value: &str) -> bool {
    matches!(
        value.to_ascii_uppercase().as_str(),
        "KZT" | "USD" | "EUR" | "RUB"
    )
}

pub fn current_local_date() -> (i32, i32, i32) {
    current_local_date_impl().unwrap_or_else(today_utc)
}

#[cfg(windows)]
fn current_local_date_impl() -> Option<(i32, i32, i32)> {
    let mut local_time = SYSTEMTIME::default();
    unsafe {
        GetLocalTime(&mut local_time);
    }
    Some((
        i32::from(local_time.wYear),
        i32::from(local_time.wMonth),
        i32::from(local_time.wDay),
    ))
}

#[cfg(unix)]
fn current_local_date_impl() -> Option<(i32, i32, i32)> {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .ok()
        .and_then(|duration| libc::time_t::try_from(duration.as_secs()).ok())?;
    let mut local_time = std::mem::MaybeUninit::<libc::tm>::uninit();
    let result = unsafe { libc::localtime_r(&timestamp, local_time.as_mut_ptr()) };
    if result.is_null() {
        return None;
    }
    let local_time = unsafe { local_time.assume_init() };
    Some((
        local_time.tm_year + 1900,
        local_time.tm_mon + 1,
        local_time.tm_mday,
    ))
}

#[cfg(not(any(unix, windows)))]
fn current_local_date_impl() -> Option<(i32, i32, i32)> {
    None
}

fn today_utc() -> (i32, i32, i32) {
    let days_since_epoch = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| (duration.as_secs() / 86_400) as i64)
        .unwrap_or(0);
    civil_from_days(days_since_epoch)
}

fn civil_from_days(days_since_epoch: i64) -> (i32, i32, i32) {
    let z = days_since_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    let year = y + i64::from(month <= 2);
    (year as i32, month as i32, day as i32)
}

fn replace_record_tags_in_tx(
    tx: &rusqlite::Transaction<'_>,
    record_id: i64,
    tags: &[String],
    tag_colors: &[TagColorAssignment],
) -> StorageResult<()> {
    tx.execute("DELETE FROM record_tags WHERE record_id = ?1", [record_id])
        .map_err(sqlite_err)?;
    for tag_name in normalize_tag_names(tags) {
        let tag_id = ensure_tag_id_in_tx(tx, &tag_name, tag_colors)?;
        tx.execute(
            "INSERT OR IGNORE INTO record_tags (record_id, tag_id) VALUES (?1, ?2)",
            (record_id, tag_id),
        )
        .map_err(sqlite_err)?;
    }
    refresh_tag_metrics_in_tx(tx)?;
    prune_orphan_tags_in_tx(tx)?;
    Ok(())
}

fn ensure_tag_id_in_tx(
    tx: &rusqlite::Transaction<'_>,
    name: &str,
    tag_colors: &[TagColorAssignment],
) -> StorageResult<i64> {
    let normalized = normalize_tag_name(name);
    if normalized.is_empty() {
        return Err("Tag name must not be empty".to_owned());
    }
    let existing = tx
        .query_row(
            "SELECT id, name FROM tags WHERE lower(name) = lower(?1) LIMIT 1",
            [normalized.as_str()],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?)),
        )
        .optional()
        .map_err(sqlite_err)?;
    if let Some((tag_id, stored_name)) = existing {
        if stored_name != normalized {
            tx.execute(
                "UPDATE tags SET name = ?1 WHERE id = ?2",
                (normalized.as_str(), tag_id),
            )
            .map_err(sqlite_err)?;
        }
        let requested_color = requested_tag_color(tag_colors, &normalized)?;
        if let Some(color) = requested_color {
            validate_tag_color_assignment(tx, &normalized, &color)?;
            tx.execute(
                "UPDATE tags SET color = ?1 WHERE id = ?2",
                (color.as_str(), tag_id),
            )
            .map_err(sqlite_err)?;
        } else {
            let color = ensure_existing_tag_color_in_tx(tx, tag_id)?;
            if color.is_empty() {
                let color = first_free_tag_color_in_tx(tx)?;
                tx.execute(
                    "UPDATE tags SET color = ?1 WHERE id = ?2",
                    (color.as_str(), tag_id),
                )
                .map_err(sqlite_err)?;
            }
        }
        return Ok(tag_id);
    }

    let color = match requested_tag_color(tag_colors, &normalized)? {
        Some(color) => color,
        None => first_free_tag_color_in_tx(tx)?,
    };
    validate_tag_color_assignment(tx, &normalized, &color)?;
    tx.execute(
        "INSERT INTO tags (name, color, usage_count, last_used_at) VALUES (?1, ?2, 0, '')",
        (normalized.as_str(), color.as_str()),
    )
    .map_err(sqlite_err)?;
    Ok(tx.last_insert_rowid())
}

fn requested_tag_color(
    assignments: &[TagColorAssignment],
    name: &str,
) -> StorageResult<Option<String>> {
    let matches: Vec<&TagColorAssignment> = assignments
        .iter()
        .filter(|assignment| normalize_tag_name(&assignment.name) == name)
        .collect();
    if matches.len() > 1 {
        return Err(format!("Duplicate color assignment for tag: {name}"));
    }
    matches
        .first()
        .map(|assignment| {
            let color = assignment.color.trim().to_lowercase();
            if !is_valid_tag_color(&color) {
                return Err(format!("Unsupported tag color: {}", assignment.color));
            }
            Ok(color)
        })
        .transpose()
}

fn ensure_existing_tag_color_in_tx(
    tx: &rusqlite::Transaction<'_>,
    tag_id: i64,
) -> StorageResult<String> {
    tx.query_row(
        "SELECT COALESCE(color, '') FROM tags WHERE id = ?1",
        [tag_id],
        |row| row.get::<_, String>(0),
    )
    .map_err(sqlite_err)
}

fn first_free_tag_color_in_tx(tx: &rusqlite::Transaction<'_>) -> StorageResult<String> {
    let mut statement = tx
        .prepare("SELECT color FROM tags WHERE color IS NOT NULL AND color <> ''")
        .map_err(sqlite_err)?;
    let used: HashSet<String> = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(sqlite_err)?
        .collect::<Result<HashSet<_>, _>>()
        .map_err(sqlite_err)?;
    Ok(TAG_PALETTE
        .iter()
        .find(|color| !used.contains(**color))
        .unwrap_or(&NO_COLOR)
        .to_string())
}

fn validate_tag_color_assignment(
    tx: &rusqlite::Transaction<'_>,
    name: &str,
    color: &str,
) -> StorageResult<()> {
    if !is_valid_tag_color(color) {
        return Err(format!("Unsupported tag color: {color}"));
    }
    if color.is_empty() {
        return Ok(());
    }
    let conflict = tx
        .query_row(
            "SELECT name FROM tags WHERE lower(color) = lower(?1) AND lower(name) <> lower(?2) LIMIT 1",
            (color, name),
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(sqlite_err)?;
    if let Some(conflict) = conflict {
        return Err(format!(
            "Tag color {color} is already assigned to {conflict}"
        ));
    }
    Ok(())
}

fn normalize_tag_colors_in_tx(tx: &rusqlite::Transaction<'_>) -> StorageResult<()> {
    let mut statement = tx
        .prepare("SELECT id, color FROM tags ORDER BY id")
        .map_err(sqlite_err)?;
    let rows = statement
        .query_map([], |row| {
            Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(sqlite_err)?;
    let rows = rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)?;
    drop(statement);

    let mut used = HashSet::new();
    for (tag_id, stored_color) in rows {
        let normalized = stored_color.trim().to_lowercase();
        let keep = is_valid_tag_color(&normalized)
            && (normalized.is_empty() || used.insert(normalized.clone()));
        let color = if keep {
            normalized
        } else {
            let next = TAG_PALETTE
                .iter()
                .find(|candidate| !used.contains(**candidate))
                .unwrap_or(&NO_COLOR)
                .to_string();
            if !next.is_empty() {
                used.insert(next.clone());
            }
            next
        };
        if color != stored_color {
            tx.execute("UPDATE tags SET color = ?1 WHERE id = ?2", (color, tag_id))
                .map_err(sqlite_err)?;
        }
    }
    Ok(())
}

fn refresh_tag_metrics_in_tx(tx: &rusqlite::Transaction<'_>) -> StorageResult<()> {
    tx.execute(
        "UPDATE tags
         SET usage_count = (
             SELECT COUNT(*) FROM record_tags WHERE record_tags.tag_id = tags.id
         ),
         last_used_at = COALESCE((
             SELECT MAX(records.date)
             FROM record_tags
             JOIN records ON records.id = record_tags.record_id
             WHERE record_tags.tag_id = tags.id
         ), '')",
        [],
    )
    .map_err(sqlite_err)?;
    Ok(())
}

fn prune_orphan_tags_in_tx(tx: &rusqlite::Transaction<'_>) -> StorageResult<()> {
    tx.execute(
        "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM record_tags)",
        [],
    )
    .map_err(sqlite_err)?;
    Ok(())
}

fn normalize_tag_names(values: &[String]) -> Vec<String> {
    let mut normalized = Vec::new();
    for value in values {
        let name = normalize_tag_name(value);
        if name.is_empty() || normalized.contains(&name) {
            continue;
        }
        normalized.push(name);
        if normalized.len() >= 3 {
            break;
        }
    }
    normalized
}

fn normalize_tag_name(value: &str) -> String {
    let stripped = value.trim().replace('#', "");
    let cleaned: String = stripped
        .chars()
        .filter(|ch| {
            ch.is_ascii_alphanumeric() || ('А'..='Я').contains(ch) || ('а'..='я').contains(ch)
        })
        .flat_map(char::to_lowercase)
        .collect();
    if cleaned.is_empty() || cleaned.chars().all(|ch| ch.is_ascii_digit()) {
        String::new()
    } else {
        cleaned
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;
    use std::fs;
    use std::io::Read;
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '',
                usage_count INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT DEFAULT NULL
            );
            CREATE TABLE record_tags (
                record_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL
            );
            CREATE TABLE debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_name TEXT NOT NULL,
                kind TEXT NOT NULL,
                total_amount_minor INTEGER NOT NULL,
                remaining_amount_minor INTEGER NOT NULL,
                currency TEXT NOT NULL,
                interest_rate REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                closed_at TEXT
            );
            CREATE TABLE debt_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                debt_id INTEGER NOT NULL,
                record_id INTEGER,
                operation_type TEXT NOT NULL,
                principal_paid_minor INTEGER NOT NULL,
                is_write_off INTEGER NOT NULL DEFAULT 0,
                payment_date TEXT NOT NULL
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

    fn temp_test_path(prefix: &str, extension: &str) -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("{prefix}_{unique}.{extension}"))
    }

    fn insert_test_debt(conn: &Connection, debt_id: i64, contact_name: &str) {
        conn.execute(
            "INSERT INTO debts (
                id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                currency, interest_rate, status, created_at
             )
             VALUES (?1, ?2, 'debt', 10000, 5000, 'KZT', 0.0, 'open', '2026-01-05')",
            (debt_id, contact_name),
        )
        .unwrap();
    }

    fn insert_test_debt_record_payment(
        conn: &Connection,
        debt_id: i64,
        record_id: i64,
        payment_id: i64,
        description: &str,
    ) {
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
             )
             VALUES (
                ?1, 'income', '2026-01-05', 1, ?2,
                100.0, 10000, 'KZT', 1.0, '1.000000',
                100.0, 10000, 'Debt', ?3
             )",
            (record_id, debt_id, description),
        )
        .unwrap();
        conn.execute(
            "INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
             )
             VALUES (?1, ?2, ?3, 'create', 10000, 0, '2026-01-05')",
            (payment_id, debt_id, record_id),
        )
        .unwrap();
    }

    fn insert_test_debt_opening_record(
        conn: &Connection,
        debt_id: i64,
        record_id: i64,
        description: &str,
    ) {
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
             )
             VALUES (
                ?1, 'income', '2026-01-05', 1, ?2,
                100.0, 10000, 'KZT', 1.0, '1.000000',
                100.0, 10000, 'Debt', ?3
             )",
            (record_id, debt_id, description),
        )
        .unwrap();
    }

    fn remove_test_db(path: &str) {
        let _ = fs::remove_file(PathBuf::from(path));
    }

    fn write_operation_xlsx_fixture(path: &std::path::Path, rows: &[Vec<&str>]) {
        let mut worksheet = StyledWorksheet::new_records_sheet(
            "Data",
            &OPERATION_TABULAR_HEADERS,
            &OPERATION_XLSX_AMOUNT_COLUMNS,
            &OPERATION_XLSX_INTEGER_COLUMNS,
        )
        .unwrap();
        for row in rows {
            let mut values = row
                .iter()
                .map(|value| value.to_string())
                .collect::<Vec<_>>();
            if values.len() == 14 {
                values.insert(11, String::new());
                values.insert(12, String::new());
            }
            worksheet.append_row(&values).unwrap();
        }
        worksheet.save(path.to_str().unwrap()).unwrap();
    }

    fn write_mandatory_xlsx_fixture(path: &std::path::Path, rows: &[Vec<&str>]) {
        let mut worksheet = StyledWorksheet::new_records_sheet(
            "Mandatory",
            &MANDATORY_TABULAR_HEADERS,
            &MANDATORY_XLSX_AMOUNT_COLUMNS,
            &MANDATORY_XLSX_INTEGER_COLUMNS,
        )
        .unwrap();
        for row in rows {
            worksheet
                .append_row(
                    &row.iter()
                        .map(|value| value.to_string())
                        .collect::<Vec<_>>(),
                )
                .unwrap();
        }
        worksheet.save(path.to_str().unwrap()).unwrap();
    }

    fn xlsx_entry_text(path: &std::path::Path, entry_name: &str) -> String {
        let file = fs::File::open(path).unwrap();
        let mut archive = zip::ZipArchive::new(file).unwrap();
        let mut entry = archive.by_name(entry_name).unwrap();
        let mut text = String::new();
        entry.read_to_string(&mut text).unwrap();
        text
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
    fn balance_row_returns_one_active_wallet() {
        let db_path = create_balance_test_db();
        assert_eq!(
            wallet_balance_row(&db_path, 1).unwrap().unwrap(),
            (1, "Cash".to_owned(), "KZT".to_owned(), 1000.0, -150.0)
        );
        assert!(wallet_balance_row(&db_path, 3).unwrap().is_none());
        assert!(wallet_balance_row(&db_path, 99).unwrap().is_none());
        assert!(wallet_balance_row(&db_path, 0).unwrap().is_none());
        remove_test_db(&db_path);
    }

    #[test]
    fn create_wallet_creates_active_non_system_wallet_with_minor_balance() {
        let db_path = create_balance_test_db();
        let wallet = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Savings".to_owned(),
                currency: "kzt".to_owned(),
                initial_balance: "10.005".to_owned(),
                allow_negative: true,
            },
        )
        .unwrap();

        assert_eq!(wallet.id, 4);
        assert_eq!(wallet.name, "Savings");
        assert_eq!(wallet.currency, "KZT");
        assert_eq!(wallet.initial_balance, 10.01);
        assert!(!wallet.system);
        assert!(wallet.allow_negative);
        assert!(wallet.is_active);
        assert_eq!(
            wallet_balance_rows(&db_path, None)
                .unwrap()
                .into_iter()
                .find(|row| row.0 == wallet.id)
                .unwrap(),
            (4, "Savings".to_owned(), "KZT".to_owned(), 10.01, 0.0)
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn create_wallet_marks_first_wallet_as_system() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute("DELETE FROM record_tags", []).unwrap();
        conn.execute("DELETE FROM records", []).unwrap();
        conn.execute("DELETE FROM mandatory_expenses", []).unwrap();
        conn.execute("DELETE FROM transfers", []).unwrap();
        conn.execute("DELETE FROM wallets", []).unwrap();
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'wallets'", [])
            .unwrap();
        drop(conn);

        let first = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Main".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();
        let second = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Savings".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();

        assert_eq!(first.id, 1);
        assert!(first.system);
        assert_eq!(second.id, 2);
        assert!(!second.system);
        remove_test_db(&db_path);
    }

    #[test]
    fn create_wallet_rejects_duplicate_names_case_insensitively() {
        let db_path = create_balance_test_db();

        let first = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Savings".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();
        let error = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: " savings ".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "5".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap_err();

        assert_eq!(first.name, "Savings");
        assert_eq!(error, "Wallet name already exists: savings");
        remove_test_db(&db_path);
    }

    #[test]
    fn create_wallet_rejects_invalid_inputs() {
        let db_path = create_balance_test_db();
        let request = WalletCreatePayload {
            name: "Savings".to_owned(),
            currency: "KZT".to_owned(),
            initial_balance: "0".to_owned(),
            allow_negative: false,
        };

        assert!(
            create_wallet(
                &db_path,
                &WalletCreatePayload {
                    name: " ".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Wallet name is required")
        );
        assert!(
            create_wallet(
                &db_path,
                &WalletCreatePayload {
                    initial_balance: "-1".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Initial balance must be zero or a positive number")
        );
        assert!(
            create_wallet(
                &db_path,
                &WalletCreatePayload {
                    currency: "AAA".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Unsupported currency")
        );
        assert!(
            create_wallet(
                &db_path,
                &WalletCreatePayload {
                    currency: "USD".to_owned(),
                    ..request
                }
            )
            .unwrap_err()
            .contains("base-currency wallets only (KZT)")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_wallet_hard_deletes_zero_wallet_without_history() {
        let db_path = create_balance_test_db();
        let wallet = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Mistake".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();

        let result = delete_wallet(&db_path, wallet.id).unwrap();

        assert_eq!(result.wallet_id, wallet.id);
        assert_eq!(result.action, "hard_deleted");
        assert!(
            !wallet_list_rows(&db_path)
                .unwrap()
                .iter()
                .any(|row| row.id == wallet.id)
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_wallet_hard_delete_normalizes_wallet_autoincrement_sequence() {
        let db_path = create_balance_test_db();
        let mistaken = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Mistake".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();

        assert_eq!(mistaken.id, 4);
        assert_eq!(
            delete_wallet(&db_path, mistaken.id).unwrap().action,
            "hard_deleted"
        );

        let corrected = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Corrected".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();
        assert_eq!(corrected.id, mistaken.id);
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_wallet_soft_deletes_zero_wallet_with_record_history() {
        let db_path = create_balance_test_db();
        let wallet = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Archive".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "INSERT INTO records (type, date, wallet_id, amount_original, amount_original_minor, amount_base, amount_base_minor, category, description)
             VALUES ('income', '2026-01-05', ?1, 10.0, 1000, 10.0, 1000, 'Test', 'In')",
            [wallet.id],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (type, date, wallet_id, amount_original, amount_original_minor, amount_base, amount_base_minor, category, description)
             VALUES ('expense', '2026-01-06', ?1, 10.0, 1000, 10.0, 1000, 'Test', 'Out')",
            [wallet.id],
        )
        .unwrap();
        drop(conn);

        let result = delete_wallet(&db_path, wallet.id).unwrap();

        assert_eq!(result.action, "soft_deleted");
        let wallet = wallet_list_rows(&db_path)
            .unwrap()
            .into_iter()
            .find(|row| row.id == wallet.id)
            .unwrap();
        assert!(!wallet.is_active);
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_wallet_rejects_missing_system_inactive_and_non_zero_wallets() {
        let db_path = create_balance_test_db();

        assert!(
            delete_wallet(&db_path, 99)
                .unwrap_err()
                .contains("Wallet not found: 99")
        );
        assert!(
            delete_wallet(&db_path, 1)
                .unwrap_err()
                .contains("System wallet cannot be deleted")
        );
        assert!(
            delete_wallet(&db_path, 3)
                .unwrap_err()
                .contains("Wallet already inactive: 3")
        );
        assert!(
            delete_wallet(&db_path, 2)
                .unwrap_err()
                .contains("Wallet with non-zero balance cannot be deleted")
        );

        let wallet = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Initial".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "1".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();
        assert!(
            delete_wallet(&db_path, wallet.id)
                .unwrap_err()
                .contains("Wallet with non-zero balance cannot be deleted")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_wallet_treats_transfer_and_mandatory_rows_as_history() {
        let db_path = create_balance_test_db();
        let transfer_wallet = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "TransferArchive".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: true,
            },
        )
        .unwrap();
        let mandatory_wallet = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "MandatoryArchive".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .unwrap();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "INSERT INTO transfers (
                from_wallet_id, to_wallet_id, date, amount_original, amount_original_minor,
                currency, rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor, description
             ) VALUES (?1, 1, '2026-01-07', 0.0, 0, 'KZT', 1.0, '1.000000', 0.0, 0, 'Zero transfer')",
            [transfer_wallet.id],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO mandatory_expenses (
                wallet_id, amount_original, amount_original_minor, currency, rate_at_operation,
                rate_at_operation_text, amount_base, amount_base_minor, category, description,
                period, date, auto_pay
             ) VALUES (?1, 0.0, 0, 'KZT', 1.0, '1.000000', 0.0, 0, 'Zero', 'History', 'monthly', '2026-01-08', 0)",
            [mandatory_wallet.id],
        )
        .unwrap();
        drop(conn);

        assert_eq!(
            delete_wallet(&db_path, transfer_wallet.id).unwrap().action,
            "soft_deleted"
        );
        assert_eq!(
            delete_wallet(&db_path, mandatory_wallet.id).unwrap().action,
            "soft_deleted"
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_template_crud_add_to_records_and_id_normalization() {
        let db_path = create_balance_test_db();
        let created = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 1,
                amount_original: "25.255".to_owned(),
                currency: "kzt".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "25.255".to_owned(),
                category: "Utilities".to_owned(),
                description: "Internet".to_owned(),
                period: "monthly".to_owned(),
                date: "2026-02-01".to_owned(),
            },
        )
        .unwrap();
        assert_eq!(created.id, 2);
        assert_eq!(created.amount_base, 25.26);
        assert_eq!(created.currency, "KZT");
        assert!(created.auto_pay);

        let updated = mandatory_template_update(
            &db_path,
            created.id,
            &MandatoryTemplateUpdatePayload {
                wallet_id: 2,
                amount_base: "30".to_owned(),
                period: "weekly".to_owned(),
                date: "".to_owned(),
            },
        )
        .unwrap();
        assert_eq!(updated.wallet_id, 2);
        assert_eq!(updated.amount_base, 30.0);
        assert_eq!(updated.period, "weekly");
        assert!(!updated.auto_pay);

        let record = mandatory_add_to_records(
            &db_path,
            &MandatoryAddToRecordsPayload {
                template_id: updated.id,
                date: "2026-02-10".to_owned(),
                wallet_id: 2,
            },
        )
        .unwrap();
        assert_eq!(record.record_type, "mandatory_expense");
        assert_eq!(record.category, "Utilities");
        assert_eq!(record.wallet_id, 2);

        assert!(mandatory_template_delete(&db_path, 1).unwrap());
        let templates = mandatory_expense_rows(&db_path).unwrap();
        assert_eq!(templates.len(), 1);
        assert_eq!(templates[0].id, 1);

        let recreated = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Mandatory".to_owned(),
                description: "Recreated".to_owned(),
                period: "daily".to_owned(),
                date: "".to_owned(),
            },
        )
        .unwrap();
        assert_eq!(recreated.id, 2);
        assert_eq!(mandatory_template_delete_all(&db_path).unwrap(), 2);
        assert!(mandatory_expense_rows(&db_path).unwrap().is_empty());
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_template_rejects_invalid_inputs() {
        let db_path = create_balance_test_db();
        let request = MandatoryTemplateCreatePayload {
            wallet_id: 1,
            amount_original: "25".to_owned(),
            currency: "KZT".to_owned(),
            rate_at_operation: "1".to_owned(),
            amount_base: "25".to_owned(),
            category: "Mandatory".to_owned(),
            description: "Template".to_owned(),
            period: "monthly".to_owned(),
            date: "".to_owned(),
        };
        assert!(
            mandatory_template_create(
                &db_path,
                &MandatoryTemplateCreatePayload {
                    wallet_id: 3,
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("inactive")
        );
        assert!(
            mandatory_template_create(
                &db_path,
                &MandatoryTemplateCreatePayload {
                    amount_original: "0".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("positive")
        );
        assert!(
            mandatory_template_create(
                &db_path,
                &MandatoryTemplateCreatePayload {
                    currency: "USD".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("base-currency")
        );
        assert!(
            mandatory_template_create(
                &db_path,
                &MandatoryTemplateCreatePayload {
                    period: "quarterly".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("period")
        );
        assert!(
            mandatory_template_create(
                &db_path,
                &MandatoryTemplateCreatePayload {
                    date: "2026-02-30".to_owned(),
                    ..request
                }
            )
            .unwrap_err()
            .contains("Date day")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_add_to_records_rejects_future_date_and_insufficient_funds() {
        let db_path = create_balance_test_db();
        let template = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 1,
                amount_original: "2000".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "2000".to_owned(),
                category: "Rent".to_owned(),
                description: "Too much".to_owned(),
                period: "monthly".to_owned(),
                date: "".to_owned(),
            },
        )
        .unwrap();
        assert!(
            mandatory_add_to_records(
                &db_path,
                &MandatoryAddToRecordsPayload {
                    template_id: template.id,
                    date: "2999-01-01".to_owned(),
                    wallet_id: 1,
                }
            )
            .unwrap_err()
            .contains("future")
        );
        assert!(
            mandatory_add_to_records(
                &db_path,
                &MandatoryAddToRecordsPayload {
                    template_id: template.id,
                    date: "2026-02-01".to_owned(),
                    wallet_id: 1,
                }
            )
            .unwrap_err()
            .contains("Insufficient funds")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_auto_pay_creates_due_records_and_skips_duplicates() {
        let db_path = create_balance_test_db();
        let daily = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 2,
                amount_original: "5".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "5".to_owned(),
                category: "Daily".to_owned(),
                description: "Coffee".to_owned(),
                period: "daily".to_owned(),
                date: "2026-02-01".to_owned(),
            },
        )
        .unwrap();
        let monthly = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 2,
                amount_original: "7".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "7".to_owned(),
                category: "Monthly".to_owned(),
                description: "Month end".to_owned(),
                period: "monthly".to_owned(),
                date: "2026-01-31".to_owned(),
            },
        )
        .unwrap();
        let result = mandatory_apply_auto_payments(&db_path, "2026-02-28").unwrap();
        assert_eq!(result.created_records.len(), 3);
        assert!(
            result
                .created_records
                .iter()
                .any(|record| record.category == daily.category && record.date == "2026-02-28")
        );
        assert!(
            result.created_records.iter().any(|record| {
                record.category == monthly.category && record.date == "2026-02-28"
            })
        );

        let duplicate = mandatory_apply_auto_payments(&db_path, "2026-02-28").unwrap();
        assert!(duplicate.created_records.is_empty());

        let future = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 2,
                amount_original: "9".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "9".to_owned(),
                category: "Future".to_owned(),
                description: "Not yet".to_owned(),
                period: "daily".to_owned(),
                date: "2026-03-01".to_owned(),
            },
        )
        .unwrap();
        let skipped = mandatory_apply_auto_payments(&db_path, "2026-02-28").unwrap();
        assert!(
            skipped
                .created_records
                .iter()
                .all(|record| record.category != future.category)
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_auto_pay_skips_future_anchors_without_error() {
        let db_path = create_balance_test_db();
        let future = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 2,
                amount_original: "9".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "9".to_owned(),
                category: "Future".to_owned(),
                description: "Not yet".to_owned(),
                period: "daily".to_owned(),
                date: "2099-02-28".to_owned(),
            },
        )
        .unwrap();

        let result = mandatory_apply_auto_payments(&db_path, "2026-06-21").unwrap();

        assert!(
            result
                .created_records
                .iter()
                .all(|record| record.category != future.category)
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_auto_pay_monthly_waits_until_anchor_day_each_month() {
        let db_path = create_balance_test_db();
        let monthly = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 2,
                amount_original: "11".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "11".to_owned(),
                category: "Monthly".to_owned(),
                description: "Due on 13th".to_owned(),
                period: "monthly".to_owned(),
                date: "2026-03-13".to_owned(),
            },
        )
        .unwrap();

        let before_due = mandatory_apply_auto_payments(&db_path, "2026-06-12").unwrap();
        assert!(before_due.created_records.is_empty());

        let on_due = mandatory_apply_auto_payments(&db_path, "2026-06-13").unwrap();
        assert!(
            on_due
                .created_records
                .iter()
                .any(|record| record.category == monthly.category && record.date == "2026-06-13")
        );

        let duplicate = mandatory_apply_auto_payments(&db_path, "2026-06-21").unwrap();
        assert!(
            !duplicate.created_records.iter().any(|record| {
                record.category == monthly.category && record.date == "2026-06-13"
            })
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_auto_pay_daily_runs_each_day_after_anchor() {
        let db_path = create_balance_test_db();
        let daily = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 2,
                amount_original: "4".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "4".to_owned(),
                category: "Daily anchor".to_owned(),
                description: "Every day after anchor".to_owned(),
                period: "daily".to_owned(),
                date: "2026-06-20".to_owned(),
            },
        )
        .unwrap();

        let before_anchor = mandatory_apply_auto_payments(&db_path, "2026-06-19").unwrap();
        assert!(
            !before_anchor
                .created_records
                .iter()
                .any(|record| record.category == daily.category)
        );

        let on_anchor = mandatory_apply_auto_payments(&db_path, "2026-06-20").unwrap();
        assert!(
            on_anchor
                .created_records
                .iter()
                .any(|record| record.category == daily.category && record.date == "2026-06-20")
        );

        let next_day = mandatory_apply_auto_payments(&db_path, "2026-06-21").unwrap();
        assert!(
            next_day
                .created_records
                .iter()
                .any(|record| record.category == daily.category && record.date == "2026-06-21")
        );

        let duplicate = mandatory_apply_auto_payments(&db_path, "2026-06-21").unwrap();
        assert!(
            !duplicate
                .created_records
                .iter()
                .any(|record| record.category == daily.category && record.date == "2026-06-21")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_auto_pay_weekly_runs_on_anchor_weekday_each_week() {
        let db_path = create_balance_test_db();
        let weekly = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 2,
                amount_original: "6".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "6".to_owned(),
                category: "Weekly anchor".to_owned(),
                description: "Every Monday".to_owned(),
                period: "weekly".to_owned(),
                date: "2026-06-15".to_owned(),
            },
        )
        .unwrap();

        let before_anchor = mandatory_apply_auto_payments(&db_path, "2026-06-14").unwrap();
        assert!(
            !before_anchor
                .created_records
                .iter()
                .any(|record| record.category == weekly.category)
        );

        let on_anchor = mandatory_apply_auto_payments(&db_path, "2026-06-15").unwrap();
        assert!(
            on_anchor
                .created_records
                .iter()
                .any(|record| record.category == weekly.category && record.date == "2026-06-15")
        );

        let later_same_week = mandatory_apply_auto_payments(&db_path, "2026-06-18").unwrap();
        assert!(
            !later_same_week
                .created_records
                .iter()
                .any(|record| record.category == weekly.category && record.date == "2026-06-15")
        );

        let next_week = mandatory_apply_auto_payments(&db_path, "2026-06-22").unwrap();
        assert!(
            next_week
                .created_records
                .iter()
                .any(|record| record.category == weekly.category && record.date == "2026-06-22")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn mandatory_auto_pay_matches_legacy_balance_behavior() {
        let db_path = create_balance_test_db();
        mandatory_template_delete_all(&db_path).unwrap();
        let template = mandatory_template_create(
            &db_path,
            &MandatoryTemplateCreatePayload {
                wallet_id: 1,
                amount_original: "5000".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "5000".to_owned(),
                category: "Large autopay".to_owned(),
                description: "Legacy batch behavior".to_owned(),
                period: "daily".to_owned(),
                date: "2026-06-01".to_owned(),
            },
        )
        .unwrap();

        let manual = mandatory_add_to_records(
            &db_path,
            &MandatoryAddToRecordsPayload {
                template_id: template.id,
                date: "2026-06-02".to_owned(),
                wallet_id: 1,
            },
        )
        .unwrap_err();
        assert!(manual.contains("Insufficient funds in wallet"));

        let result = mandatory_apply_auto_payments(&db_path, "2026-06-02").unwrap();
        assert!(
            result.created_records.iter().any(|record| {
                record.category == "Large autopay" && record.date == "2026-06-02"
            })
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn import_export_mandatory_csv_replaces_templates_and_normalizes_ids() {
        let db_path = create_balance_test_db();
        let path = temp_test_path("ledgera_mandatory_import", "csv");
        fs::write(
            &path,
            "type,date,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,period\n\
mandatory_expense,2026-03-01,1,Rent,-100,KZT,1,100,,monthly\n\
mandatory_expense,,2,Phone,25,KZT,1,25,Mobile,weekly\n",
        )
        .unwrap();

        let preview = preview_import_mandatory_csv(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(preview.imported, 2);
        assert!(preview.errors.is_empty());
        assert_eq!(mandatory_expense_rows(&db_path).unwrap().len(), 1);

        let result = import_mandatory_csv(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(result.imported, 2);
        let templates = mandatory_expense_rows(&db_path).unwrap();
        assert_eq!(
            templates.iter().map(|row| row.id).collect::<Vec<_>>(),
            vec![1, 2]
        );
        assert_eq!(templates[0].description, "Rent");
        assert!(templates[0].auto_pay);
        assert_eq!(templates[0].amount_base, 100.0);
        assert!(!templates[1].auto_pay);

        let export_path = temp_test_path("ledgera_mandatory_export", "csv");
        let export = export_mandatory_csv(&db_path, export_path.to_str().unwrap()).unwrap();
        assert_eq!(export.exported_rows, 2);
        let exported = fs::read_to_string(&export_path).unwrap();
        assert!(exported.starts_with(
            "type,date,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,period"
        ));
        assert!(
            exported
                .contains("mandatory_expense,2026-03-01,1,Rent,100.00,KZT,1,100.00,Rent,monthly")
        );

        let _ = fs::remove_file(path);
        let _ = fs::remove_file(export_path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_export_mandatory_xlsx_uses_python_style_sheet() {
        let db_path = create_balance_test_db();
        let import_path = temp_test_path("ledgera_mandatory_import", "xlsx");
        write_mandatory_xlsx_fixture(
            &import_path,
            &[
                vec![
                    "mandatory_expense",
                    "2026-04-01",
                    "1",
                    "Utilities",
                    "50",
                    "KZT",
                    "1",
                    "50",
                    "Internet",
                    "monthly",
                ],
                vec![
                    "mandatory_expense",
                    "",
                    "2",
                    "Gym",
                    "30",
                    "KZT",
                    "1",
                    "30",
                    "Membership",
                    "yearly",
                ],
            ],
        );

        let preview =
            preview_import_mandatory_xlsx(&db_path, import_path.to_str().unwrap()).unwrap();
        assert_eq!(preview.imported, 2);
        import_mandatory_xlsx(&db_path, import_path.to_str().unwrap()).unwrap();
        let templates = mandatory_expense_rows(&db_path).unwrap();
        assert_eq!(templates.len(), 2);
        assert_eq!(templates[0].category, "Utilities");
        assert_eq!(templates[1].period, "yearly");

        let export_path = temp_test_path("ledgera_mandatory_export", "xlsx");
        let export = export_mandatory_xlsx(&db_path, export_path.to_str().unwrap()).unwrap();
        assert_eq!(export.exported_rows, 2);
        let sheet_xml = xlsx_entry_text(&export_path, "xl/worksheets/sheet1.xml");
        assert!(sheet_xml.contains("<sheetViews><sheetView"));
        assert!(sheet_xml.contains("<pane ySplit=\"1\" topLeftCell=\"A2\""));
        assert!(sheet_xml.contains("<autoFilter ref=\"A1:J3\""));
        let styles_xml = xlsx_entry_text(&export_path, "xl/styles.xml");
        assert!(styles_xml.contains("1F4E78"));
        assert!(styles_xml.contains("#,##0.00"));

        let _ = fs::remove_file(import_path);
        let _ = fs::remove_file(export_path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_mandatory_rejects_invalid_rows_without_replacing_existing_templates() {
        let db_path = create_balance_test_db();
        let path = temp_test_path("ledgera_mandatory_invalid", "csv");
        fs::write(
            &path,
            "type,date,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,period\n\
mandatory_expense,2026-02-30,1,Rent,100,KZT,1,100,Rent,monthly\n\
mandatory_expense,,99,Phone,25,KZT,1,25,Mobile,weekly\n\
expense,,1,Food,10,KZT,1,10,Wrong,monthly\n",
        )
        .unwrap();

        let preview = preview_import_mandatory_csv(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 3);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("Date day"))
        );
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("wallet not found"))
        );
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("unsupported type"))
        );
        let before = mandatory_expense_rows(&db_path).unwrap();
        let error = import_mandatory_csv(&db_path, path.to_str().unwrap()).unwrap_err();
        assert!(error.contains("Mandatory import contains validation errors"));
        assert_eq!(mandatory_expense_rows(&db_path).unwrap(), before);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_mandatory_rejects_empty_files_without_replacing_existing_templates() {
        let db_path = create_balance_test_db();
        let path = temp_test_path("ledgera_mandatory_empty", "csv");
        fs::write(
            &path,
            "type,date,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,period\n",
        )
        .unwrap();

        let before = mandatory_expense_rows(&db_path).unwrap();
        let preview = preview_import_mandatory_csv(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 0);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("Mandatory import contains no templates"))
        );

        let error = import_mandatory_csv(&db_path, path.to_str().unwrap()).unwrap_err();
        assert!(error.contains("Mandatory import contains no templates"));
        assert_eq!(mandatory_expense_rows(&db_path).unwrap(), before);

        let _ = fs::remove_file(path);
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
    fn standalone_record_update_replaces_tags_and_category_lookup_excludes_linked_rows() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "UPDATE records SET category = 'Transfer Mirror' WHERE id = 4",
            [],
        )
        .unwrap();
        drop(conn);

        let updated = update_standalone_record(
            &db_path,
            2,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: "2026-02-10".to_owned(),
                wallet_id: 2,
                amount_original: "75.25".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "75.25".to_owned(),
                category: "Dining".to_owned(),
                description: "Updated dinner".to_owned(),
                tags: vec!["work".to_owned(), "dining".to_owned(), "work".to_owned()],
            },
        )
        .unwrap();

        assert_eq!(updated.date, "2026-02-10");
        assert_eq!(updated.wallet_id, 2);
        assert_eq!(updated.amount_original, 75.25);
        assert_eq!(updated.category, "Dining");
        assert_eq!(updated.description, "Updated dinner");
        assert_eq!(updated.tags, vec!["dining".to_owned(), "work".to_owned()]);
        assert_eq!(
            tag_names(&db_path).unwrap(),
            vec!["dining".to_owned(), "work".to_owned()]
        );
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "INSERT INTO records
                (type, date, wallet_id, amount_original, amount_original_minor, currency,
                 rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor,
                 category, description)
             VALUES
                ('expense', '2026-02-11', 1, 1, 100, 'KZT', 1, '1', 1, 100, ' Dining ', 'Updated dinner')",
            [],
        )
        .unwrap();
        drop(conn);
        assert_eq!(
            distinct_record_categories(&db_path, "expense").unwrap(),
            vec!["Dining".to_owned()]
        );
        let suggestions = operation_suggestions(&db_path).unwrap();
        assert_eq!(
            suggestions.tags,
            vec!["dining".to_owned(), "work".to_owned()]
        );
        assert_eq!(suggestions.expense_categories, vec!["Dining".to_owned()]);
        assert_eq!(
            suggestions.expense_descriptions,
            vec!["Updated dinner".to_owned()]
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn distinct_record_descriptions_excludes_linked_rows_and_markers() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "UPDATE records SET description = '' WHERE transfer_id IS NULL",
            [],
        )
        .unwrap();
        conn.execute(
            "UPDATE records SET description = 'Transfer mirror' WHERE id = 4",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records
                (id, type, date, wallet_id, amount_original, amount_original_minor, currency,
                 rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor,
                 category, description)
             VALUES
                (100, 'income', '2026-02-01', 1, 10, 1000, 'KZT', 1, '1', 10, 1000, 'Salary', 'Payroll'),
                (101, 'expense', '2026-02-02', 1, 5, 500, 'KZT', 1, '1', 5, 500, 'Food', 'Lunch'),
                (102, 'expense', '2026-02-03', 1, 1, 100, 'KZT', 1, '1', 1, 100, 'Transfer', '[transfer:42]')",
            [],
        )
        .unwrap();
        drop(conn);

        assert_eq!(
            distinct_record_descriptions(&db_path, None).unwrap(),
            vec!["Lunch".to_owned(), "Payroll".to_owned()]
        );
        assert_eq!(
            distinct_record_descriptions(&db_path, Some("income")).unwrap(),
            vec!["Payroll".to_owned()]
        );
        assert_eq!(
            distinct_record_descriptions(&db_path, Some("expense")).unwrap(),
            vec!["Lunch".to_owned()]
        );
        assert!(distinct_record_descriptions(&db_path, Some("transfer")).is_err());
        remove_test_db(&db_path);
    }

    #[test]
    fn standalone_record_create_and_update_reject_invalid_dates() {
        let db_path = create_balance_test_db();
        let create_error = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "income".to_owned(),
                date: "2026-13-32".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Salary".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(create_error.contains("Date month must be between 01 and 12"));

        let update_error = update_standalone_record(
            &db_path,
            2,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: "2026-02-30".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(update_error.contains("Date day must be between 01 and 28"));
        remove_test_db(&db_path);
    }

    #[test]
    fn standalone_record_create_and_update_reject_future_dates() {
        let db_path = create_balance_test_db();
        let create_error = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "income".to_owned(),
                date: "2999-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Salary".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(create_error.contains("Date cannot be in the future"));

        let update_error = update_standalone_record(
            &db_path,
            2,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: "2999-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(update_error.contains("Date cannot be in the future"));
        remove_test_db(&db_path);
    }

    #[test]
    fn standalone_record_create_and_update_reject_invalid_currency() {
        let db_path = create_balance_test_db();
        let create_error = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "income".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "K1T".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Salary".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(create_error.contains("Currency code must contain 3 letters"));

        let update_error = update_standalone_record(
            &db_path,
            2,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "US1".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(update_error.contains("Currency code must contain 3 letters"));
        remove_test_db(&db_path);
    }

    #[test]
    fn standalone_record_create_and_update_reject_unsupported_currency() {
        let db_path = create_balance_test_db();
        let create_error = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "income".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "AAA".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Salary".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(create_error.contains("Unsupported currency"));

        let update_error = update_standalone_record(
            &db_path,
            2,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "AAA".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(update_error.contains("Unsupported currency"));
        remove_test_db(&db_path);
    }

    #[test]
    fn standalone_record_create_and_update_reject_non_base_currency() {
        let db_path = create_balance_test_db();
        let create_error = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "income".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "USD".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Salary".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(create_error.contains("base-currency records only (KZT)"));

        let update_error = update_standalone_record(
            &db_path,
            2,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "USD".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(update_error.contains("base-currency records only (KZT)"));
        remove_test_db(&db_path);
    }

    #[test]
    fn standalone_record_create_and_update_reject_non_positive_amounts() {
        let db_path = create_balance_test_db();
        let create_error = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "income".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "0".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "0".to_owned(),
                category: "Salary".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(create_error.contains("Record amount must be positive"));

        let update_error = update_standalone_record(
            &db_path,
            2,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "-1".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "-1".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(update_error.contains("Record amount must be positive"));
        remove_test_db(&db_path);
    }

    #[test]
    fn standalone_record_delete_removes_tags_and_rejects_linked_rows() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id, amount_original,
                amount_original_minor, amount_base, amount_base_minor, category
             ) VALUES (6, 'expense', '2026-01-05', 1, 10, 20.0, 2000, 20.0, 2000, 'Debt')",
            [],
        )
        .unwrap();
        drop(conn);

        assert!(
            update_standalone_record(
                &db_path,
                4,
                &StandaloneRecordUpdatePayload {
                    record_type: "expense".to_owned(),
                    date: "2026-01-10".to_owned(),
                    wallet_id: 1,
                    amount_original: "10".to_owned(),
                    currency: "KZT".to_owned(),
                    rate_at_operation: "1".to_owned(),
                    amount_base: "10".to_owned(),
                    category: "Blocked".to_owned(),
                    description: "".to_owned(),
                    tags: vec![],
                },
            )
            .unwrap_err()
            .contains("Only standalone records")
        );
        assert!(delete_standalone_record(&db_path, 2).unwrap());
        assert!(standalone_record_get_row(&db_path, 2).unwrap().is_none());
        assert!(tag_names(&db_path).unwrap().is_empty());
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_debt_linked_record_removes_payment_and_restores_debt() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_record_payment(&conn, 1, 6, 1, "Debt payment");
        drop(conn);

        assert!(delete_standalone_record(&db_path, 6).unwrap());

        let conn = Connection::open(&db_path).unwrap();
        let record_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM records WHERE id = 6", [], |row| {
                row.get(0)
            })
            .unwrap();
        let payment_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM debt_payments WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        let debt_state: (i64, String, Option<String>) = conn
            .query_row(
                "SELECT remaining_amount_minor, status, closed_at FROM debts WHERE id = 1",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(record_count, 0);
        assert_eq!(payment_count, 0);
        assert_eq!(debt_state, (10000, "open".to_owned(), None));
        remove_test_db(&db_path);
    }

    #[test]
    fn create_transfer_creates_transfer_and_linked_records() {
        let db_path = create_balance_test_db();
        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "125.505".to_owned(),
                currency: "kzt".to_owned(),
                description: "Move funds".to_owned(),
                commission_amount: "".to_owned(),
                commission_currency: "".to_owned(),
            },
        )
        .unwrap();

        assert_eq!(created.id, 2);
        assert_eq!(created.from_wallet_id, 1);
        assert_eq!(created.to_wallet_id, 2);
        assert_eq!(created.amount_original, 125.51);
        assert_eq!(created.currency, "KZT");
        assert_eq!(created.description, "Move funds");

        let linked: Vec<RecordRow> =
            filtered_record_list_rows(&db_path, &RecordFilterPayload::default())
                .unwrap()
                .into_iter()
                .filter(|record| record.transfer_id == Some(created.id))
                .collect();
        assert_eq!(linked.len(), 2);
        assert!(
            linked
                .iter()
                .any(|record| record.record_type == "expense" && record.wallet_id == 1)
        );
        assert!(
            linked
                .iter()
                .any(|record| record.record_type == "income" && record.wallet_id == 2)
        );
        assert_eq!(
            wallet_balance_rows(&db_path, None).unwrap()[0],
            (1, "Cash".to_owned(), "KZT".to_owned(), 1000.0, -275.51)
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn create_transfer_with_commission_creates_standalone_marker_record() {
        let db_path = create_balance_test_db();
        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "100".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move funds".to_owned(),
                commission_amount: "3.5".to_owned(),
                commission_currency: "kzt".to_owned(),
            },
        )
        .unwrap();

        let rows = filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        let commission = rows
            .iter()
            .find(|record| {
                record.transfer_id.is_none()
                    && record.description == format!("[transfer:{}]", created.id)
            })
            .unwrap();
        assert_eq!(commission.record_type, "expense");
        assert_eq!(commission.wallet_id, 1);
        assert_eq!(commission.amount_base, 3.5);
        assert_eq!(commission.category, "Commission");
        remove_test_db(&db_path);
    }

    #[test]
    fn create_transfer_normalizes_transfer_ids_after_gaps() {
        let db_path = create_balance_test_db();
        let second = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "100".to_owned(),
                currency: "KZT".to_owned(),
                description: "Second".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .unwrap();
        assert_eq!(second.id, 2);
        assert!(delete_transfer(&db_path, 1).unwrap());

        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-02".to_owned(),
                amount: "50".to_owned(),
                currency: "KZT".to_owned(),
                description: "Third".to_owned(),
                commission_amount: "1".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .unwrap();

        assert_eq!(created.id, 2);
        let transfers = transfer_list_rows(&db_path).unwrap();
        assert_eq!(
            transfers
                .iter()
                .map(|transfer| transfer.id)
                .collect::<Vec<_>>(),
            vec![1, 2]
        );
        let rows = record_list_rows(&db_path).unwrap();
        assert!(rows.iter().any(|record| record.transfer_id == Some(1)));
        assert!(rows.iter().any(|record| record.transfer_id == Some(2)));
        assert!(
            rows.iter()
                .any(|record| record.description == "[transfer:2]")
        );
        assert!(
            !rows
                .iter()
                .any(|record| record.description == "[transfer:3]")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn transfer_commission_marker_survives_standalone_amount_edit_and_transfer_delete() {
        let db_path = create_balance_test_db();
        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "100".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move funds".to_owned(),
                commission_amount: "3.5".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .unwrap();
        let marker = format!("[transfer:{}]", created.id);
        let commission = filtered_record_list_rows(&db_path, &RecordFilterPayload::default())
            .unwrap()
            .into_iter()
            .find(|record| record.transfer_id.is_none() && record.description == marker)
            .unwrap();

        let updated = update_standalone_record(
            &db_path,
            commission.id,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: commission.date,
                wallet_id: commission.wallet_id,
                amount_original: "7.25".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "7.25".to_owned(),
                category: "Commission".to_owned(),
                description: marker.clone(),
                tags: vec![],
            },
        )
        .unwrap();
        assert_eq!(updated.amount_base, 7.25);
        assert_eq!(updated.description, marker);

        assert!(delete_transfer(&db_path, created.id).unwrap());
        let rows = filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        assert!(!rows.iter().any(|record| record.description == marker));
        remove_test_db(&db_path);
    }

    #[test]
    fn standalone_crud_rejects_transfer_commission_marker_detach() {
        let db_path = create_balance_test_db();
        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "100".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move funds".to_owned(),
                commission_amount: "3.5".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .unwrap();
        let marker = format!("[transfer:{}]", created.id);
        let commission = filtered_record_list_rows(&db_path, &RecordFilterPayload::default())
            .unwrap()
            .into_iter()
            .find(|record| record.transfer_id.is_none() && record.description == marker)
            .unwrap();

        let update_error = update_standalone_record(
            &db_path,
            commission.id,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: commission.date,
                wallet_id: commission.wallet_id,
                amount_original: "7.25".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "7.25".to_owned(),
                category: "Fee".to_owned(),
                description: "edited".to_owned(),
                tags: vec![],
            },
        )
        .unwrap_err();
        assert!(update_error.contains("controlled by the transfer"));

        let delete_error = delete_standalone_record(&db_path, commission.id).unwrap_err();
        assert!(delete_error.contains("deleted with its transfer"));
        remove_test_db(&db_path);
    }

    #[test]
    fn update_transfer_updates_transfer_and_linked_records() {
        let db_path = create_balance_test_db();
        let updated = update_transfer(
            &db_path,
            1,
            &TransferUpdatePayload {
                from_wallet_id: 2,
                to_wallet_id: 1,
                date: "2026-02-10".to_owned(),
                amount: "80.255".to_owned(),
                currency: "kzt".to_owned(),
                description: "Back to cash".to_owned(),
            },
        )
        .unwrap();

        assert_eq!(updated.from_wallet_id, 2);
        assert_eq!(updated.to_wallet_id, 1);
        assert_eq!(updated.date, "2026-02-10");
        assert_eq!(updated.amount_original, 80.26);
        assert_eq!(updated.currency, "KZT");
        assert_eq!(updated.description, "Back to cash");

        let linked: Vec<RecordRow> =
            filtered_record_list_rows(&db_path, &RecordFilterPayload::default())
                .unwrap()
                .into_iter()
                .filter(|record| record.transfer_id == Some(1))
                .collect();
        assert_eq!(linked.len(), 2);
        let expense = linked
            .iter()
            .find(|record| record.record_type == "expense")
            .unwrap();
        let income = linked
            .iter()
            .find(|record| record.record_type == "income")
            .unwrap();
        assert_eq!(expense.wallet_id, 2);
        assert_eq!(income.wallet_id, 1);
        assert_eq!(expense.date, "2026-02-10");
        assert_eq!(income.amount_base, 80.26);
        assert_eq!(expense.description, "Back to cash");
        remove_test_db(&db_path);
    }

    #[test]
    fn update_transfer_moves_existing_commission_marker_without_changing_amount() {
        let db_path = create_balance_test_db();
        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "100".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move funds".to_owned(),
                commission_amount: "3.5".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .unwrap();

        update_transfer(
            &db_path,
            created.id,
            &TransferUpdatePayload {
                from_wallet_id: 2,
                to_wallet_id: 1,
                date: "2026-02-09".to_owned(),
                amount: "50".to_owned(),
                currency: "KZT".to_owned(),
                description: "Return funds".to_owned(),
            },
        )
        .unwrap();

        let rows = filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        let commission = rows
            .iter()
            .find(|record| {
                record.transfer_id.is_none()
                    && record.description == format!("[transfer:{}]", created.id)
            })
            .unwrap();
        assert_eq!(commission.wallet_id, 2);
        assert_eq!(commission.date, "2026-02-09");
        assert_eq!(commission.amount_base, 3.5);
        remove_test_db(&db_path);
    }

    #[test]
    fn create_transfer_rejects_invalid_inputs() {
        let db_path = create_balance_test_db();
        let request = TransferCreatePayload {
            from_wallet_id: 1,
            to_wallet_id: 2,
            date: "2026-02-01".to_owned(),
            amount: "100".to_owned(),
            currency: "KZT".to_owned(),
            description: "".to_owned(),
            commission_amount: "0".to_owned(),
            commission_currency: "KZT".to_owned(),
        };

        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    to_wallet_id: 1,
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("must be different")
        );
        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    to_wallet_id: 3,
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("target wallet is inactive")
        );
        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    to_wallet_id: 99,
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("target wallet not found")
        );
        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    date: "2026-02-30".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Date day must be between")
        );
        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    date: "2999-01-01".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Date cannot be in the future")
        );
        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    amount: "0".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Transfer amount must be positive")
        );
        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    commission_amount: "-1".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Commission amount must be non-negative")
        );
        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    currency: "USD".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("base-currency transfers only (KZT)")
        );
        assert!(
            create_transfer(
                &db_path,
                &TransferCreatePayload {
                    amount: "2000".to_owned(),
                    ..request
                }
            )
            .unwrap_err()
            .contains("Insufficient funds")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn update_transfer_rejects_invalid_inputs_and_corrupted_integrity() {
        let db_path = create_balance_test_db();
        let request = TransferUpdatePayload {
            from_wallet_id: 1,
            to_wallet_id: 2,
            date: "2026-02-01".to_owned(),
            amount: "100".to_owned(),
            currency: "KZT".to_owned(),
            description: "".to_owned(),
        };

        assert!(
            update_transfer(
                &db_path,
                1,
                &TransferUpdatePayload {
                    to_wallet_id: 1,
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("must be different")
        );
        assert!(
            update_transfer(
                &db_path,
                1,
                &TransferUpdatePayload {
                    to_wallet_id: 3,
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("target wallet is inactive")
        );
        assert!(
            update_transfer(
                &db_path,
                1,
                &TransferUpdatePayload {
                    date: "2026-02-30".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Date day must be between")
        );
        assert!(
            update_transfer(
                &db_path,
                1,
                &TransferUpdatePayload {
                    date: "2999-01-01".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Date cannot be in the future")
        );
        assert!(
            update_transfer(
                &db_path,
                1,
                &TransferUpdatePayload {
                    amount: "0".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Transfer amount must be positive")
        );
        assert!(
            update_transfer(
                &db_path,
                1,
                &TransferUpdatePayload {
                    currency: "USD".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("base-currency transfers only (KZT)")
        );
        assert!(
            update_transfer(
                &db_path,
                1,
                &TransferUpdatePayload {
                    amount: "2000".to_owned(),
                    ..request.clone()
                }
            )
            .unwrap_err()
            .contains("Insufficient funds")
        );

        let conn = Connection::open(&db_path).unwrap();
        conn.execute("DELETE FROM records WHERE id = 5", [])
            .unwrap();
        drop(conn);
        assert!(
            update_transfer(&db_path, 1, &request)
                .unwrap_err()
                .contains("expected 2 linked records")
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_transfer_removes_transfer_linked_records_and_commission_marker() {
        let db_path = create_balance_test_db();
        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "100".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move funds".to_owned(),
                commission_amount: "3.5".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .unwrap();

        assert!(delete_transfer(&db_path, created.id).unwrap());

        assert!(transfer_get_row(&db_path, created.id).unwrap().is_none());
        let rows = filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        assert!(
            !rows
                .iter()
                .any(|record| record.transfer_id == Some(created.id))
        );
        assert!(!rows.iter().any(|record| {
            record.transfer_id.is_none()
                && record.description == format!("[transfer:{}]", created.id)
        }));
        assert_eq!(
            wallet_balance_rows(&db_path, None)
                .unwrap()
                .into_iter()
                .find(|row| row.0 == 1)
                .unwrap(),
            (1, "Cash".to_owned(), "KZT".to_owned(), 1000.0, -150.0)
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_transfer_cleans_tags_without_deleting_unowned_marker_rows() {
        let db_path = create_balance_test_db();
        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "100".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move funds".to_owned(),
                commission_amount: "3.5".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .unwrap();
        let marker = format!("[transfer:{}]", created.id);
        let conn = Connection::open(&db_path).unwrap();
        let commission_id: i64 = conn
            .query_row(
                "SELECT id FROM records
                 WHERE transfer_id IS NULL
                   AND category = 'Commission'
                   AND description = ?1",
                [marker.as_str()],
                |row| row.get(0),
            )
            .unwrap();
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, transfer_id, related_debt_id,
                amount_original, amount_original_minor, amount_base, amount_base_minor,
                category, description
             ) VALUES (
                99, 'expense', '2026-02-01', 1, NULL, NULL,
                1.0, 100, 1.0, 100, 'General', ?1
             )",
            [marker.as_str()],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO tags (id, name) VALUES (10, 'transfer-tag')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO tags (id, name) VALUES (11, 'protected-tag')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO record_tags (record_id, tag_id) VALUES (?1, 10)",
            [commission_id],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO record_tags (record_id, tag_id) VALUES (99, 11)",
            [],
        )
        .unwrap();
        drop(conn);

        assert!(delete_transfer(&db_path, created.id).unwrap());

        let rows = filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        let protected_record_id = rows
            .iter()
            .find_map(|record| (record.description == marker).then_some(record.id))
            .expect("protected marker record");
        let conn = Connection::open(&db_path).unwrap();
        let record_tags: Vec<(i64, i64)> = {
            let mut stmt = conn
                .prepare("SELECT record_id, tag_id FROM record_tags ORDER BY record_id, tag_id")
                .unwrap();
            stmt.query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
                .unwrap()
                .collect::<Result<Vec<_>, _>>()
                .unwrap()
        };
        assert!(record_tags.contains(&(protected_record_id, 11)));
        assert!(
            !record_tags
                .iter()
                .any(|(record_id, _tag_id)| *record_id == commission_id)
        );
        let tags: Vec<String> = {
            let mut stmt = conn.prepare("SELECT name FROM tags ORDER BY id").unwrap();
            stmt.query_map([], |row| row.get(0))
                .unwrap()
                .collect::<Result<Vec<_>, _>>()
                .unwrap()
        };
        assert!(tags.contains(&"food".to_owned()));
        assert!(tags.contains(&"protected-tag".to_owned()));
        assert!(!tags.contains(&"transfer-tag".to_owned()));
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_transfer_rejects_missing_and_corrupted_integrity() {
        let db_path = create_balance_test_db();

        assert!(
            delete_transfer(&db_path, 99)
                .unwrap_err()
                .contains("Transfer not found: 99")
        );

        let conn = Connection::open(&db_path).unwrap();
        conn.execute("DELETE FROM records WHERE id = 5", [])
            .unwrap();
        drop(conn);

        assert!(
            delete_transfer(&db_path, 1)
                .unwrap_err()
                .contains("expected 2 linked records")
        );
        assert!(transfer_get_row(&db_path, 1).unwrap().is_some());
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_all_operations_removes_owned_records_and_skips_unsupported_rows() {
        let db_path = create_balance_test_db();
        let created = create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-02-01".to_owned(),
                amount: "100".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move funds".to_owned(),
                commission_amount: "3.5".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .unwrap();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_record_payment(&conn, 1, 60, 1, "Debt payment");
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id,
                amount_original, amount_original_minor, amount_base, amount_base_minor, category
             ) VALUES (61, 'expense', '2026-01-06', 1, 1, 10.0, 1000, 10.0, 1000, 'Detached debt row')",
            [],
        )
        .unwrap();
        drop(conn);

        let result = delete_all_operations(&db_path).unwrap();

        assert_eq!(
            result,
            OperationDeleteResult {
                deleted_records: 3,
                deleted_transfers: 2,
                deleted_debt_linked_records: 2,
                skipped_records: 0,
            }
        );
        assert!(transfer_get_row(&db_path, created.id).unwrap().is_none());
        let rows = filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        assert!(rows.is_empty());
        let conn = Connection::open(&db_path).unwrap();
        let payment_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM debt_payments", [], |row| row.get(0))
            .unwrap();
        let remaining: i64 = conn
            .query_row(
                "SELECT remaining_amount_minor FROM debts WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        let tag_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM tags", [], |row| row.get(0))
            .unwrap();
        assert_eq!(payment_count, 0);
        assert_eq!(remaining, 10000);
        assert_eq!(tag_count, 0);
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_operations_selection_removes_selected_records_and_transfers_only() {
        let db_path = create_balance_test_db();

        let result = delete_operations_selection(&db_path, &[2], &[1]).unwrap();

        assert_eq!(
            result,
            OperationDeleteResult {
                deleted_records: 1,
                deleted_transfers: 1,
                deleted_debt_linked_records: 0,
                skipped_records: 0,
            }
        );
        let rows = filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        let mut ids: Vec<i64> = rows.iter().map(|record| record.id).collect();
        ids.sort_unstable();
        assert_eq!(ids, vec![1, 2]);
        let created = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "income".to_owned(),
                date: "2026-02-10".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Next".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap();
        assert_eq!(created.id, 3);
        assert!(transfer_get_row(&db_path, 1).unwrap().is_none());
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_operations_selection_removes_debt_linked_record_and_payment() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_record_payment(&conn, 1, 6, 1, "Debt payment");
        drop(conn);

        let result = delete_operations_selection(&db_path, &[6], &[]).unwrap();

        assert_eq!(
            result,
            OperationDeleteResult {
                deleted_records: 0,
                deleted_transfers: 0,
                deleted_debt_linked_records: 1,
                skipped_records: 0,
            }
        );
        let conn = Connection::open(&db_path).unwrap();
        let payment_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM debt_payments", [], |row| row.get(0))
            .unwrap();
        let remaining: i64 = conn
            .query_row(
                "SELECT remaining_amount_minor FROM debts WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(payment_count, 0);
        assert_eq!(remaining, 10000);
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_operations_selection_removes_mandatory_expense_record() {
        let db_path = create_balance_test_db();

        let result = delete_operations_selection(&db_path, &[3], &[]).unwrap();

        assert_eq!(
            result,
            OperationDeleteResult {
                deleted_records: 1,
                deleted_transfers: 0,
                deleted_debt_linked_records: 0,
                skipped_records: 0,
            }
        );
        let rows = filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        assert!(
            !rows
                .iter()
                .any(|record| record.record_type == "mandatory_expense")
        );
        let created = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "income".to_owned(),
                date: "2026-02-10".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Next".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            },
        )
        .unwrap();
        assert_eq!(created.id, 5);
        remove_test_db(&db_path);
    }

    #[test]
    fn delete_operations_selection_rejects_linked_rows_without_partial_delete() {
        let db_path = create_balance_test_db();

        let error = delete_operations_selection(&db_path, &[4], &[]).unwrap_err();

        assert!(error.contains("Select transfer #1 instead of linked record #4"));
        assert_eq!(
            filtered_record_list_rows(&db_path, &RecordFilterPayload::default())
                .unwrap()
                .len(),
            5
        );
        assert!(transfer_get_row(&db_path, 1).unwrap().is_some());
        remove_test_db(&db_path);
    }

    #[test]
    fn import_export_records_csv_writes_operations_owned_rows_and_aggregate_transfer() {
        let db_path = create_balance_test_db();
        let path = std::env::temp_dir().join(format!(
            "ledgera_ops_export_{}.csv",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::write(&path, "stale export").unwrap();

        let result = export_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.exported_rows, 4);
        let contents = fs::read_to_string(&path).unwrap();
        assert!(!contents.contains("stale export"));
        assert!(contents.contains("date,type,wallet_id,category"));
        assert_eq!(contents.matches(",transfer,").count(), 1);
        assert!(contents.contains("Move to card"));
        assert!(contents.contains("mandatory_expense"));
        assert!(contents.contains("2026-01-03,mandatory_expense,2,Rent"));
        assert!(contents.contains("Monthly,,monthly,3"));

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_export_records_csv_round_trips_debt_linked_rows() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_record_payment(&conn, 1, 6, 1, "Debt opening");
        drop(conn);

        let path = temp_test_path("ledgera_ops_export_debt", "csv");
        export_records_csv(&db_path, path.to_str().unwrap()).unwrap();
        let contents = fs::read_to_string(&path).unwrap();
        assert!(contents.contains("record_id,related_debt_id,transfer_id"));
        assert!(contents.contains("Debt opening"));
        assert!(contents.contains(",6,1,,,"));

        let result = import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.imported, 5);
        assert_eq!(result.skipped, 0);
        let records = record_list_rows(&db_path).unwrap();
        let debt_records: Vec<_> = records
            .iter()
            .filter(|record| record.related_debt_id == Some(1))
            .collect();
        assert_eq!(debt_records.len(), 1);
        assert_eq!(debt_records[0].description, "Debt opening");
        let payment_record_id: i64 = Connection::open(&db_path)
            .unwrap()
            .query_row(
                "SELECT record_id FROM debt_payments WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(payment_record_id, debt_records[0].id);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_remaps_debt_payment_by_semantics_when_record_id_drifted() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
             )
             VALUES (
                8, 'expense', '2026-01-06', 1, 1,
                50.0, 5000, 'KZT', 1.0, '1.000000',
                50.0, 5000, 'Debt payment', 'Repay Alex'
             )",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
             )
             VALUES (1, 1, 99, 'debt_repay', 5000, 0, '2026-01-06')",
            [],
        )
        .unwrap();
        drop(conn);
        let path = temp_test_path("ledgera_ops_import_drifted_debt_payment", "csv");
        fs::write(
            &path,
            concat!(
                "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,tags,period,record_id,related_debt_id,transfer_id,from_wallet_id,to_wallet_id\n",
                "2026-01-06,expense,1,Debt payment,50,KZT,1,50,Repay Alex,,,8,1,,,\n"
            ),
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(preview.skipped, 0);
        assert!(!preview.blocking_errors);
        let result = import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.imported, 1);
        let conn = Connection::open(&db_path).unwrap();
        let payment_record_id: i64 = conn
            .query_row(
                "SELECT record_id FROM debt_payments WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        let linked_record: (String, i64) = conn
            .query_row(
                "SELECT description, related_debt_id FROM records WHERE id = ?1",
                [payment_record_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .unwrap();
        assert_eq!(linked_record, ("Repay Alex".to_owned(), 1));

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_semantic_remap_from_existing_other_record() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
             )
             VALUES (
                7, 'expense', '2026-01-06', 1, 1,
                50.0, 5000, 'KZT', 1.0, '1.000000',
                50.0, 5000, 'Debt payment', 'Existing repay'
             )",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
             )
             VALUES (
                8, 'expense', '2026-01-06', 1, 1,
                50.0, 5000, 'KZT', 1.0, '1.000000',
                50.0, 5000, 'Debt payment', 'Imported repay'
             )",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
             )
             VALUES (1, 1, 7, 'debt_repay', 5000, 0, '2026-01-06')",
            [],
        )
        .unwrap();
        drop(conn);
        let path = temp_test_path("ledgera_ops_import_existing_other_debt_payment", "csv");
        fs::write(
            &path,
            concat!(
                "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,tags,period,record_id,related_debt_id,transfer_id,from_wallet_id,to_wallet_id\n",
                "2026-01-06,expense,1,Debt payment,50,KZT,1,50,Imported repay,,,8,1,,,\n"
            ),
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| { error.contains("is already linked to existing record 7") })
        );
        let error = import_records_csv(&db_path, path.to_str().unwrap()).unwrap_err();
        assert!(error.contains("Operations import contains validation errors"));
        let payment_record_id: i64 = Connection::open(&db_path)
            .unwrap()
            .query_row(
                "SELECT record_id FROM debt_payments WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(payment_record_id, 7);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_existing_payment_like_orphan_debt_record() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
             )
             VALUES (
                8, 'expense', '2026-01-06', 1, 1,
                50.0, 5000, 'KZT', 1.0, '1.000000',
                50.0, 5000, 'Debt payment', 'Orphan repay'
             )",
            [],
        )
        .unwrap();
        drop(conn);
        let path = temp_test_path("ledgera_ops_import_orphan_debt_payment", "csv");
        fs::write(
            &path,
            concat!(
                "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,tags,period,record_id,related_debt_id,transfer_id,from_wallet_id,to_wallet_id\n",
                "2026-01-06,expense,1,Debt payment,50,KZT,1,50,Orphan repay,,,8,1,,,\n"
            ),
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| { error.contains("is not linked to payment history") })
        );
        let payment_count: i64 = Connection::open(&db_path)
            .unwrap()
            .query_row("SELECT COUNT(*) FROM debt_payments", [], |row| row.get(0))
            .unwrap();
        assert_eq!(payment_count, 0);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_export_records_csv_round_trips_debt_opening_rows_without_history() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_opening_record(&conn, 1, 6, "Debt opening");
        drop(conn);

        let path = temp_test_path("ledgera_ops_export_debt_opening", "csv");
        export_records_csv(&db_path, path.to_str().unwrap()).unwrap();
        let contents = fs::read_to_string(&path).unwrap();
        assert!(contents.contains("Debt opening"));
        assert!(contents.contains(",6,1,,,"));

        let result = import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.imported, 5);
        assert_eq!(result.skipped, 0);
        let records = record_list_rows(&db_path).unwrap();
        let debt_records: Vec<_> = records
            .iter()
            .filter(|record| record.related_debt_id == Some(1))
            .collect();
        assert_eq!(debt_records.len(), 1);
        assert_eq!(debt_records[0].description, "Debt opening");
        let payment_count: i64 = Connection::open(&db_path)
            .unwrap()
            .query_row("SELECT COUNT(*) FROM debt_payments", [], |row| row.get(0))
            .unwrap();
        assert_eq!(payment_count, 0);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_export_records_csv_round_trips_mandatory_expense_rows() {
        let db_path = create_balance_test_db();
        let path = temp_test_path("ledgera_ops_export_mandatory", "csv");
        export_records_csv(&db_path, path.to_str().unwrap()).unwrap();
        let contents = fs::read_to_string(&path).unwrap();
        assert!(contents.contains("mandatory_expense"));
        assert!(contents.contains(",mandatory_expense,2,Rent"));
        assert!(contents.contains("Monthly,,monthly,3"));

        let result = import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.imported, 4);
        assert_eq!(result.skipped, 0);
        let records = record_list_rows(&db_path).unwrap();
        let mandatory_rows: Vec<_> = records
            .iter()
            .filter(|record| record.record_type == "mandatory_expense")
            .collect();
        assert_eq!(mandatory_rows.len(), 1);
        assert_eq!(mandatory_rows[0].period.as_deref(), Some("monthly"));
        assert_eq!(mandatory_rows[0].category, "Rent");

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_invalid_mandatory_expense_rows() {
        let db_path = create_balance_test_db();
        let path = temp_test_path("ledgera_ops_import_invalid_mandatory", "csv");
        write_csv_rows(
            path.to_str().unwrap(),
            &OPERATION_TABULAR_HEADERS,
            &[
                vec![
                    "2026-01-05".to_owned(),
                    "mandatory_expense".to_owned(),
                    "1".to_owned(),
                    "Rent".to_owned(),
                    "100.00".to_owned(),
                    "KZT".to_owned(),
                    "1".to_owned(),
                    "100.00".to_owned(),
                    "Rent".to_owned(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                ],
                vec![
                    "2026-01-05".to_owned(),
                    "mandatory_expense".to_owned(),
                    "1".to_owned(),
                    "Rent".to_owned(),
                    "100.00".to_owned(),
                    "KZT".to_owned(),
                    "1".to_owned(),
                    "100.00".to_owned(),
                    "Rent".to_owned(),
                    String::new(),
                    "quarterly".to_owned(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                ],
                vec![
                    "2026-01-05".to_owned(),
                    "mandatory_expense".to_owned(),
                    "1".to_owned(),
                    "Rent".to_owned(),
                    "100.00".to_owned(),
                    "KZT".to_owned(),
                    "1".to_owned(),
                    "100.00".to_owned(),
                    "Rent".to_owned(),
                    String::new(),
                    "monthly".to_owned(),
                    String::new(),
                    "1".to_owned(),
                    String::new(),
                    String::new(),
                    String::new(),
                ],
                vec![
                    "2026-01-05".to_owned(),
                    "income".to_owned(),
                    "1".to_owned(),
                    "Salary".to_owned(),
                    "100.00".to_owned(),
                    "KZT".to_owned(),
                    "1".to_owned(),
                    "100.00".to_owned(),
                    "Salary".to_owned(),
                    String::new(),
                    "monthly".to_owned(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                    String::new(),
                ],
            ],
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 4);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("mandatory_expense requires period"))
        );
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("Invalid mandatory period"))
        );
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("mandatory_expense rows cannot be debt-linked"))
        );
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("period is only supported for mandatory_expense rows"))
        );
        let before = record_list_rows(&db_path).unwrap();
        let error = import_records_csv(&db_path, path.to_str().unwrap()).unwrap_err();
        assert!(error.contains("Operations import contains validation errors"));
        assert_eq!(record_list_rows(&db_path).unwrap(), before);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_debt_linked_row_without_record_id() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_opening_record(&conn, 1, 6, "Debt opening");
        drop(conn);
        let path = temp_test_path("ledgera_ops_import_debt_missing_record", "csv");
        write_csv_rows(
            path.to_str().unwrap(),
            &OPERATION_TABULAR_HEADERS,
            &[vec![
                "2026-01-05".to_owned(),
                "income".to_owned(),
                "1".to_owned(),
                "Debt".to_owned(),
                "100.00".to_owned(),
                "KZT".to_owned(),
                "1".to_owned(),
                "100.00".to_owned(),
                "Debt opening".to_owned(),
                String::new(),
                String::new(),
                String::new(),
                "1".to_owned(),
                String::new(),
                String::new(),
                String::new(),
            ]],
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 1);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("debt-linked rows require record_id"))
        );

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_debt_linked_row_for_missing_debt() {
        let db_path = create_balance_test_db();
        let path = temp_test_path("ledgera_ops_import_debt_missing_debt", "csv");
        write_csv_rows(
            path.to_str().unwrap(),
            &OPERATION_TABULAR_HEADERS,
            &[vec![
                "2026-01-05".to_owned(),
                "income".to_owned(),
                "1".to_owned(),
                "Debt".to_owned(),
                "100.00".to_owned(),
                "KZT".to_owned(),
                "1".to_owned(),
                "100.00".to_owned(),
                "Missing debt".to_owned(),
                String::new(),
                String::new(),
                "6".to_owned(),
                "99".to_owned(),
                String::new(),
                String::new(),
                String::new(),
            ]],
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 1);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("debt not found"))
        );
        let error = import_records_csv(&db_path, path.to_str().unwrap()).unwrap_err();
        assert!(error.contains("Operations import contains validation errors"));

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_duplicate_debt_linked_record_id() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_opening_record(&conn, 1, 6, "Debt opening");
        drop(conn);
        let path = temp_test_path("ledgera_ops_import_debt_duplicate_record", "csv");
        let row = vec![
            "2026-01-05".to_owned(),
            "income".to_owned(),
            "1".to_owned(),
            "Debt".to_owned(),
            "100.00".to_owned(),
            "KZT".to_owned(),
            "1".to_owned(),
            "100.00".to_owned(),
            "Debt opening".to_owned(),
            String::new(),
            String::new(),
            "6".to_owned(),
            "1".to_owned(),
            String::new(),
            String::new(),
            String::new(),
        ];
        write_csv_rows(
            path.to_str().unwrap(),
            &OPERATION_TABULAR_HEADERS,
            &[row.clone(), row],
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 1);
        assert_eq!(preview.skipped, 1);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("duplicate debt-linked record_id 6"))
        );

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_debt_payment_remap_to_wrong_debt() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt(&conn, 2, "Blair");
        insert_test_debt_record_payment(&conn, 1, 6, 1, "Debt opening");
        drop(conn);
        let path = temp_test_path("ledgera_ops_import_debt_wrong_remap", "csv");
        write_csv_rows(
            path.to_str().unwrap(),
            &OPERATION_TABULAR_HEADERS,
            &[vec![
                "2026-01-05".to_owned(),
                "income".to_owned(),
                "1".to_owned(),
                "Debt".to_owned(),
                "100.00".to_owned(),
                "KZT".to_owned(),
                "1".to_owned(),
                "100.00".to_owned(),
                "Wrong debt".to_owned(),
                String::new(),
                String::new(),
                "6".to_owned(),
                "2".to_owned(),
                String::new(),
                String::new(),
                String::new(),
            ]],
        )
        .unwrap();

        let error = import_records_csv(&db_path, path.to_str().unwrap()).unwrap_err();

        assert!(error.contains("does not belong to debt 2"));
        let conn = Connection::open(&db_path).unwrap();
        let payment_record_id: i64 = conn
            .query_row(
                "SELECT record_id FROM debt_payments WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(payment_record_id, 6);
        let wrong_record_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM records WHERE description = 'Wrong debt'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(wrong_record_count, 0);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_debt_payment_history_mismatch() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_record_payment(&conn, 1, 6, 1, "Debt payment");
        drop(conn);
        let path = temp_test_path("ledgera_ops_import_debt_history_mismatch", "csv");
        write_csv_rows(
            path.to_str().unwrap(),
            &OPERATION_TABULAR_HEADERS,
            &[vec![
                "2026-01-05".to_owned(),
                "income".to_owned(),
                "1".to_owned(),
                "Debt".to_owned(),
                "101.00".to_owned(),
                "KZT".to_owned(),
                "1".to_owned(),
                "101.00".to_owned(),
                "Changed payment".to_owned(),
                String::new(),
                String::new(),
                "6".to_owned(),
                "1".to_owned(),
                String::new(),
                String::new(),
                String::new(),
            ]],
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 1);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("does not match payment history"))
        );
        let error = import_records_csv(&db_path, path.to_str().unwrap()).unwrap_err();
        assert!(error.contains("Operations import contains validation errors"));
        let unchanged_count: i64 = Connection::open(&db_path)
            .unwrap()
            .query_row(
                "SELECT COUNT(*) FROM records WHERE description = 'Debt payment'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(unchanged_count, 1);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_multiple_debt_payment_backlinks() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_record_payment(&conn, 1, 6, 1, "Debt payment");
        conn.execute(
            "INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
             )
             VALUES (2, 1, 6, 'debt_repay', 10000, 0, '2026-01-05')",
            [],
        )
        .unwrap();
        drop(conn);
        let path = temp_test_path("ledgera_ops_import_debt_duplicate_payment", "csv");
        write_csv_rows(
            path.to_str().unwrap(),
            &OPERATION_TABULAR_HEADERS,
            &[vec![
                "2026-01-05".to_owned(),
                "income".to_owned(),
                "1".to_owned(),
                "Debt".to_owned(),
                "100.00".to_owned(),
                "KZT".to_owned(),
                "1".to_owned(),
                "100.00".to_owned(),
                "Debt payment".to_owned(),
                String::new(),
                String::new(),
                "6".to_owned(),
                "1".to_owned(),
                String::new(),
                String::new(),
                String::new(),
            ]],
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 1);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("multiple matching debt payments"))
        );

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_export_records_xlsx_round_trips_debt_linked_rows() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        insert_test_debt(&conn, 1, "Alex");
        insert_test_debt_record_payment(&conn, 1, 6, 1, "Debt opening");
        drop(conn);

        let path = temp_test_path("ledgera_ops_export_debt", "xlsx");
        export_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();
        let mut workbook = open_workbook_auto(&path).unwrap();
        let range = workbook.worksheet_range("Data").unwrap();
        let rows: Vec<Vec<String>> = range
            .rows()
            .map(|row| row.iter().map(xlsx_cell_to_string).collect())
            .collect();
        assert_eq!(
            rows[0],
            OPERATION_TABULAR_HEADERS
                .iter()
                .map(|value| value.to_string())
                .collect::<Vec<_>>()
        );
        assert!(rows.iter().any(|row| {
            row.get(8).map(String::as_str) == Some("Debt opening")
                && row.get(11).map(String::as_str) == Some("6")
                && row.get(12).map(String::as_str) == Some("1")
        }));

        let result = import_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.imported, 5);
        assert_eq!(result.skipped, 0);
        let records = record_list_rows(&db_path).unwrap();
        let debt_records: Vec<_> = records
            .iter()
            .filter(|record| record.related_debt_id == Some(1))
            .collect();
        assert_eq!(debt_records.len(), 1);
        assert_eq!(debt_records[0].description, "Debt opening");
        let payment_record_id: i64 = Connection::open(&db_path)
            .unwrap()
            .query_row(
                "SELECT record_id FROM debt_payments WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(payment_record_id, debt_records[0].id);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_xlsx_recreates_debt_payment_after_delete_all() {
        let db_path = create_balance_test_db();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "INSERT INTO debts (
                id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                currency, interest_rate, status, created_at
             )
             VALUES (1, 'Alex', 'debt', 10000, 5000, 'KZT', 0.0, 'open', '2026-01-01')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
             )
             VALUES (
                6, 'expense', '2026-01-05', 1, 1,
                50.0, 5000, 'KZT', 1.0, '1.000000',
                50.0, 5000, 'Debt payment', 'Repay Alex'
             )",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
             )
             VALUES (1, 1, 6, 'debt_repay', 5000, 0, '2026-01-05')",
            [],
        )
        .unwrap();
        drop(conn);
        let path = temp_test_path("ledgera_ops_reimport_debt_payment", "xlsx");
        export_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();

        delete_all_operations(&db_path).unwrap();
        let conn = Connection::open(&db_path).unwrap();
        let payment_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM debt_payments", [], |row| row.get(0))
            .unwrap();
        let restored_remaining: i64 = conn
            .query_row(
                "SELECT remaining_amount_minor FROM debts WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(payment_count, 0);
        assert_eq!(restored_remaining, 10000);
        drop(conn);

        let preview = preview_import_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(preview.skipped, 0);
        assert!(!preview.blocking_errors);
        let result = import_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();

        assert!(result.imported >= 1);
        let conn = Connection::open(&db_path).unwrap();
        let recreated_payment: (i64, i64, i64) = conn
            .query_row(
                "SELECT debt_id, record_id, principal_paid_minor FROM debt_payments",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(recreated_payment.0, 1);
        assert_eq!(recreated_payment.2, 5000);
        let linked_record_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM records WHERE id = ?1 AND related_debt_id = 1",
                [recreated_payment.1],
                |row| row.get(0),
            )
            .unwrap();
        let remaining: i64 = conn
            .query_row(
                "SELECT remaining_amount_minor FROM debts WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(linked_record_count, 1);
        assert_eq!(remaining, 5000);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_xlsx_rejects_debt_linked_row_for_missing_debt() {
        let db_path = create_balance_test_db();
        let path = temp_test_path("ledgera_ops_import_debt_missing_debt", "xlsx");
        write_operation_xlsx_fixture(
            &path,
            &[vec![
                "2026-01-05",
                "income",
                "1",
                "Debt",
                "100.00",
                "KZT",
                "1",
                "100.00",
                "Missing debt",
                "",
                "",
                "6",
                "99",
                "",
                "",
                "",
            ]],
        );

        let preview = preview_import_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 1);
        assert!(preview.blocking_errors);
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("debt not found"))
        );
        let error = import_records_xlsx(&db_path, path.to_str().unwrap()).unwrap_err();
        assert!(error.contains("Operations import contains validation errors"));

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn export_records_xlsx_writes_python_style_data_sheet() {
        let db_path = create_balance_test_db();
        let path = std::env::temp_dir().join(format!(
            "ledgera_ops_export_{}.xlsx",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));

        let result = export_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.exported_rows, 4);
        let mut workbook = open_workbook_auto(&path).unwrap();
        assert_eq!(workbook.sheet_names()[0], "Data");
        let range = workbook.worksheet_range("Data").unwrap();
        let raw_rows: Vec<Vec<Data>> = range.rows().map(|row| row.to_vec()).collect();
        let rows: Vec<Vec<String>> = range
            .rows()
            .map(|row| row.iter().map(xlsx_cell_to_string).collect())
            .collect();
        assert_eq!(
            rows[0],
            OPERATION_TABULAR_HEADERS
                .iter()
                .map(|value| value.to_string())
                .collect::<Vec<_>>()
        );
        assert!(
            rows.iter()
                .any(|row| row.get(1).map(String::as_str) == Some("transfer"))
        );
        assert!(
            rows.iter()
                .any(|row| row.iter().any(|cell| cell == "Move to card"))
        );
        let mandatory_row = rows
            .iter()
            .find(|row| row.get(1).map(String::as_str) == Some("mandatory_expense"))
            .unwrap();
        assert_eq!(mandatory_row.get(10).map(String::as_str), Some("monthly"));
        let transfer_row = raw_rows
            .iter()
            .find(|row| row.get(1).map(xlsx_cell_to_string).as_deref() == Some("transfer"))
            .unwrap();
        assert!(matches!(
            transfer_row.get(13),
            Some(Data::Int(1)) | Some(Data::Float(1.0))
        ));
        assert!(matches!(
            transfer_row.get(14),
            Some(Data::Int(1)) | Some(Data::Float(1.0))
        ));
        assert!(matches!(
            transfer_row.get(15),
            Some(Data::Int(2)) | Some(Data::Float(2.0))
        ));
        let standalone_row = raw_rows
            .iter()
            .find(|row| row.iter().any(|cell| xlsx_cell_to_string(cell) == "Food"))
            .unwrap();
        assert!(matches!(
            standalone_row.get(2),
            Some(Data::Int(1)) | Some(Data::Float(1.0))
        ));

        let sheet_xml = xlsx_entry_text(&path, "xl/worksheets/sheet1.xml");
        assert!(sheet_xml.contains("<pane ySplit=\"1\" topLeftCell=\"A2\""));
        assert!(sheet_xml.contains("<autoFilter ref=\"A1:P5\""));
        assert!(sheet_xml.contains("<c r=\"C2\" s=\""));
        assert!(sheet_xml.contains("<c r=\"E2\" s=\""));
        assert!(sheet_xml.contains("<c r=\"N2\" s=\""));
        let styles_xml = xlsx_entry_text(&path, "xl/styles.xml");
        assert!(styles_xml.contains("<fgColor rgb=\"FF1F4E78\""));
        assert!(styles_xml.contains("<color rgb=\"FFFFFFFF\""));
        assert!(styles_xml.contains("formatCode=\"#,##0.00\""));

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn report_exports_keep_five_columns_and_sections() {
        let db_path = create_balance_test_db();
        let csv_path = temp_test_path("ledgera_report", "csv");
        let xlsx_path = temp_test_path("ledgera_report", "xlsx");
        let pdf_path = temp_test_path("ledgera_report", "pdf");
        let filters = ReportFilters {
            period_start: Some("2026-01-01".to_owned()),
            period_end: Some("2026-01-04".to_owned()),
            ..ReportFilters::default()
        };

        report_export_csv(&db_path, &filters, csv_path.to_str().unwrap()).unwrap();
        let mut reader = ::csv::ReaderBuilder::new()
            .has_headers(false)
            .from_path(&csv_path)
            .unwrap();
        let rows: Vec<::csv::StringRecord> = reader.records().map(Result::unwrap).collect();
        assert!(!rows.is_empty());
        assert!(rows.iter().all(|row| row.len() == 5));
        assert_eq!(rows[1].get(4), Some("Tags"));

        report_export_xlsx(&db_path, &filters, xlsx_path.to_str().unwrap()).unwrap();
        let mut workbook = open_workbook_auto(&xlsx_path).unwrap();
        assert_eq!(
            workbook.sheet_names(),
            vec!["Report", "By Tag", "Yearly Report"]
        );
        let report_range = workbook.worksheet_range("Report").unwrap();
        assert_eq!(
            report_range.get_value((1, 4)).map(xlsx_cell_to_string),
            Some("Tags".to_owned())
        );

        report_export_pdf(&db_path, &filters, pdf_path.to_str().unwrap()).unwrap();
        let pdf = fs::read(&pdf_path).unwrap();
        assert!(pdf.starts_with(b"%PDF-"));
        assert!(String::from_utf8_lossy(&pdf).contains("/Type0"));

        let grouped_csv_path = temp_test_path("ledgera_grouped_report", "csv");
        let grouped_xlsx_path = temp_test_path("ledgera_grouped_report", "xlsx");
        let grouped_pdf_path = temp_test_path("ledgera_grouped_report", "pdf");
        let grouped_filters = ReportFilters {
            group_by_category: true,
            ..filters.clone()
        };
        report_export_csv(
            &db_path,
            &grouped_filters,
            grouped_csv_path.to_str().unwrap(),
        )
        .unwrap();
        let mut grouped_reader = ::csv::ReaderBuilder::new()
            .has_headers(false)
            .from_path(&grouped_csv_path)
            .unwrap();
        let grouped_rows: Vec<::csv::StringRecord> =
            grouped_reader.records().map(Result::unwrap).collect();
        assert!(!grouped_rows.is_empty());
        assert!(grouped_rows.iter().all(|row| row.len() == 3));
        report_export_xlsx(
            &db_path,
            &grouped_filters,
            grouped_xlsx_path.to_str().unwrap(),
        )
        .unwrap();
        let grouped_workbook = open_workbook_auto(&grouped_xlsx_path).unwrap();
        assert_eq!(grouped_workbook.sheet_names(), vec!["Report"]);
        report_export_pdf(
            &db_path,
            &grouped_filters,
            grouped_pdf_path.to_str().unwrap(),
        )
        .unwrap();

        let _ = fs::remove_file(csv_path);
        let _ = fs::remove_file(xlsx_path);
        let _ = fs::remove_file(pdf_path);
        let _ = fs::remove_file(grouped_csv_path);
        let _ = fs::remove_file(grouped_xlsx_path);
        let _ = fs::remove_file(grouped_pdf_path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_preview_then_commit_replaces_operations_owned_rows() {
        let db_path = create_balance_test_db();
        create_standalone_record_with_tag_colors(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "1".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "1".to_owned(),
                category: "Existing".to_owned(),
                description: "Existing tag owner".to_owned(),
                tags: vec!["work".to_owned()],
            },
            &[TagColorAssignment {
                name: "work".to_owned(),
                color: TAG_PALETTE[10].to_owned(),
            }],
        )
        .unwrap();
        let path = std::env::temp_dir().join(format!(
            "ledgera_ops_import_{}.csv",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::write(
            &path,
            "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,tags,period,transfer_id,from_wallet_id,to_wallet_id\n\
             2026-02-01,income,1,Salary,100.00,KZT,1,100.00,Imported salary,\"work, main\",,,,,\n\
             2026-02-02,transfer,,Transfer,25.00,KZT,1,25.00,Imported transfer,,,7,1,2\n",
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(preview.imported, 2);
        assert!(preview.dry_run);
        assert_eq!(record_list_rows(&db_path).unwrap().len(), 6);

        let result = import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.imported, 2);
        assert!(!result.dry_run);
        let records = record_list_rows(&db_path).unwrap();
        assert!(
            !records
                .iter()
                .any(|record| record.record_type == "mandatory_expense")
        );
        assert!(records.iter().any(|record| {
            record.transfer_id.is_none()
                && record.record_type == "income"
                && record.category == "Salary"
                && record.tags == vec!["main".to_owned(), "work".to_owned()]
        }));
        let imported_tag_colors = tag_color_rows(&db_path).unwrap();
        assert_eq!(
            imported_tag_colors
                .iter()
                .find(|row| row.name == "work")
                .unwrap()
                .color,
            TAG_PALETTE[10]
        );
        let transfer_rows: Vec<_> = records
            .iter()
            .filter(|record| record.transfer_id.is_some())
            .collect();
        assert_eq!(transfer_rows.len(), 2);
        let transfers = transfer_list_rows(&db_path).unwrap();
        assert_eq!(transfers.len(), 1);
        assert_eq!(transfers[0].id, 1);
        assert!(
            transfer_rows
                .iter()
                .all(|record| record.transfer_id == Some(1))
        );

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_xlsx_preview_then_commit_replaces_operations_owned_rows() {
        let db_path = create_balance_test_db();
        let path = std::env::temp_dir().join(format!(
            "ledgera_ops_import_{}.xlsx",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        write_operation_xlsx_fixture(
            &path,
            &[
                vec![
                    "2026-02-01",
                    "income",
                    "1",
                    "Salary",
                    "100.00",
                    "KZT",
                    "1",
                    "100.00",
                    "Imported salary",
                    "work, main",
                    "",
                    "",
                    "",
                    "",
                ],
                vec![
                    "2026-02-02",
                    "transfer",
                    "",
                    "Transfer",
                    "25.00",
                    "KZT",
                    "1",
                    "25.00",
                    "Imported transfer",
                    "",
                    "",
                    "7",
                    "1",
                    "2",
                ],
            ],
        );

        let preview = preview_import_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(preview.imported, 2);
        assert!(preview.dry_run);
        assert_eq!(record_list_rows(&db_path).unwrap().len(), 5);

        let result = import_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(result.imported, 2);
        assert!(!result.dry_run);
        let records = record_list_rows(&db_path).unwrap();
        assert!(
            !records
                .iter()
                .any(|record| record.record_type == "mandatory_expense")
        );
        assert!(records.iter().any(|record| {
            record.transfer_id.is_none()
                && record.record_type == "income"
                && record.category == "Salary"
                && record.tags == vec!["main".to_owned(), "work".to_owned()]
        }));
        let transfer_rows: Vec<_> = records
            .iter()
            .filter(|record| record.transfer_id.is_some())
            .collect();
        assert_eq!(transfer_rows.len(), 2);
        assert!(
            transfer_rows
                .iter()
                .all(|record| record.transfer_id == Some(1))
        );

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_preserves_file_order_for_journal_sorting() {
        let db_path = create_balance_test_db();
        let path = std::env::temp_dir().join(format!(
            "ledgera_ops_import_order_{}.csv",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::write(
            &path,
            "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,tags,period,transfer_id,from_wallet_id,to_wallet_id\n\
             2026-02-01,income,1,Salary,100.00,KZT,1,100.00,Oldest,,,,,\n\
             2026-02-02,expense,1,Food,10.00,KZT,1,10.00,Same day first,,,,,\n\
             2026-02-02,expense,1,Food,20.00,KZT,1,20.00,Same day second,,,,,\n\
             2026-02-03,transfer,,Transfer,25.00,KZT,1,25.00,Newest transfer,,,9,1,2\n",
        )
        .unwrap();

        import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        let imported_rows: Vec<_> = record_list_rows(&db_path)
            .unwrap()
            .into_iter()
            .filter(|record| {
                record.description == "Oldest"
                    || record.description == "Same day first"
                    || record.description == "Same day second"
                    || record.description == "Newest transfer"
            })
            .collect();
        let oldest_id = imported_rows
            .iter()
            .find(|record| record.description == "Oldest")
            .unwrap()
            .id;
        let same_day_first_id = imported_rows
            .iter()
            .find(|record| record.description == "Same day first")
            .unwrap()
            .id;
        let same_day_second_id = imported_rows
            .iter()
            .find(|record| record.description == "Same day second")
            .unwrap()
            .id;
        assert!(oldest_id < same_day_first_id);
        assert!(same_day_first_id < same_day_second_id);

        let journal_rows =
            filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        let descriptions: Vec<_> = journal_rows
            .iter()
            .map(|record| record.description.as_str())
            .collect();
        let newest_transfer_position = descriptions
            .iter()
            .position(|description| *description == "Newest transfer")
            .unwrap();
        let same_day_second_position = descriptions
            .iter()
            .position(|description| *description == "Same day second")
            .unwrap();
        let same_day_first_position = descriptions
            .iter()
            .position(|description| *description == "Same day first")
            .unwrap();
        let oldest_position = descriptions
            .iter()
            .position(|description| *description == "Oldest")
            .unwrap();
        assert!(newest_transfer_position < same_day_second_position);
        assert!(same_day_second_position < same_day_first_position);
        assert!(same_day_first_position < oldest_position);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_xlsx_preserves_file_order_for_journal_sorting() {
        let db_path = create_balance_test_db();
        let path = std::env::temp_dir().join(format!(
            "ledgera_ops_import_order_{}.xlsx",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        write_operation_xlsx_fixture(
            &path,
            &[
                vec![
                    "2026-02-01",
                    "income",
                    "1",
                    "Salary",
                    "100.00",
                    "KZT",
                    "1",
                    "100.00",
                    "Oldest",
                    "",
                    "",
                    "",
                    "",
                    "",
                ],
                vec![
                    "2026-02-02",
                    "expense",
                    "1",
                    "Food",
                    "10.00",
                    "KZT",
                    "1",
                    "10.00",
                    "Same day first",
                    "",
                    "",
                    "",
                    "",
                    "",
                ],
                vec![
                    "2026-02-02",
                    "expense",
                    "1",
                    "Food",
                    "20.00",
                    "KZT",
                    "1",
                    "20.00",
                    "Same day second",
                    "",
                    "",
                    "",
                    "",
                    "",
                ],
                vec![
                    "2026-02-03",
                    "transfer",
                    "",
                    "Transfer",
                    "25.00",
                    "KZT",
                    "1",
                    "25.00",
                    "Newest transfer",
                    "",
                    "",
                    "9",
                    "1",
                    "2",
                ],
            ],
        );

        import_records_xlsx(&db_path, path.to_str().unwrap()).unwrap();

        let journal_rows =
            filtered_record_list_rows(&db_path, &RecordFilterPayload::default()).unwrap();
        let descriptions: Vec<_> = journal_rows
            .iter()
            .map(|record| record.description.as_str())
            .collect();
        let newest_transfer_position = descriptions
            .iter()
            .position(|description| *description == "Newest transfer")
            .unwrap();
        let same_day_second_position = descriptions
            .iter()
            .position(|description| *description == "Same day second")
            .unwrap();
        let same_day_first_position = descriptions
            .iter()
            .position(|description| *description == "Same day first")
            .unwrap();
        let oldest_position = descriptions
            .iter()
            .position(|description| *description == "Oldest")
            .unwrap();
        assert!(newest_transfer_position < same_day_second_position);
        assert!(same_day_second_position < same_day_first_position);
        assert!(same_day_first_position < oldest_position);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_skips_invalid_rows_without_mutating_on_preview() {
        let db_path = create_balance_test_db();
        let path = std::env::temp_dir().join(format!(
            "ledgera_ops_import_invalid_{}.csv",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::write(
            &path,
            "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,tags,period,transfer_id,from_wallet_id,to_wallet_id\n\
             2999-01-01,income,1,Future,10.00,KZT,1,10.00,,,,,,\n\
             2026-02-02,transfer,,Transfer,25.00,KZT,1,25.00,Bad transfer,,,1,1,1\n",
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 2);
        assert!(preview.errors.iter().any(|error| error.contains("future")));
        assert!(
            preview
                .errors
                .iter()
                .any(|error| error.contains("different"))
        );
        assert_eq!(record_list_rows(&db_path).unwrap().len(), 5);

        let _ = fs::remove_file(path);
        remove_test_db(&db_path);
    }

    #[test]
    fn import_records_csv_rejects_orphan_transfer_commission_marker() {
        let db_path = create_balance_test_db();
        let path = std::env::temp_dir().join(format!(
            "ledgera_ops_import_orphan_marker_{}.csv",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::write(
            &path,
            "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,tags,period,transfer_id,from_wallet_id,to_wallet_id\n\
             2026-02-01,expense,1,Commission,5.00,KZT,1,5.00,[transfer:99],,,,,\n",
        )
        .unwrap();

        let preview = preview_import_records_csv(&db_path, path.to_str().unwrap()).unwrap();

        assert_eq!(preview.imported, 0);
        assert_eq!(preview.skipped, 1);
        assert!(preview.errors.iter().any(|error| {
            error.contains(
                "transfer commission marker [transfer:99] requires an aggregate transfer row",
            )
        }));
        assert_eq!(record_list_rows(&db_path).unwrap().len(), 5);

        let result = import_records_csv(&db_path, path.to_str().unwrap()).unwrap();
        assert_eq!(result.imported, 0);
        assert_eq!(record_list_rows(&db_path).unwrap().len(), 5);

        let _ = fs::remove_file(path);
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

    #[test]
    fn tag_palette_assigns_first_free_color_and_allows_manual_reassignment() {
        let db_path = create_balance_test_db();
        assert_eq!(TAG_PALETTE.len(), 32);
        assert!(TAG_PALETTE.iter().all(|color| is_valid_tag_color(color)));

        let first = create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "expense".to_owned(),
                date: "2026-02-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "First".to_owned(),
                tags: vec!["alpha".to_owned()],
            },
        )
        .unwrap();
        create_standalone_record(
            &db_path,
            &StandaloneRecordCreatePayload {
                record_type: "expense".to_owned(),
                date: "2026-02-02".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "Second".to_owned(),
                tags: vec!["beta".to_owned()],
            },
        )
        .unwrap();
        let initial = tag_color_rows(&db_path).unwrap();
        let alpha_color = initial
            .iter()
            .find(|row| row.name == "alpha")
            .unwrap()
            .color
            .clone();
        let beta_color = initial
            .iter()
            .find(|row| row.name == "beta")
            .unwrap()
            .color
            .clone();
        assert!(!alpha_color.is_empty());
        assert_ne!(alpha_color, beta_color);

        update_standalone_record_with_tag_colors(
            &db_path,
            first.id,
            &StandaloneRecordUpdatePayload {
                record_type: "expense".to_owned(),
                date: "2026-02-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "First".to_owned(),
                tags: vec!["alpha".to_owned()],
            },
            &[TagColorAssignment {
                name: "alpha".to_owned(),
                color: TAG_PALETTE[10].to_owned(),
            }],
        )
        .unwrap();
        assert_eq!(
            tag_color_rows(&db_path)
                .unwrap()
                .into_iter()
                .find(|row| row.name == "alpha")
                .unwrap()
                .color,
            TAG_PALETTE[10]
        );
        remove_test_db(&db_path);
    }

    #[test]
    fn tag_palette_rejects_color_conflicts_and_invalid_values() {
        let db_path = create_balance_test_db();
        let payload = StandaloneRecordCreatePayload {
            record_type: "expense".to_owned(),
            date: "2026-02-01".to_owned(),
            wallet_id: 1,
            amount_original: "10".to_owned(),
            currency: "KZT".to_owned(),
            rate_at_operation: "1".to_owned(),
            amount_base: "10".to_owned(),
            category: "Food".to_owned(),
            description: "Tagged".to_owned(),
            tags: vec!["alpha".to_owned()],
        };
        create_standalone_record_with_tag_colors(
            &db_path,
            &payload,
            &[TagColorAssignment {
                name: "alpha".to_owned(),
                color: TAG_PALETTE[0].to_owned(),
            }],
        )
        .unwrap();
        let beta_payload = StandaloneRecordCreatePayload {
            tags: vec!["beta".to_owned()],
            ..payload.clone()
        };
        let conflict = create_standalone_record_with_tag_colors(
            &db_path,
            &beta_payload,
            &[TagColorAssignment {
                name: "beta".to_owned(),
                color: TAG_PALETTE[0].to_owned(),
            }],
        )
        .unwrap_err();
        assert!(conflict.contains("already assigned"));
        let invalid = create_standalone_record_with_tag_colors(
            &db_path,
            &payload,
            &[TagColorAssignment {
                name: "alpha".to_owned(),
                color: "#ffffff".to_owned(),
            }],
        )
        .unwrap_err();
        assert!(invalid.contains("Unsupported tag color"));
        remove_test_db(&db_path);
    }
}
