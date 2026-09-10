use crate::{
    StorageResult, minor_amount_expr, normalize_record_ids_in_tx, signed_minor_amount_expr,
    sqlite_err, storage_clear_read_connection_cache, with_cached_read_connection,
};
use ledgera_engine_core::{minor_to_money_value, normalize_currency_code, to_minor_units};
use rusqlite::{Connection, OptionalExtension, params, params_from_iter};

const FULL_PCT_MINOR: i64 = 10_000;

#[derive(Debug, Clone, PartialEq)]
pub struct DistributionValidationRow {
    pub level: String,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DistributionItemPayload {
    pub id: i64,
    pub name: String,
    pub group_name: String,
    pub sort_order: i64,
    pub pct: f64,
    pub pct_minor: i64,
    pub is_active: bool,
    pub amount_base: f64,
    pub amount_minor: i64,
    pub subitems: Vec<DistributionSubitemPayload>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DistributionSubitemPayload {
    pub id: i64,
    pub item_id: i64,
    pub name: String,
    pub sort_order: i64,
    pub pct: f64,
    pub pct_minor: i64,
    pub is_active: bool,
    pub amount_base: f64,
    pub amount_minor: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DistributionMonthlyPayload {
    pub month: String,
    pub net_income_base: f64,
    pub net_income_minor: i64,
    pub is_negative: bool,
    pub items: Vec<DistributionItemPayload>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FrozenDistributionPayload {
    pub month: String,
    pub column_order: Vec<String>,
    pub headings_by_column: Vec<(String, String)>,
    pub values_by_column: Vec<(String, String)>,
    pub is_negative: bool,
    pub auto_fixed: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BudgetPayload {
    pub id: i64,
    pub category: String,
    pub start_date: String,
    pub end_date: String,
    pub limit_base: f64,
    pub limit_base_minor: i64,
    pub include_mandatory: bool,
    pub scope_type: String,
    pub scope_value: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BudgetCreatePayload<'a> {
    pub category: &'a str,
    pub scope_type: &'a str,
    pub scope_value: &'a str,
    pub start_date: &'a str,
    pub end_date: &'a str,
    pub limit_base: f64,
    pub limit_base_minor: i64,
    pub include_mandatory: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BudgetResultPayload {
    pub budget: BudgetPayload,
    pub spent_base: f64,
    pub spent_minor: i64,
    pub remaining_base: f64,
    pub usage_pct: f64,
    pub time_pct: f64,
    pub status: String,
    pub pace_status: String,
    pub forecast_remaining_base: Option<f64>,
    pub forecast_delta_base: Option<f64>,
    pub forecast_days_left: Option<i64>,
    pub forecast_status_key: Option<String>,
    pub forecast_status_params: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DebtRecalculatePayload {
    pub remaining_amount_minor: i64,
    pub status: String,
    pub closed_at: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DebtPayload {
    pub id: i64,
    pub contact_name: String,
    pub kind: String,
    pub total_amount_minor: i64,
    pub remaining_amount_minor: i64,
    pub currency: String,
    pub interest_rate: f64,
    pub status: String,
    pub created_at: String,
    pub closed_at: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DebtPaymentPayload {
    pub id: i64,
    pub debt_id: i64,
    pub record_id: Option<i64>,
    pub operation_type: String,
    pub principal_paid_minor: i64,
    pub is_write_off: bool,
    pub payment_date: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DebtRecordPayload {
    pub record_type: String,
    pub date: String,
    pub wallet_id: i64,
    pub amount_original: f64,
    pub amount_original_minor: i64,
    pub currency: String,
    pub rate_at_operation: f64,
    pub rate_at_operation_text: String,
    pub amount_base: f64,
    pub amount_base_minor: i64,
    pub category: String,
    pub description: String,
    pub period: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DebtCreatePayload {
    pub kind: String,
    pub contact_name: String,
    pub wallet_id: i64,
    pub amount: String,
    pub currency: String,
    pub created_at: String,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DebtPaymentRequestPayload {
    pub debt_id: i64,
    pub wallet_id: Option<i64>,
    pub amount: String,
    pub payment_date: String,
    pub description: String,
}

fn apply_pct(amount_minor: i64, pct_minor: i64) -> i64 {
    let numerator = i128::from(amount_minor) * i128::from(pct_minor);
    let sign = if numerator < 0 { -1 } else { 1 };
    let rounded_abs =
        (numerator.abs() + i128::from(FULL_PCT_MINOR / 2)) / i128::from(FULL_PCT_MINOR);
    (rounded_abs * i128::from(sign)) as i64
}

fn open_write_connection(db_path: &str) -> StorageResult<Connection> {
    Connection::open(db_path).map_err(sqlite_err)
}

fn map_distribution_integrity_error(
    err: rusqlite::Error,
    name: &str,
    item_id: Option<i64>,
) -> String {
    let message = err.to_string();
    if message.contains("distribution_items.name") {
        return format!("Distribution item '{name}' already exists");
    }
    if message.contains("distribution_subitems.item_id, distribution_subitems.name") {
        if let Some(id) = item_id {
            return format!("Distribution subitem '{name}' already exists for item #{id}");
        }
        return format!("Distribution subitem '{name}' already exists");
    }
    format!("sqlite error: {err}")
}

fn distribution_item_from_conn(
    conn: &Connection,
    item_id: i64,
) -> StorageResult<DistributionItemPayload> {
    conn.query_row(
        "SELECT id, name, group_name, sort_order, pct, pct_minor, is_active
         FROM distribution_items
         WHERE id = ?",
        [item_id],
        |row| {
            Ok(DistributionItemPayload {
                id: row.get(0)?,
                name: row.get(1)?,
                group_name: row.get(2)?,
                sort_order: row.get(3)?,
                pct: row.get(4)?,
                pct_minor: row.get(5)?,
                is_active: row.get(6)?,
                amount_base: 0.0,
                amount_minor: 0,
                subitems: Vec::new(),
            })
        },
    )
    .optional()
    .map_err(sqlite_err)?
    .ok_or_else(|| format!("Distribution item not found: {item_id}"))
}

fn distribution_subitem_from_conn(
    conn: &Connection,
    subitem_id: i64,
) -> StorageResult<DistributionSubitemPayload> {
    conn.query_row(
        "SELECT id, item_id, name, sort_order, pct, pct_minor, is_active
         FROM distribution_subitems
         WHERE id = ?",
        [subitem_id],
        |row| {
            Ok(DistributionSubitemPayload {
                id: row.get(0)?,
                item_id: row.get(1)?,
                name: row.get(2)?,
                sort_order: row.get(3)?,
                pct: row.get(4)?,
                pct_minor: row.get(5)?,
                is_active: row.get(6)?,
                amount_base: 0.0,
                amount_minor: 0,
            })
        },
    )
    .optional()
    .map_err(sqlite_err)?
    .ok_or_else(|| format!("Distribution subitem not found: {subitem_id}"))
}

fn distribution_item_exists(conn: &Connection, item_id: i64) -> StorageResult<bool> {
    conn.query_row(
        "SELECT 1 FROM distribution_items WHERE id = ?",
        [item_id],
        |_| Ok(()),
    )
    .optional()
    .map_err(sqlite_err)
    .map(|row| row.is_some())
}

fn budget_from_conn(conn: &Connection, budget_id: i64) -> StorageResult<BudgetPayload> {
    conn.query_row(
        "SELECT id, category, start_date, end_date,
                limit_base, limit_base_minor, include_mandatory, scope_type, scope_value
         FROM budgets
         WHERE id = ?",
        [budget_id],
        |row| {
            Ok(BudgetPayload {
                id: row.get(0)?,
                category: row.get(1)?,
                start_date: row.get(2)?,
                end_date: row.get(3)?,
                limit_base: row.get(4)?,
                limit_base_minor: row.get(5)?,
                include_mandatory: row.get(6)?,
                scope_type: row.get(7)?,
                scope_value: row.get(8)?,
            })
        },
    )
    .optional()
    .map_err(sqlite_err)?
    .ok_or_else(|| format!("Budget not found: {budget_id}"))
}

fn budget_exists(conn: &Connection, budget_id: i64) -> StorageResult<bool> {
    conn.query_row(
        "SELECT 1 FROM budgets WHERE id = ?",
        [budget_id],
        |_| Ok(()),
    )
    .optional()
    .map_err(sqlite_err)
    .map(|row| row.is_some())
}

fn budget_date_parts(value: &str) -> StorageResult<(i32, i32, i32)> {
    let parts: Vec<_> = value.split('-').collect();
    if parts.len() != 3 {
        return Err(format!("Invalid budget date: {value}"));
    }
    let year = parts[0]
        .parse::<i32>()
        .map_err(|_| format!("Invalid budget date: {value}"))?;
    let month = parts[1]
        .parse::<i32>()
        .map_err(|_| format!("Invalid budget date: {value}"))?;
    let day = parts[2]
        .parse::<i32>()
        .map_err(|_| format!("Invalid budget date: {value}"))?;
    if parts[0].len() != 4
        || parts[1].len() != 2
        || parts[2].len() != 2
        || !(1..=12).contains(&month)
    {
        return Err(format!("Invalid budget date: {value}"));
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    if !(1..=days[(month - 1) as usize]).contains(&day) {
        return Err(format!("Invalid budget date: {value}"));
    }
    Ok((year, month, day))
}

fn budget_day_number(year: i32, month: i32, day: i32) -> i64 {
    let y = year - i32::from(month <= 2);
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let year_of_era = y - era * 400;
    let month_index = month + if month > 2 { -3 } else { 9 };
    let day_of_year = (153 * month_index + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    i64::from(era * 146097 + day_of_era)
}

fn normalize_budget_fields(
    category: &str,
    scope_type: &str,
    scope_value: &str,
    limit_base: f64,
    limit_base_minor: i64,
) -> StorageResult<(String, String, String)> {
    let scope_type = scope_type.trim().to_ascii_lowercase();
    if scope_type != "category" && scope_type != "tag" {
        return Err("scope_type must be 'category' or 'tag'".to_owned());
    }
    let normalized_category = category.trim().to_owned();
    let normalized_scope_value = scope_value.trim().to_owned();
    if normalized_category.is_empty() || normalized_scope_value.is_empty() {
        return Err("scope_value is required".to_owned());
    }
    if !limit_base.is_finite() || limit_base_minor <= 0 {
        return Err("Budget limit must be positive".to_owned());
    }
    Ok((normalized_category, scope_type, normalized_scope_value))
}

fn validate_budget_payload(
    category: &str,
    scope_type: &str,
    scope_value: &str,
    start_date: &str,
    end_date: &str,
    limit_base: f64,
    limit_base_minor: i64,
) -> StorageResult<()> {
    normalize_budget_fields(
        category,
        scope_type,
        scope_value,
        limit_base,
        limit_base_minor,
    )?;
    budget_date_parts(start_date)?;
    budget_date_parts(end_date)?;
    if start_date > end_date {
        return Err("start_date must be <= end_date".to_owned());
    }
    Ok(())
}

fn budget_status(start_date: &str, end_date: &str, today: &str) -> StorageResult<String> {
    let start = budget_date_parts(start_date)?;
    let end = budget_date_parts(end_date)?;
    let today = budget_date_parts(today)?;
    Ok(if today < start {
        "future"
    } else if today > end {
        "expired"
    } else {
        "active"
    }
    .to_owned())
}

fn budget_forecast(
    budget: &BudgetPayload,
    spent_minor: i64,
    today: &str,
) -> StorageResult<(
    Option<f64>,
    Option<f64>,
    Option<i64>,
    Option<String>,
    Option<String>,
)> {
    let start = budget_date_parts(&budget.start_date)?;
    let end = budget_date_parts(&budget.end_date)?;
    let today = budget_date_parts(today)?;
    let total_days =
        (budget_day_number(end.0, end.1, end.2) - budget_day_number(start.0, start.1, start.2) + 1)
            .max(1);
    let elapsed_days = if today < start {
        0
    } else if today > end {
        total_days
    } else {
        budget_day_number(today.0, today.1, today.2) - budget_day_number(start.0, start.1, start.2)
            + 1
    };
    if elapsed_days < 3 && spent_minor < (budget.limit_base_minor / 10).max(1) {
        return Ok((None, None, None, None, None));
    }
    let daily_burn = spent_minor as f64 / elapsed_days.max(1) as f64;
    let projected_spent = (daily_burn * total_days as f64).round() as i64;
    let projected_remaining = budget.limit_base_minor - projected_spent;
    let current_remaining = budget.limit_base_minor - spent_minor;
    let days_left = if daily_burn > 0.0 && current_remaining > 0 {
        Some((current_remaining as f64 / daily_burn).max(0.0) as i64)
    } else {
        None
    };
    let remaining = minor_to_money_value(projected_remaining);
    let (key, params) = if projected_remaining < 0 && days_left.is_some() {
        (
            "budget.forecast.overspend_in_days",
            Some(format!("{{\"days\":{}}}", days_left.unwrap())),
        )
    } else if projected_remaining < 0 {
        ("budget.forecast.overspend", None)
    } else {
        (
            "budget.forecast.remaining",
            Some(format!("{{\"amount_base\":{remaining:.2}}}")),
        )
    };
    Ok((
        Some(remaining),
        Some(remaining),
        days_left,
        Some(key.to_owned()),
        params,
    ))
}

fn debt_from_conn(conn: &Connection, debt_id: i64) -> StorageResult<DebtPayload> {
    conn.query_row(
        "SELECT id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                currency, interest_rate, status, created_at, closed_at
         FROM debts
         WHERE id = ?",
        [debt_id],
        |row| {
            Ok(DebtPayload {
                id: row.get(0)?,
                contact_name: row.get(1)?,
                kind: row.get(2)?,
                total_amount_minor: row.get(3)?,
                remaining_amount_minor: row.get(4)?,
                currency: row.get(5)?,
                interest_rate: row.get(6)?,
                status: row.get(7)?,
                created_at: row.get(8)?,
                closed_at: row.get(9)?,
            })
        },
    )
    .optional()
    .map_err(sqlite_err)?
    .ok_or_else(|| format!("Debt not found: {debt_id}"))
}

fn debt_payment_from_conn(conn: &Connection, payment_id: i64) -> StorageResult<DebtPaymentPayload> {
    conn.query_row(
        "SELECT id, debt_id, record_id, operation_type, principal_paid_minor,
                is_write_off, payment_date
         FROM debt_payments
         WHERE id = ?",
        [payment_id],
        |row| {
            Ok(DebtPaymentPayload {
                id: row.get(0)?,
                debt_id: row.get(1)?,
                record_id: row.get(2)?,
                operation_type: row.get(3)?,
                principal_paid_minor: row.get(4)?,
                is_write_off: row.get(5)?,
                payment_date: row.get(6)?,
            })
        },
    )
    .optional()
    .map_err(sqlite_err)?
    .ok_or_else(|| format!("Debt payment not found: {payment_id}"))
}

fn active_debt_wallet_in_tx(tx: &rusqlite::Transaction<'_>, wallet_id: i64) -> StorageResult<bool> {
    let wallet = tx
        .query_row(
            "SELECT allow_negative, is_active FROM wallets WHERE id = ?1",
            [wallet_id],
            |row| Ok((row.get::<_, i64>(0)? != 0, row.get::<_, i64>(1)? != 0)),
        )
        .optional()
        .map_err(sqlite_err)?;
    let Some((allow_negative, is_active)) = wallet else {
        return Err(format!("Wallet not found: {wallet_id}"));
    };
    if !is_active {
        return Err("Cannot create obligation for inactive wallet".to_owned());
    }
    Ok(allow_negative)
}

fn wallet_balance_minor_for_debt_in_tx(
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

fn base_currency_code_for_debt_in_tx(tx: &rusqlite::Transaction<'_>) -> StorageResult<String> {
    let has_schema_meta = tx
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'",
            [],
            |_| Ok(()),
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
    let normalized = value.trim().to_uppercase();
    if normalized.is_empty() {
        Ok("KZT".to_owned())
    } else {
        Ok(normalized)
    }
}

fn validate_debt_date(value: &str) -> StorageResult<()> {
    let bytes = value.as_bytes();
    if bytes.len() != 10 || bytes[4] != b'-' || bytes[7] != b'-' {
        return Err("Date must use YYYY-MM-DD format".to_owned());
    }
    let year = parse_debt_date_part(value, 0, 4, "year")?;
    let month = parse_debt_date_part(value, 5, 7, "month")?;
    let day = parse_debt_date_part(value, 8, 10, "day")?;
    if !(1..=12).contains(&month) {
        return Err("Date month must be between 01 and 12".to_owned());
    }
    let max_day = debt_days_in_month(year, month);
    if day < 1 || day > max_day {
        return Err(format!("Date day must be between 01 and {max_day:02}"));
    }
    if (year, month, day) > crate::current_local_date() {
        return Err("Date cannot be in the future".to_owned());
    }
    Ok(())
}

fn parse_debt_date_part(value: &str, start: usize, end: usize, name: &str) -> StorageResult<i32> {
    let part = &value[start..end];
    if !part.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(format!("Date {name} must contain digits only"));
    }
    part.parse::<i32>()
        .map_err(|_| format!("Date {name} is invalid"))
}

fn debt_days_in_month(year: i32, month: i32) -> i32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if debt_is_leap_year(year) => 29,
        2 => 28,
        _ => 0,
    }
}

fn debt_is_leap_year(year: i32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn insert_debt_row(conn: &Connection, debt: &DebtPayload, with_id: bool) -> StorageResult<i64> {
    if with_id {
        conn.execute(
            "INSERT INTO debts (
                id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                currency, interest_rate, status, created_at, closed_at
             )
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params![
                debt.id,
                debt.contact_name,
                debt.kind,
                debt.total_amount_minor,
                debt.remaining_amount_minor,
                debt.currency,
                debt.interest_rate,
                debt.status,
                debt.created_at,
                debt.closed_at
            ],
        )
        .map_err(sqlite_err)?;
        Ok(debt.id)
    } else {
        conn.execute(
            "INSERT INTO debts (
                contact_name, kind, total_amount_minor, remaining_amount_minor,
                currency, interest_rate, status, created_at, closed_at
             )
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params![
                debt.contact_name,
                debt.kind,
                debt.total_amount_minor,
                debt.remaining_amount_minor,
                debt.currency,
                debt.interest_rate,
                debt.status,
                debt.created_at,
                debt.closed_at
            ],
        )
        .map_err(sqlite_err)?;
        Ok(conn.last_insert_rowid())
    }
}

fn insert_debt_record_row(
    conn: &Connection,
    record: &DebtRecordPayload,
    related_debt_id: i64,
) -> StorageResult<i64> {
    conn.execute(
        "INSERT INTO records (
            type, date, wallet_id, transfer_id, related_debt_id,
            amount_original, amount_original_minor, currency,
            rate_at_operation, rate_at_operation_text,
            amount_base, amount_base_minor, category, description, period
         )
         VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        params![
            record.record_type,
            record.date,
            record.wallet_id,
            related_debt_id,
            record.amount_original,
            record.amount_original_minor,
            record.currency,
            record.rate_at_operation,
            record.rate_at_operation_text,
            record.amount_base,
            record.amount_base_minor,
            record.category,
            record.description,
            record.period
        ],
    )
    .map_err(sqlite_err)?;
    Ok(conn.last_insert_rowid())
}

fn insert_debt_payment_row(
    conn: &Connection,
    payment: &DebtPaymentPayload,
    debt_id: i64,
    record_id: Option<i64>,
    with_id: bool,
) -> StorageResult<i64> {
    if with_id {
        conn.execute(
            "INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
             )
             VALUES (?, ?, ?, ?, ?, ?, ?)",
            params![
                payment.id,
                debt_id,
                record_id,
                payment.operation_type,
                payment.principal_paid_minor,
                payment.is_write_off,
                payment.payment_date
            ],
        )
        .map_err(sqlite_err)?;
        Ok(payment.id)
    } else {
        conn.execute(
            "INSERT INTO debt_payments (
                debt_id, record_id, operation_type,
                principal_paid_minor, is_write_off, payment_date
             )
             VALUES (?, ?, ?, ?, ?, ?)",
            params![
                debt_id,
                record_id,
                payment.operation_type,
                payment.principal_paid_minor,
                payment.is_write_off,
                payment.payment_date
            ],
        )
        .map_err(sqlite_err)?;
        Ok(conn.last_insert_rowid())
    }
}

pub fn distribution_net_income_for_period(
    db_path: &str,
    start_date: &str,
    end_date: &str,
) -> StorageResult<(f64, i64)> {
    with_cached_read_connection(db_path, |conn| {
        let expr = signed_minor_amount_expr("amount_base", "type");
        let net_minor = conn
            .query_row(
                &format!(
                    "SELECT COALESCE(SUM({expr}), 0)
                     FROM records
                     WHERE transfer_id IS NULL
                       AND date >= ?
                       AND date <= ?"
                ),
                (start_date, end_date),
                |row| row.get::<_, i64>(0),
            )
            .map_err(sqlite_err)?;
        Ok((minor_to_money_value(net_minor), net_minor))
    })
}

pub fn distribution_available_months(db_path: &str) -> StorageResult<Vec<String>> {
    with_cached_read_connection(db_path, |conn| {
        let mut stmt = conn
            .prepare(
                "SELECT DISTINCT substr(date, 1, 7) AS month
                 FROM records
                 WHERE transfer_id IS NULL
                 ORDER BY month ASC",
            )
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| row.get::<_, String>(0))
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })
}

pub fn distribution_history_months(
    db_path: &str,
    start_month: &str,
    end_month: &str,
) -> StorageResult<Vec<String>> {
    with_cached_read_connection(db_path, |conn| {
        let mut stmt = conn
            .prepare(
                "SELECT DISTINCT substr(date, 1, 7) AS month
                 FROM records
                 WHERE transfer_id IS NULL
                   AND substr(date, 1, 7) >= ?
                   AND substr(date, 1, 7) <= ?
                 ORDER BY month ASC",
            )
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map((start_month, end_month), |row| row.get::<_, String>(0))
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })
}

pub fn distribution_validate_structure(
    db_path: &str,
) -> StorageResult<Vec<DistributionValidationRow>> {
    with_cached_read_connection(db_path, |conn| {
        let mut errors = Vec::new();
        let total_pct_minor = conn
            .query_row(
                "SELECT COALESCE(SUM(pct_minor), 0)
                 FROM distribution_items
                 WHERE is_active = 1",
                [],
                |row| row.get::<_, i64>(0),
            )
            .map_err(sqlite_err)?;
        if total_pct_minor != FULL_PCT_MINOR {
            errors.push(DistributionValidationRow {
                level: "error".to_owned(),
                message: format!(
                    "Sum of top-level item percentages is {:.2}% (must be 100.00%)",
                    minor_to_money_value(total_pct_minor)
                ),
            });
        }

        let mut stmt = conn
            .prepare(
                "SELECT id, name
                 FROM distribution_items
                 WHERE is_active = 1
                 ORDER BY sort_order ASC, name COLLATE NOCASE ASC, id ASC",
            )
            .map_err(sqlite_err)?;
        let items = stmt
            .query_map([], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })
            .map_err(sqlite_err)?;
        for item in items {
            let (item_id, item_name) = item.map_err(sqlite_err)?;
            let (sub_total_minor, sub_count) = conn
                .query_row(
                    "SELECT COALESCE(SUM(pct_minor), 0), COUNT(*)
                     FROM distribution_subitems
                     WHERE item_id = ? AND is_active = 1",
                    [item_id],
                    |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?)),
                )
                .map_err(sqlite_err)?;
            if sub_count > 0 && sub_total_minor != FULL_PCT_MINOR {
                errors.push(DistributionValidationRow {
                    level: "error".to_owned(),
                    message: format!(
                        "Sum of subitem percentages for '{}' is {:.2}% (must be 100.00%)",
                        item_name,
                        minor_to_money_value(sub_total_minor)
                    ),
                });
            }
        }
        Ok(errors)
    })
}

pub fn distribution_monthly_payload(
    db_path: &str,
    month: &str,
    start_date: &str,
    end_date: &str,
) -> StorageResult<DistributionMonthlyPayload> {
    let (net_income_base, net_income_minor) =
        distribution_net_income_for_period(db_path, start_date, end_date)?;
    with_cached_read_connection(db_path, |conn| {
        let mut item_stmt = conn
            .prepare(
                "SELECT id, name, group_name, sort_order, pct, pct_minor, is_active
                 FROM distribution_items
                 WHERE is_active = 1
                 ORDER BY sort_order ASC, name COLLATE NOCASE ASC, id ASC",
            )
            .map_err(sqlite_err)?;
        let item_rows = item_stmt
            .query_map([], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, i64>(3)?,
                    row.get::<_, f64>(4)?,
                    row.get::<_, i64>(5)?,
                    row.get::<_, bool>(6)?,
                ))
            })
            .map_err(sqlite_err)?;
        let mut items = Vec::new();
        for item_row in item_rows {
            let (id, name, group_name, sort_order, pct, pct_minor, is_active) =
                item_row.map_err(sqlite_err)?;
            let item_minor = apply_pct(net_income_minor, pct_minor);
            let mut sub_stmt = conn
                .prepare(
                    "SELECT id, item_id, name, sort_order, pct, pct_minor, is_active
                     FROM distribution_subitems
                     WHERE item_id = ? AND is_active = 1
                     ORDER BY sort_order ASC, name COLLATE NOCASE ASC, id ASC",
                )
                .map_err(sqlite_err)?;
            let sub_rows = sub_stmt
                .query_map([id], |row| {
                    Ok(DistributionSubitemPayload {
                        id: row.get(0)?,
                        item_id: row.get(1)?,
                        name: row.get(2)?,
                        sort_order: row.get(3)?,
                        pct: row.get(4)?,
                        pct_minor: row.get(5)?,
                        is_active: row.get(6)?,
                        amount_base: 0.0,
                        amount_minor: 0,
                    })
                })
                .map_err(sqlite_err)?;
            let mut subitems = Vec::new();
            for sub_row in sub_rows {
                let mut subitem = sub_row.map_err(sqlite_err)?;
                subitem.amount_minor = apply_pct(item_minor, subitem.pct_minor);
                subitem.amount_base = minor_to_money_value(subitem.amount_minor);
                subitems.push(subitem);
            }
            items.push(DistributionItemPayload {
                id,
                name,
                group_name,
                sort_order,
                pct,
                pct_minor,
                is_active,
                amount_base: minor_to_money_value(item_minor),
                amount_minor: item_minor,
                subitems,
            });
        }
        Ok(DistributionMonthlyPayload {
            month: month.to_owned(),
            net_income_base,
            net_income_minor,
            is_negative: net_income_minor < 0,
            items,
        })
    })
}

pub fn distribution_item_rows(
    db_path: &str,
    active_only: bool,
) -> StorageResult<Vec<DistributionItemPayload>> {
    with_cached_read_connection(db_path, |conn| {
        let where_clause = if active_only {
            "WHERE is_active = 1"
        } else {
            ""
        };
        let mut stmt = conn
            .prepare(&format!(
                "SELECT id, name, group_name, sort_order, pct, pct_minor, is_active
                 FROM distribution_items
                 {where_clause}
                 ORDER BY sort_order ASC, name COLLATE NOCASE ASC, id ASC"
            ))
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| {
                Ok(DistributionItemPayload {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    group_name: row.get(2)?,
                    sort_order: row.get(3)?,
                    pct: row.get(4)?,
                    pct_minor: row.get(5)?,
                    is_active: row.get(6)?,
                    amount_base: 0.0,
                    amount_minor: 0,
                    subitems: Vec::new(),
                })
            })
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })
}

pub fn distribution_subitem_rows(
    db_path: &str,
    item_id: i64,
    active_only: bool,
) -> StorageResult<Vec<DistributionSubitemPayload>> {
    with_cached_read_connection(db_path, |conn| {
        if !distribution_item_exists(conn, item_id)? {
            return Err(format!("Distribution item not found: {item_id}"));
        }
        let active_clause = if active_only { "AND is_active = 1" } else { "" };
        let mut stmt = conn
            .prepare(&format!(
                "SELECT id, item_id, name, sort_order, pct, pct_minor, is_active
                 FROM distribution_subitems
                 WHERE item_id = ? {active_clause}
                 ORDER BY sort_order ASC, name COLLATE NOCASE ASC, id ASC"
            ))
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map([item_id], |row| {
                Ok(DistributionSubitemPayload {
                    id: row.get(0)?,
                    item_id: row.get(1)?,
                    name: row.get(2)?,
                    sort_order: row.get(3)?,
                    pct: row.get(4)?,
                    pct_minor: row.get(5)?,
                    is_active: row.get(6)?,
                    amount_base: 0.0,
                    amount_minor: 0,
                })
            })
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })
}

pub fn distribution_create_item(
    db_path: &str,
    name: &str,
    group_name: &str,
    sort_order: i64,
    pct: f64,
    pct_minor: i64,
) -> StorageResult<DistributionItemPayload> {
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "INSERT INTO distribution_items (name, group_name, sort_order, pct, pct_minor)
         VALUES (?, ?, ?, ?, ?)",
        params![name, group_name, sort_order, pct, pct_minor],
    )
    .map_err(|err| map_distribution_integrity_error(err, name, None))?;
    let item_id = tx.last_insert_rowid();
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    distribution_item_from_conn(&conn, item_id)
}

pub fn distribution_update_item_pct(
    db_path: &str,
    item_id: i64,
    pct: f64,
    pct_minor: i64,
) -> StorageResult<DistributionItemPayload> {
    let mut conn = open_write_connection(db_path)?;
    if !distribution_item_exists(&conn, item_id)? {
        return Err(format!("Distribution item not found: {item_id}"));
    }
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "UPDATE distribution_items SET pct = ?, pct_minor = ? WHERE id = ?",
        params![pct, pct_minor, item_id],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    distribution_item_from_conn(&conn, item_id)
}

pub fn distribution_update_item_name(
    db_path: &str,
    item_id: i64,
    name: &str,
) -> StorageResult<DistributionItemPayload> {
    let mut conn = open_write_connection(db_path)?;
    if !distribution_item_exists(&conn, item_id)? {
        return Err(format!("Distribution item not found: {item_id}"));
    }
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "UPDATE distribution_items SET name = ? WHERE id = ?",
        params![name, item_id],
    )
    .map_err(|err| map_distribution_integrity_error(err, name, None))?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    distribution_item_from_conn(&conn, item_id)
}

pub fn distribution_update_item_order(
    db_path: &str,
    item_id: i64,
    sort_order: i64,
) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    if !distribution_item_exists(&conn, item_id)? {
        return Err(format!("Distribution item not found: {item_id}"));
    }
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "UPDATE distribution_items SET sort_order = ? WHERE id = ?",
        params![sort_order, item_id],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn distribution_delete_item(db_path: &str, item_id: i64) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    if !distribution_item_exists(&conn, item_id)? {
        return Err(format!("Distribution item not found: {item_id}"));
    }
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute("DELETE FROM distribution_items WHERE id = ?", [item_id])
        .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn distribution_create_subitem(
    db_path: &str,
    item_id: i64,
    name: &str,
    sort_order: i64,
    pct: f64,
    pct_minor: i64,
) -> StorageResult<DistributionSubitemPayload> {
    let mut conn = open_write_connection(db_path)?;
    if !distribution_item_exists(&conn, item_id)? {
        return Err(format!("Distribution item not found: {item_id}"));
    }
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "INSERT INTO distribution_subitems (item_id, name, sort_order, pct, pct_minor)
         VALUES (?, ?, ?, ?, ?)",
        params![item_id, name, sort_order, pct, pct_minor],
    )
    .map_err(|err| map_distribution_integrity_error(err, name, Some(item_id)))?;
    let subitem_id = tx.last_insert_rowid();
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    distribution_subitem_from_conn(&conn, subitem_id)
}

pub fn distribution_update_subitem_pct(
    db_path: &str,
    subitem_id: i64,
    pct: f64,
    pct_minor: i64,
) -> StorageResult<DistributionSubitemPayload> {
    let mut conn = open_write_connection(db_path)?;
    distribution_subitem_from_conn(&conn, subitem_id)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "UPDATE distribution_subitems SET pct = ?, pct_minor = ? WHERE id = ?",
        params![pct, pct_minor, subitem_id],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    distribution_subitem_from_conn(&conn, subitem_id)
}

pub fn distribution_update_subitem_name(
    db_path: &str,
    subitem_id: i64,
    name: &str,
) -> StorageResult<DistributionSubitemPayload> {
    let mut conn = open_write_connection(db_path)?;
    let existing = distribution_subitem_from_conn(&conn, subitem_id)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "UPDATE distribution_subitems SET name = ? WHERE id = ?",
        params![name, subitem_id],
    )
    .map_err(|err| map_distribution_integrity_error(err, name, Some(existing.item_id)))?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    distribution_subitem_from_conn(&conn, subitem_id)
}

pub fn distribution_update_subitem_order(
    db_path: &str,
    subitem_id: i64,
    sort_order: i64,
) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    distribution_subitem_from_conn(&conn, subitem_id)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "UPDATE distribution_subitems SET sort_order = ? WHERE id = ?",
        params![sort_order, subitem_id],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn distribution_delete_subitem(db_path: &str, subitem_id: i64) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    distribution_subitem_from_conn(&conn, subitem_id)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "DELETE FROM distribution_subitems WHERE id = ?",
        [subitem_id],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn distribution_replace_structure(
    db_path: &str,
    items: &[DistributionItemPayload],
    subitems: &[DistributionSubitemPayload],
) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute("DELETE FROM distribution_subitems", [])
        .map_err(sqlite_err)?;
    tx.execute("DELETE FROM distribution_items", [])
        .map_err(sqlite_err)?;

    let mut sorted_items = items.to_vec();
    sorted_items.sort_by(|left, right| {
        left.sort_order
            .cmp(&right.sort_order)
            .then_with(|| left.name.to_lowercase().cmp(&right.name.to_lowercase()))
            .then_with(|| left.id.cmp(&right.id))
    });
    for item in &sorted_items {
        tx.execute(
            "INSERT INTO distribution_items (
                id, name, group_name, sort_order, pct, pct_minor, is_active
             )
             VALUES (?, ?, ?, ?, ?, ?, ?)",
            params![
                item.id,
                item.name,
                item.group_name,
                item.sort_order,
                item.pct,
                item.pct_minor,
                item.is_active
            ],
        )
        .map_err(|err| map_distribution_integrity_error(err, &item.name, None))?;
    }

    let mut sorted_subitems = subitems.to_vec();
    sorted_subitems.sort_by(|left, right| {
        left.sort_order
            .cmp(&right.sort_order)
            .then_with(|| left.name.to_lowercase().cmp(&right.name.to_lowercase()))
            .then_with(|| left.id.cmp(&right.id))
    });
    for subitem in &sorted_subitems {
        tx.execute(
            "INSERT INTO distribution_subitems (
                id, item_id, name, sort_order, pct, pct_minor, is_active
             )
             VALUES (?, ?, ?, ?, ?, ?, ?)",
            params![
                subitem.id,
                subitem.item_id,
                subitem.name,
                subitem.sort_order,
                subitem.pct,
                subitem.pct_minor,
                subitem.is_active
            ],
        )
        .map_err(|err| {
            map_distribution_integrity_error(err, &subitem.name, Some(subitem.item_id))
        })?;
    }

    tx.execute(
        "DELETE FROM sqlite_sequence WHERE name IN ('distribution_items', 'distribution_subitems')",
        [],
    )
    .map_err(sqlite_err)?;
    if let Some(max_id) = items.iter().map(|item| item.id).max() {
        tx.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES('distribution_items', ?)",
            [max_id],
        )
        .map_err(sqlite_err)?;
    }
    if let Some(max_id) = subitems.iter().map(|subitem| subitem.id).max() {
        tx.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES('distribution_subitems', ?)",
            [max_id],
        )
        .map_err(sqlite_err)?;
    }
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn distribution_is_month_fixed(db_path: &str, month: &str) -> StorageResult<bool> {
    with_cached_read_connection(db_path, |conn| {
        conn.query_row(
            "SELECT 1 FROM distribution_snapshots WHERE month = ?",
            [month],
            |_| Ok(()),
        )
        .optional()
        .map_err(sqlite_err)
        .map(|row| row.is_some())
    })
}

pub fn distribution_is_month_auto_fixed(db_path: &str, month: &str) -> StorageResult<bool> {
    with_cached_read_connection(db_path, |conn| {
        Ok(conn
            .query_row(
                "SELECT auto_fixed FROM distribution_snapshots WHERE month = ?",
                [month],
                |row| row.get::<_, bool>(0),
            )
            .optional()
            .map_err(sqlite_err)?
            .unwrap_or(false))
    })
}

pub fn distribution_write_frozen_row(
    db_path: &str,
    row: &FrozenDistributionPayload,
) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "INSERT OR REPLACE INTO distribution_snapshots (month, is_negative, auto_fixed)
         VALUES (?, ?, ?)",
        params![row.month, row.is_negative, row.auto_fixed],
    )
    .map_err(sqlite_err)?;
    tx.execute(
        "DELETE FROM distribution_snapshot_values WHERE snapshot_month = ?",
        [row.month.as_str()],
    )
    .map_err(sqlite_err)?;
    for (index, column_id) in row.column_order.iter().enumerate() {
        let label = row
            .headings_by_column
            .iter()
            .find(|(key, _)| key == column_id)
            .map(|(_, value)| value.as_str())
            .unwrap_or(column_id);
        let value = row
            .values_by_column
            .iter()
            .find(|(key, _)| key == column_id)
            .map(|(_, value)| value.as_str())
            .unwrap_or("-");
        tx.execute(
            "INSERT INTO distribution_snapshot_values (
                snapshot_month, column_key, column_label, column_order, value_text
             )
             VALUES (?, ?, ?, ?, ?)",
            params![row.month, column_id, label, index as i64, value],
        )
        .map_err(sqlite_err)?;
    }
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn distribution_unfreeze_month(db_path: &str, month: &str) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    let auto_fixed = conn
        .query_row(
            "SELECT auto_fixed FROM distribution_snapshots WHERE month = ?",
            [month],
            |row| row.get::<_, bool>(0),
        )
        .optional()
        .map_err(sqlite_err)?
        .unwrap_or(false);
    if auto_fixed {
        return Err(format!("Month {month} is auto-fixed and cannot be unfixed"));
    }
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "DELETE FROM distribution_snapshots WHERE month = ?",
        [month],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn distribution_frozen_rows(
    db_path: &str,
    start_month: Option<&str>,
    end_month: Option<&str>,
) -> StorageResult<Vec<FrozenDistributionPayload>> {
    with_cached_read_connection(db_path, |conn| {
        let mut clauses = Vec::new();
        if start_month.is_some() {
            clauses.push("month >= ?");
        }
        if end_month.is_some() {
            clauses.push("month <= ?");
        }
        let where_clause = if clauses.is_empty() {
            String::new()
        } else {
            format!("WHERE {}", clauses.join(" AND "))
        };
        let mut params_vec: Vec<String> = Vec::new();
        if let Some(start) = start_month {
            params_vec.push(start.to_owned());
        }
        if let Some(end) = end_month {
            params_vec.push(end.to_owned());
        }
        let mut stmt = conn
            .prepare(&format!(
                "SELECT month, is_negative, auto_fixed
                 FROM distribution_snapshots
                 {where_clause}
                 ORDER BY month ASC"
            ))
            .map_err(sqlite_err)?;
        let snapshot_rows = stmt
            .query_map(params_from_iter(params_vec.iter()), |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, bool>(1)?,
                    row.get::<_, bool>(2)?,
                ))
            })
            .map_err(sqlite_err)?
            .collect::<Result<Vec<_>, _>>()
            .map_err(sqlite_err)?;

        let mut rows = Vec::new();
        for (month, is_negative, auto_fixed) in snapshot_rows {
            let mut values_stmt = conn
                .prepare(
                    "SELECT column_key, column_label, value_text
                     FROM distribution_snapshot_values
                     WHERE snapshot_month = ?
                     ORDER BY column_order ASC",
                )
                .map_err(sqlite_err)?;
            let values = values_stmt
                .query_map([month.as_str()], |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                    ))
                })
                .map_err(sqlite_err)?
                .collect::<Result<Vec<_>, _>>()
                .map_err(sqlite_err)?;
            rows.push(FrozenDistributionPayload {
                month,
                column_order: values.iter().map(|(key, _, _)| key.clone()).collect(),
                headings_by_column: values
                    .iter()
                    .map(|(key, label, _)| (key.clone(), label.clone()))
                    .collect(),
                values_by_column: values
                    .into_iter()
                    .map(|(key, _, value)| (key, value))
                    .collect(),
                is_negative,
                auto_fixed,
            });
        }
        Ok(rows)
    })
}

pub fn distribution_replace_frozen_rows(
    db_path: &str,
    rows: &[FrozenDistributionPayload],
) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute("DELETE FROM distribution_snapshot_values", [])
        .map_err(sqlite_err)?;
    tx.execute("DELETE FROM distribution_snapshots", [])
        .map_err(sqlite_err)?;
    let mut sorted_rows = rows.to_vec();
    sorted_rows.sort_by(|left, right| left.month.cmp(&right.month));
    for row in &sorted_rows {
        tx.execute(
            "INSERT INTO distribution_snapshots (month, is_negative, auto_fixed)
             VALUES (?, ?, ?)",
            params![row.month, row.is_negative, row.auto_fixed],
        )
        .map_err(sqlite_err)?;
        for (index, column_id) in row.column_order.iter().enumerate() {
            let label = row
                .headings_by_column
                .iter()
                .find(|(key, _)| key == column_id)
                .map(|(_, value)| value.as_str())
                .unwrap_or(column_id);
            let value = row
                .values_by_column
                .iter()
                .find(|(key, _)| key == column_id)
                .map(|(_, value)| value.as_str())
                .unwrap_or("-");
            tx.execute(
                "INSERT INTO distribution_snapshot_values (
                    snapshot_month, column_key, column_label, column_order, value_text
                 )
                 VALUES (?, ?, ?, ?, ?)",
                params![row.month, column_id, label, index as i64, value],
            )
            .map_err(sqlite_err)?;
        }
    }
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn budget_rows(db_path: &str) -> StorageResult<Vec<BudgetPayload>> {
    with_cached_read_connection(db_path, |conn| {
        let mut stmt = conn
            .prepare(
                "SELECT id, category, start_date, end_date,
                        limit_base, limit_base_minor, include_mandatory, scope_type, scope_value
                 FROM budgets
                 ORDER BY start_date DESC, category ASC, id DESC",
            )
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| {
                Ok(BudgetPayload {
                    id: row.get(0)?,
                    category: row.get(1)?,
                    start_date: row.get(2)?,
                    end_date: row.get(3)?,
                    limit_base: row.get(4)?,
                    limit_base_minor: row.get(5)?,
                    include_mandatory: row.get(6)?,
                    scope_type: row.get(7)?,
                    scope_value: row.get(8)?,
                })
            })
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })
}

pub fn budget_create(
    db_path: &str,
    payload: BudgetCreatePayload<'_>,
) -> StorageResult<BudgetPayload> {
    validate_budget_payload(
        payload.category,
        payload.scope_type,
        payload.scope_value,
        payload.start_date,
        payload.end_date,
        payload.limit_base,
        payload.limit_base_minor,
    )?;
    let (category, scope_type, scope_value) = normalize_budget_fields(
        payload.category,
        payload.scope_type,
        payload.scope_value,
        payload.limit_base,
        payload.limit_base_minor,
    )?;
    if budget_overlap_exists(
        db_path,
        &scope_type,
        &scope_value,
        payload.start_date,
        payload.end_date,
        None,
    )? {
        return Err(format!(
            "Budget for '{}' already exists for overlapping period",
            payload.scope_value
        ));
    }
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "INSERT INTO budgets (
            category, scope_type, scope_value,
            start_date, end_date, limit_base, limit_base_minor, include_mandatory
         )
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        params![
            category,
            scope_type,
            scope_value,
            payload.start_date,
            payload.end_date,
            payload.limit_base,
            payload.limit_base_minor,
            payload.include_mandatory
        ],
    )
    .map_err(sqlite_err)?;
    let budget_id = tx.last_insert_rowid();
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    budget_from_conn(&conn, budget_id)
}

pub fn budget_delete(db_path: &str, budget_id: i64) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    if !budget_exists(&conn, budget_id)? {
        return Err(format!("Budget not found: {budget_id}"));
    }
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute("DELETE FROM budgets WHERE id = ?", [budget_id])
        .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn budget_update_limit(
    db_path: &str,
    budget_id: i64,
    limit_base: f64,
    limit_base_minor: i64,
) -> StorageResult<BudgetPayload> {
    if !limit_base.is_finite() || limit_base_minor <= 0 {
        return Err("Budget limit must be positive".to_owned());
    }
    let mut conn = open_write_connection(db_path)?;
    if !budget_exists(&conn, budget_id)? {
        return Err(format!("Budget not found: {budget_id}"));
    }
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "UPDATE budgets SET limit_base = ?, limit_base_minor = ? WHERE id = ?",
        params![limit_base, limit_base_minor, budget_id],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    budget_from_conn(&conn, budget_id)
}

pub fn budget_replace_rows(db_path: &str, budgets: &[BudgetPayload]) -> StorageResult<()> {
    for budget in budgets {
        validate_budget_payload(
            &budget.category,
            &budget.scope_type,
            &budget.scope_value,
            &budget.start_date,
            &budget.end_date,
            budget.limit_base,
            budget.limit_base_minor,
        )?;
    }
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute("DELETE FROM budgets", []).map_err(sqlite_err)?;
    let mut sorted = budgets.to_vec();
    sorted.sort_by_key(|budget| budget.id);
    for budget in &sorted {
        let (category, scope_type, scope_value) = normalize_budget_fields(
            &budget.category,
            &budget.scope_type,
            &budget.scope_value,
            budget.limit_base,
            budget.limit_base_minor,
        )?;
        tx.execute(
            "INSERT INTO budgets (
                id, category, start_date, end_date,
                limit_base, limit_base_minor, include_mandatory, scope_type, scope_value
             )
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params![
                budget.id,
                category,
                budget.start_date,
                budget.end_date,
                budget.limit_base,
                budget.limit_base_minor,
                budget.include_mandatory,
                scope_type,
                scope_value,
            ],
        )
        .map_err(sqlite_err)?;
    }
    tx.execute("DELETE FROM sqlite_sequence WHERE name = ?", ["budgets"])
        .map_err(sqlite_err)?;
    if let Some(max_id) = budgets.iter().map(|budget| budget.id).max() {
        tx.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES('budgets', ?)",
            [max_id],
        )
        .map_err(sqlite_err)?;
    }
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn budget_spent_minor(
    db_path: &str,
    scope_type: &str,
    scope_value: &str,
    start_date: &str,
    end_date: &str,
    include_mandatory: bool,
) -> StorageResult<i64> {
    with_cached_read_connection(db_path, |conn| {
        let minor_expr = minor_amount_expr("amount_base");
        let type_filter = if include_mandatory {
            "type IN ('expense', 'mandatory_expense')"
        } else {
            "type = 'expense'"
        };
        let sql = if scope_type == "tag" {
            format!(
                "SELECT COALESCE(SUM({minor_expr}), 0)
                 FROM records
                 WHERE {type_filter}
                   AND transfer_id IS NULL
                   AND date >= ?
                   AND date <= ?
                   AND EXISTS (
                        SELECT 1
                        FROM record_tags AS rt
                        JOIN tags AS t ON t.id = rt.tag_id
                        WHERE rt.record_id = records.id
                          AND lower(t.name) = lower(?)
                   )"
            )
        } else {
            format!(
                "SELECT COALESCE(SUM({minor_expr}), 0)
                 FROM records
                 WHERE {type_filter}
                   AND category = ?
                   AND transfer_id IS NULL
                   AND date >= ?
                   AND date <= ?"
            )
        };
        let params: [&dyn rusqlite::ToSql; 3] = if scope_type == "tag" {
            [&start_date, &end_date, &scope_value]
        } else {
            [&scope_value, &start_date, &end_date]
        };
        conn.query_row(&sql, params, |row| row.get::<_, i64>(0))
            .map_err(sqlite_err)
    })
}

pub fn budget_batch_spent_minor(
    db_path: &str,
    budgets: &[(i64, String, String, String, String, bool)],
) -> StorageResult<Vec<(i64, i64)>> {
    budgets
        .iter()
        .map(
            |(id, scope_type, scope_value, start_date, end_date, include_mandatory)| {
                budget_spent_minor(
                    db_path,
                    scope_type,
                    scope_value,
                    start_date,
                    end_date,
                    *include_mandatory,
                )
                .map(|spent| (*id, spent))
            },
        )
        .collect()
}

pub fn budget_results(
    db_path: &str,
    today: Option<&str>,
) -> StorageResult<Vec<BudgetResultPayload>> {
    let today = today.map(str::to_owned).unwrap_or_else(|| {
        let (year, month, day) = crate::current_local_date();
        format!("{year:04}-{month:02}-{day:02}")
    });
    budget_date_parts(&today)?;
    let budgets = budget_rows(db_path)?;
    budgets
        .into_iter()
        .map(|budget| {
            let spent_minor = budget_spent_minor(
                db_path,
                &budget.scope_type,
                &budget.scope_value,
                &budget.start_date,
                &budget.end_date,
                budget.include_mandatory,
            )?;
            let spent_base = minor_to_money_value(spent_minor);
            let limit_minor = budget.limit_base_minor;
            let usage_pct = if limit_minor > 0 {
                spent_minor as f64 / limit_minor as f64 * 100.0
            } else {
                0.0
            };
            let start = budget_date_parts(&budget.start_date)?;
            let end = budget_date_parts(&budget.end_date)?;
            let current = budget_date_parts(&today)?;
            let total_days = (budget_day_number(end.0, end.1, end.2)
                - budget_day_number(start.0, start.1, start.2)
                + 1)
            .max(1);
            let elapsed_days = if current < start {
                0
            } else if current > end {
                total_days
            } else {
                budget_day_number(current.0, current.1, current.2)
                    - budget_day_number(start.0, start.1, start.2)
                    + 1
            };
            let time_pct = (elapsed_days as f64 / total_days as f64 * 100.0 * 10.0).round() / 10.0;
            let status = budget_status(&budget.start_date, &budget.end_date, &today)?;
            let pace_status = if spent_minor >= limit_minor {
                "overspent"
            } else if usage_pct > time_pct + 10.0 {
                "overpace"
            } else {
                "on_track"
            };
            let (
                forecast_remaining_base,
                forecast_delta_base,
                forecast_days_left,
                forecast_status_key,
                forecast_status_params,
            ) = budget_forecast(&budget, spent_minor, &today)?;
            Ok(BudgetResultPayload {
                remaining_base: minor_to_money_value(limit_minor - spent_minor),
                budget,
                spent_base,
                spent_minor,
                usage_pct: (usage_pct * 10.0).round() / 10.0,
                time_pct,
                status: status.to_owned(),
                pace_status: pace_status.to_owned(),
                forecast_remaining_base,
                forecast_delta_base,
                forecast_days_left,
                forecast_status_key,
                forecast_status_params,
            })
        })
        .collect()
}

pub fn budget_overlap_exists(
    db_path: &str,
    scope_type: &str,
    scope_value: &str,
    start_date: &str,
    end_date: &str,
    exclude_id: Option<i64>,
) -> StorageResult<bool> {
    with_cached_read_connection(db_path, |conn| {
        let exclude_clause = if exclude_id.is_some() {
            "AND id != ?"
        } else {
            ""
        };
        let sql = format!(
            "SELECT 1
             FROM budgets
             WHERE scope_type = ?
               AND scope_value = ?
               AND start_date <= ?
               AND end_date >= ?
               {exclude_clause}
             LIMIT 1"
        );
        let exists = if let Some(id) = exclude_id {
            conn.query_row(
                &sql,
                (scope_type, scope_value, end_date, start_date, id),
                |_| Ok(()),
            )
            .optional()
        } else {
            conn.query_row(
                &sql,
                (scope_type, scope_value, end_date, start_date),
                |_| Ok(()),
            )
            .optional()
        }
        .map_err(sqlite_err)?
        .is_some();
        Ok(exists)
    })
}

pub fn debt_rows(db_path: &str) -> StorageResult<Vec<DebtPayload>> {
    with_cached_read_connection(db_path, |conn| {
        let mut stmt = conn
            .prepare(
                "SELECT id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                        currency, interest_rate, status, created_at, closed_at
                 FROM debts
                 ORDER BY id",
            )
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| {
                Ok(DebtPayload {
                    id: row.get(0)?,
                    contact_name: row.get(1)?,
                    kind: row.get(2)?,
                    total_amount_minor: row.get(3)?,
                    remaining_amount_minor: row.get(4)?,
                    currency: row.get(5)?,
                    interest_rate: row.get(6)?,
                    status: row.get(7)?,
                    created_at: row.get(8)?,
                    closed_at: row.get(9)?,
                })
            })
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })
}

pub fn debt_payment_rows(
    db_path: &str,
    debt_id: Option<i64>,
) -> StorageResult<Vec<DebtPaymentPayload>> {
    with_cached_read_connection(db_path, |conn| {
        let sql = if debt_id.is_some() {
            "SELECT id, debt_id, record_id, operation_type, principal_paid_minor,
                    is_write_off, payment_date
             FROM debt_payments
             WHERE debt_id = ?
             ORDER BY id"
        } else {
            "SELECT id, debt_id, record_id, operation_type, principal_paid_minor,
                    is_write_off, payment_date
             FROM debt_payments
             ORDER BY id"
        };
        let mut stmt = conn.prepare(sql).map_err(sqlite_err)?;
        let rows = if let Some(id) = debt_id {
            stmt.query_map([id], |row| {
                Ok(DebtPaymentPayload {
                    id: row.get(0)?,
                    debt_id: row.get(1)?,
                    record_id: row.get(2)?,
                    operation_type: row.get(3)?,
                    principal_paid_minor: row.get(4)?,
                    is_write_off: row.get(5)?,
                    payment_date: row.get(6)?,
                })
            })
            .map_err(sqlite_err)?
            .collect::<Result<Vec<_>, _>>()
        } else {
            stmt.query_map([], |row| {
                Ok(DebtPaymentPayload {
                    id: row.get(0)?,
                    debt_id: row.get(1)?,
                    record_id: row.get(2)?,
                    operation_type: row.get(3)?,
                    principal_paid_minor: row.get(4)?,
                    is_write_off: row.get(5)?,
                    payment_date: row.get(6)?,
                })
            })
            .map_err(sqlite_err)?
            .collect::<Result<Vec<_>, _>>()
        };
        rows.map_err(sqlite_err)
    })
}

pub fn debt_create_obligation(
    db_path: &str,
    debt: &DebtPayload,
    open_record: &DebtRecordPayload,
) -> StorageResult<DebtPayload> {
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let debt_id = insert_debt_row(&tx, debt, false)?;
    insert_debt_record_row(&tx, open_record, debt_id)?;
    let debt_id_map = normalize_debt_ids_in_tx(&tx)?;
    let normalized_debt_id = debt_id_map.get(&debt_id).copied().unwrap_or(debt_id);
    normalize_record_ids_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    debt_from_conn(&conn, normalized_debt_id)
}

pub fn debt_create(db_path: &str, payload: &DebtCreatePayload) -> StorageResult<DebtPayload> {
    let kind = payload.kind.trim().to_lowercase();
    if kind != "debt" && kind != "loan" {
        return Err("Debt kind must be debt or loan".to_owned());
    }
    let contact_name = payload.contact_name.trim();
    if contact_name.is_empty() {
        return Err("Contact name is required".to_owned());
    }
    if payload.wallet_id <= 0 {
        return Err("Wallet is required".to_owned());
    }
    let created_at = payload.created_at.trim();
    validate_debt_date(created_at)?;
    let amount_minor = to_minor_units(&payload.amount)?;
    if amount_minor <= 0 {
        return Err("Amount must be positive".to_owned());
    }

    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let base_currency = base_currency_code_for_debt_in_tx(&tx)?;
    let currency = normalize_currency_code(&payload.currency, &base_currency);
    if !currency.eq_ignore_ascii_case(&base_currency) {
        return Err(format!(
            "Kotlin Debts currently supports base-currency obligations only ({base_currency})"
        ));
    }
    let allow_negative = active_debt_wallet_in_tx(&tx, payload.wallet_id)?;
    if kind == "loan" && !allow_negative {
        let balance_minor = wallet_balance_minor_for_debt_in_tx(&tx, payload.wallet_id)?;
        if balance_minor - amount_minor < 0 {
            return Err("Insufficient funds in wallet".to_owned());
        }
    }

    let amount_base = minor_to_money_value(amount_minor);
    let debt = DebtPayload {
        id: 0,
        contact_name: contact_name.to_owned(),
        kind: kind.clone(),
        total_amount_minor: amount_minor,
        remaining_amount_minor: amount_minor,
        currency: currency.clone(),
        interest_rate: 0.0,
        status: "open".to_owned(),
        created_at: created_at.to_owned(),
        closed_at: None,
    };
    let debt_id = insert_debt_row(&tx, &debt, false)?;
    let description = payload.description.trim();
    let record = DebtRecordPayload {
        record_type: if kind == "debt" {
            "income".to_owned()
        } else {
            "expense".to_owned()
        },
        date: created_at.to_owned(),
        wallet_id: payload.wallet_id,
        amount_original: amount_base,
        amount_original_minor: amount_minor,
        currency,
        rate_at_operation: 1.0,
        rate_at_operation_text: "1.000000".to_owned(),
        amount_base,
        amount_base_minor: amount_minor,
        category: if kind == "debt" {
            "Debt".to_owned()
        } else {
            "Loan".to_owned()
        },
        description: if description.is_empty() {
            contact_name.to_owned()
        } else {
            description.to_owned()
        },
        period: None,
    };
    insert_debt_record_row(&tx, &record, debt_id)?;
    let debt_id_map = normalize_debt_ids_in_tx(&tx)?;
    let normalized_debt_id = debt_id_map.get(&debt_id).copied().unwrap_or(debt_id);
    normalize_record_ids_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    debt_from_conn(&conn, normalized_debt_id)
}

pub fn debt_register_payment_validated(
    db_path: &str,
    payload: &DebtPaymentRequestPayload,
) -> StorageResult<DebtPaymentPayload> {
    let amount_minor = to_minor_units(&payload.amount)?;
    let mut conn = open_write_connection(db_path)?;
    let payment_date = payload.payment_date.trim();
    validate_debt_date(payment_date)?;
    let wallet_id = payload
        .wallet_id
        .filter(|wallet_id| *wallet_id > 0)
        .ok_or_else(|| "Wallet is required".to_owned())?;

    let tx = conn.transaction().map_err(sqlite_err)?;
    let debt = debt_from_conn(&tx, payload.debt_id)?;
    if debt.status == "closed" || debt.remaining_amount_minor <= 0 {
        return Err("Debt is already closed".to_owned());
    }
    let payment_amount_minor =
        debt_validate_payment_amount(debt.remaining_amount_minor, amount_minor)?;
    let allow_negative = active_debt_wallet_in_tx(&tx, wallet_id)?;
    if debt.kind == "debt" && !allow_negative {
        let balance_minor = wallet_balance_minor_for_debt_in_tx(&tx, wallet_id)?;
        if balance_minor - payment_amount_minor < 0 {
            return Err("Insufficient funds in wallet".to_owned());
        }
    }

    let amount_base = minor_to_money_value(payment_amount_minor);
    let payment = DebtPaymentPayload {
        id: 0,
        debt_id: debt.id,
        record_id: None,
        operation_type: if debt.kind == "loan" {
            "loan_collect".to_owned()
        } else {
            "debt_repay".to_owned()
        },
        principal_paid_minor: payment_amount_minor,
        is_write_off: false,
        payment_date: payment_date.to_owned(),
    };
    let record = DebtRecordPayload {
        record_type: if debt.kind == "loan" {
            "income".to_owned()
        } else {
            "expense".to_owned()
        },
        date: payment_date.to_owned(),
        wallet_id,
        amount_original: amount_base,
        amount_original_minor: payment_amount_minor,
        currency: debt.currency.clone(),
        rate_at_operation: 1.0,
        rate_at_operation_text: "1".to_owned(),
        amount_base,
        amount_base_minor: payment_amount_minor,
        category: if debt.kind == "loan" {
            "Loan payment".to_owned()
        } else {
            "Debt payment".to_owned()
        },
        description: if payload.description.trim().is_empty() {
            debt.contact_name
        } else {
            payload.description.trim().to_owned()
        },
        period: None,
    };
    let payment_id = debt_register_payment_in_tx(&tx, debt.id, &payment, Some(&record))?;
    normalize_record_ids_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    debt_payment_from_conn(&conn, payment_id)
}

pub fn debt_register_write_off_validated(
    db_path: &str,
    payload: &DebtPaymentRequestPayload,
) -> StorageResult<DebtPaymentPayload> {
    let amount_minor = to_minor_units(&payload.amount)?;
    let mut conn = open_write_connection(db_path)?;
    let payment_date = payload.payment_date.trim();
    validate_debt_date(payment_date)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let debt = debt_from_conn(&tx, payload.debt_id)?;
    if debt.status == "closed" || debt.remaining_amount_minor <= 0 {
        return Err("Debt is already closed".to_owned());
    }
    let payment_amount_minor =
        debt_validate_payment_amount(debt.remaining_amount_minor, amount_minor)?;
    let payment = DebtPaymentPayload {
        id: 0,
        debt_id: debt.id,
        record_id: None,
        operation_type: "debt_forgive".to_owned(),
        principal_paid_minor: payment_amount_minor,
        is_write_off: true,
        payment_date: payment_date.to_owned(),
    };
    let payment_id = debt_register_payment_in_tx(&tx, debt.id, &payment, None)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    debt_payment_from_conn(&conn, payment_id)
}

pub fn debt_close_validated(
    db_path: &str,
    payload: &DebtPaymentRequestPayload,
) -> StorageResult<DebtPayload> {
    let mut conn = open_write_connection(db_path)?;
    let payment_date = payload.payment_date.trim();
    validate_debt_date(payment_date)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let debt = debt_from_conn(&tx, payload.debt_id)?;
    if debt.status == "closed" || debt.remaining_amount_minor <= 0 {
        return Ok(debt);
    }
    let wallet_id = payload
        .wallet_id
        .filter(|wallet_id| *wallet_id > 0)
        .ok_or_else(|| "Wallet is required".to_owned())?;
    let allow_negative = active_debt_wallet_in_tx(&tx, wallet_id)?;
    if debt.kind == "debt" && !allow_negative {
        let balance_minor = wallet_balance_minor_for_debt_in_tx(&tx, wallet_id)?;
        if balance_minor - debt.remaining_amount_minor < 0 {
            return Err("Insufficient funds in wallet".to_owned());
        }
    }
    let amount_base = minor_to_money_value(debt.remaining_amount_minor);
    let payment = DebtPaymentPayload {
        id: 0,
        debt_id: debt.id,
        record_id: None,
        operation_type: if debt.kind == "loan" {
            "loan_collect".to_owned()
        } else {
            "debt_repay".to_owned()
        },
        principal_paid_minor: debt.remaining_amount_minor,
        is_write_off: false,
        payment_date: payment_date.to_owned(),
    };
    let record = DebtRecordPayload {
        record_type: if debt.kind == "loan" {
            "income".to_owned()
        } else {
            "expense".to_owned()
        },
        date: payment_date.to_owned(),
        wallet_id,
        amount_original: amount_base,
        amount_original_minor: debt.remaining_amount_minor,
        currency: debt.currency.clone(),
        rate_at_operation: 1.0,
        rate_at_operation_text: "1".to_owned(),
        amount_base,
        amount_base_minor: debt.remaining_amount_minor,
        category: if debt.kind == "loan" {
            "Loan payment".to_owned()
        } else {
            "Debt payment".to_owned()
        },
        description: if payload.description.trim().is_empty() {
            debt.contact_name
        } else {
            payload.description.trim().to_owned()
        },
        period: None,
    };
    debt_register_payment_in_tx(&tx, debt.id, &payment, Some(&record))?;
    normalize_record_ids_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    debt_from_conn(&conn, payload.debt_id)
}

pub fn debt_delete(db_path: &str, debt_id: i64) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    debt_from_conn(&conn, debt_id)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute(
        "UPDATE records SET related_debt_id = NULL WHERE related_debt_id = ?",
        [debt_id],
    )
    .map_err(sqlite_err)?;
    tx.execute("DELETE FROM debt_payments WHERE debt_id = ?", [debt_id])
        .map_err(sqlite_err)?;
    tx.execute("DELETE FROM debts WHERE id = ?", [debt_id])
        .map_err(sqlite_err)?;
    normalize_debt_ids_in_tx(&tx)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn debt_register_payment(
    db_path: &str,
    debt_id: i64,
    payment: &DebtPaymentPayload,
    payment_record: Option<&DebtRecordPayload>,
) -> StorageResult<DebtPaymentPayload> {
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    let payment_id = debt_register_payment_in_tx(&tx, debt_id, payment, payment_record)?;
    if payment_record.is_some() {
        normalize_record_ids_in_tx(&tx)?;
    }
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    debt_payment_from_conn(&conn, payment_id)
}

fn debt_register_payment_in_tx(
    tx: &rusqlite::Transaction<'_>,
    debt_id: i64,
    payment: &DebtPaymentPayload,
    payment_record: Option<&DebtRecordPayload>,
) -> StorageResult<i64> {
    if payment.debt_id != debt_id {
        return Err("Payment debt id does not match target debt".to_owned());
    }
    let debt = debt_from_conn(tx, debt_id)?;
    if debt.status == "closed" || debt.remaining_amount_minor <= 0 {
        return Err("Debt is already closed".to_owned());
    }
    let payment_amount_minor =
        debt_validate_payment_amount(debt.remaining_amount_minor, payment.principal_paid_minor)?;
    validate_debt_date(payment.payment_date.as_str())?;
    let record_id = if let Some(record) = payment_record {
        Some(insert_debt_record_row(&tx, record, debt_id)?)
    } else {
        None
    };
    let payment_id = insert_debt_payment_row(&tx, payment, debt_id, record_id, false)?;
    let remaining_amount_minor = debt.remaining_amount_minor - payment_amount_minor;
    let is_closed = remaining_amount_minor == 0;
    tx.execute(
        "UPDATE debts
         SET remaining_amount_minor = ?, status = ?, closed_at = ?
         WHERE id = ?",
        params![
            remaining_amount_minor,
            if is_closed { "closed" } else { "open" },
            if is_closed {
                Some(payment.payment_date.as_str())
            } else {
                None
            },
            debt_id
        ],
    )
    .map_err(sqlite_err)?;
    Ok(payment_id)
}

pub fn debt_delete_payment(
    db_path: &str,
    payment_id: i64,
    delete_linked_record: bool,
) -> StorageResult<DebtPayload> {
    let mut conn = open_write_connection(db_path)?;
    let payment = debt_payment_from_conn(&conn, payment_id)?;
    let debt = debt_from_conn(&conn, payment.debt_id)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    if delete_linked_record {
        if let Some(record_id) = payment.record_id {
            let linked_record = tx
                .query_row(
                    "SELECT type, transfer_id, related_debt_id
                     FROM records
                     WHERE id = ?",
                    [record_id],
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
            let Some((record_type, transfer_id, related_debt_id)) = linked_record else {
                return Err(format!(
                    "Debt payment #{payment_id} linked record not found: {record_id}"
                ));
            };
            if transfer_id.is_some()
                || related_debt_id != Some(payment.debt_id)
                || (record_type != "income" && record_type != "expense")
            {
                return Err(format!(
                    "Debt payment #{payment_id} linked record {record_id} does not belong to debt {}",
                    payment.debt_id
                ));
            }
            tx.execute("DELETE FROM record_tags WHERE record_id = ?", [record_id])
                .map_err(sqlite_err)?;
            let deleted = tx
                .execute(
                    "DELETE FROM records
                     WHERE id = ?
                       AND related_debt_id = ?
                       AND transfer_id IS NULL
                       AND type IN ('income', 'expense')",
                    (record_id, payment.debt_id),
                )
                .map_err(sqlite_err)?;
            if deleted != 1 {
                return Err(format!(
                    "Debt payment #{payment_id} linked record delete failed: {record_id}"
                ));
            }
            refresh_tag_metrics_in_tx(&tx)?;
            prune_orphan_tags_in_tx(&tx)?;
            normalize_record_ids_in_tx(&tx)?;
        }
    }
    tx.execute("DELETE FROM debt_payments WHERE id = ?", [payment_id])
        .map_err(sqlite_err)?;
    let restored_remaining =
        (debt.remaining_amount_minor + payment.principal_paid_minor).min(debt.total_amount_minor);
    tx.execute(
        "UPDATE debts
         SET remaining_amount_minor = ?, status = ?, closed_at = ?
         WHERE id = ?",
        params![
            restored_remaining,
            if restored_remaining > 0 {
                "open"
            } else {
                debt.status.as_str()
            },
            if restored_remaining > 0 {
                None::<&str>
            } else {
                debt.closed_at.as_deref()
            },
            payment.debt_id
        ],
    )
    .map_err(sqlite_err)?;
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    let conn = open_write_connection(db_path)?;
    debt_from_conn(&conn, payment.debt_id)
}

fn normalize_debt_ids_in_tx(
    tx: &rusqlite::Transaction<'_>,
) -> StorageResult<std::collections::HashMap<i64, i64>> {
    let mut stmt = tx
        .prepare("SELECT id FROM debts ORDER BY created_at, id")
        .map_err(sqlite_err)?;
    let rows = stmt
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)?;
    let ordered_ids = rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)?;
    let debt_id_map: std::collections::HashMap<i64, i64> = ordered_ids
        .iter()
        .enumerate()
        .map(|(index, old_id)| (*old_id, i64::try_from(index + 1).unwrap_or(i64::MAX)))
        .collect();
    if debt_id_map.iter().all(|(old_id, new_id)| old_id == new_id) {
        return Ok(debt_id_map);
    }

    for (old_id, new_id) in &debt_id_map {
        let temp_id = -*new_id;
        tx.execute("UPDATE debts SET id = ? WHERE id = ?", (temp_id, old_id))
            .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE records SET related_debt_id = ? WHERE related_debt_id = ?",
            (temp_id, old_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE debt_payments SET debt_id = ? WHERE debt_id = ?",
            (temp_id, old_id),
        )
        .map_err(sqlite_err)?;
    }

    for new_id in debt_id_map.values() {
        let temp_id = -*new_id;
        tx.execute("UPDATE debts SET id = ? WHERE id = ?", (new_id, temp_id))
            .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE records SET related_debt_id = ? WHERE related_debt_id = ?",
            (new_id, temp_id),
        )
        .map_err(sqlite_err)?;
        tx.execute(
            "UPDATE debt_payments SET debt_id = ? WHERE debt_id = ?",
            (new_id, temp_id),
        )
        .map_err(sqlite_err)?;
    }

    reset_debt_sqlite_sequence_to_max_id_in_tx(tx, "debts")?;
    Ok(debt_id_map)
}

fn reset_debt_sqlite_sequence_to_max_id_in_tx(
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
    tx.execute("DELETE FROM sqlite_sequence WHERE name = ?", [table])
        .map_err(sqlite_err)?;
    if max_id > 0 {
        tx.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES(?, ?)",
            (table, max_id),
        )
        .map_err(sqlite_err)?;
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

pub fn debt_replace_rows(
    db_path: &str,
    debts: &[DebtPayload],
    payments: &[DebtPaymentPayload],
) -> StorageResult<()> {
    let mut conn = open_write_connection(db_path)?;
    let tx = conn.transaction().map_err(sqlite_err)?;
    tx.execute("DELETE FROM debt_payments", [])
        .map_err(sqlite_err)?;
    tx.execute("DELETE FROM debts", []).map_err(sqlite_err)?;
    tx.execute(
        "DELETE FROM sqlite_sequence WHERE name IN ('debts', 'debt_payments')",
        [],
    )
    .map_err(sqlite_err)?;

    let mut sorted_debts = debts.to_vec();
    sorted_debts.sort_by_key(|debt| debt.id);
    for debt in &sorted_debts {
        insert_debt_row(&tx, debt, true)?;
    }

    let mut sorted_payments = payments.to_vec();
    sorted_payments.sort_by_key(|payment| payment.id);
    for payment in &sorted_payments {
        if !sorted_debts.iter().any(|debt| debt.id == payment.debt_id) {
            return Err(format!(
                "Debt payment #{} references missing debt {}",
                payment.id, payment.debt_id
            ));
        }
        if let Some(record_id) = payment.record_id {
            let exists = tx
                .query_row(
                    "SELECT 1 FROM records WHERE id = ?",
                    [record_id],
                    |_| Ok(()),
                )
                .optional()
                .map_err(sqlite_err)?
                .is_some();
            if !exists {
                return Err(format!(
                    "Debt payment #{} references missing record {}",
                    payment.id, record_id
                ));
            }
        }
        insert_debt_payment_row(&tx, payment, payment.debt_id, payment.record_id, true)?;
    }

    if let Some(max_id) = debts.iter().map(|debt| debt.id).max() {
        tx.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES('debts', ?)",
            [max_id],
        )
        .map_err(sqlite_err)?;
    }
    if let Some(max_id) = payments.iter().map(|payment| payment.id).max() {
        tx.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES('debt_payments', ?)",
            [max_id],
        )
        .map_err(sqlite_err)?;
    }
    tx.commit().map_err(sqlite_err)?;
    storage_clear_read_connection_cache();
    Ok(())
}

pub fn debt_payment_total_minor(db_path: &str, debt_id: i64) -> StorageResult<i64> {
    with_cached_read_connection(db_path, |conn| {
        conn.query_row(
            "SELECT COALESCE(SUM(principal_paid_minor), 0)
             FROM debt_payments
             WHERE debt_id = ?",
            [debt_id],
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)
    })
}

pub fn debt_recalculate_payload(
    db_path: &str,
    debt_id: i64,
) -> StorageResult<DebtRecalculatePayload> {
    with_cached_read_connection(db_path, |conn| {
        let total_amount_minor = conn
            .query_row(
                "SELECT total_amount_minor FROM debts WHERE id = ?",
                [debt_id],
                |row| row.get::<_, i64>(0),
            )
            .map_err(sqlite_err)?;
        let (paid_minor, latest_payment_date) = conn
            .query_row(
                "SELECT COALESCE(SUM(principal_paid_minor), 0), MAX(payment_date)
                 FROM debt_payments
                 WHERE debt_id = ?",
                [debt_id],
                |row| Ok((row.get::<_, i64>(0)?, row.get::<_, Option<String>>(1)?)),
            )
            .map_err(sqlite_err)?;
        let remaining_amount_minor = (total_amount_minor - paid_minor).max(0);
        let is_closed = remaining_amount_minor == 0;
        Ok(DebtRecalculatePayload {
            remaining_amount_minor,
            status: if is_closed { "closed" } else { "open" }.to_owned(),
            closed_at: if is_closed { latest_payment_date } else { None },
        })
    })
}

pub fn debt_validate_payment_amount(
    remaining_amount_minor: i64,
    payment_amount_minor: i64,
) -> StorageResult<i64> {
    if payment_amount_minor <= 0 {
        return Err("Payment amount must be positive".to_owned());
    }
    if payment_amount_minor > remaining_amount_minor {
        return Err("Payment amount exceeds remaining debt".to_owned());
    }
    Ok(payment_amount_minor)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn apply_pct_rounds_half_up_for_positive_and_negative_values() {
        assert_eq!(apply_pct(101, 5000), 51);
        assert_eq!(apply_pct(-101, 5000), -51);
    }

    fn test_db_path(name: &str) -> String {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        std::env::temp_dir()
            .join(format!("ledgera_{name}_{nanos}.db"))
            .to_string_lossy()
            .into_owned()
    }

    fn init_distribution_schema(db_path: &str) {
        let conn = Connection::open(db_path).expect("open test db");
        conn.execute_batch(
            "
            CREATE TABLE budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                scope_type TEXT NOT NULL DEFAULT 'category',
                scope_value TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                limit_base REAL NOT NULL,
                limit_base_minor INTEGER NOT NULL DEFAULT 0,
                include_mandatory INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                date TEXT NOT NULL,
                wallet_id INTEGER NOT NULL,
                transfer_id INTEGER,
                related_debt_id INTEGER,
                amount_original REAL NOT NULL,
                amount_original_minor INTEGER,
                currency TEXT NOT NULL,
                rate_at_operation REAL NOT NULL,
                rate_at_operation_text TEXT NOT NULL,
                amount_base REAL NOT NULL,
                amount_base_minor INTEGER,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                period TEXT
            );
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
            CREATE TABLE schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            CREATE TABLE distribution_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                group_name TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                pct REAL NOT NULL DEFAULT 0.0,
                pct_minor INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE distribution_subitems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                pct REAL NOT NULL DEFAULT 0.0,
                pct_minor INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(item_id) REFERENCES distribution_items(id) ON DELETE CASCADE,
                UNIQUE(item_id, name)
            );
            CREATE TABLE distribution_snapshots (
                month TEXT PRIMARY KEY,
                is_negative INTEGER NOT NULL DEFAULT 0,
                auto_fixed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE distribution_snapshot_values (
                snapshot_month TEXT NOT NULL,
                column_key TEXT NOT NULL,
                column_label TEXT NOT NULL,
                column_order INTEGER NOT NULL,
                value_text TEXT NOT NULL,
                PRIMARY KEY(snapshot_month, column_key),
                FOREIGN KEY(snapshot_month) REFERENCES distribution_snapshots(month) ON DELETE CASCADE
            );
            ",
        )
        .expect("schema");
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('base_currency', 'KZT')",
            [],
        )
        .expect("base currency");
        conn.execute(
            "INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor, system, allow_negative, is_active
             ) VALUES (1, 'Cash', 'KZT', 1000.0, 100000, 1, 0, 1)",
            [],
        )
        .expect("wallet 1");
        conn.execute(
            "INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor, system, allow_negative, is_active
             ) VALUES (2, 'Negative', 'KZT', 0.0, 0, 0, 1, 1)",
            [],
        )
        .expect("wallet 2");
        conn.execute(
            "INSERT INTO wallets (
                id, name, currency, initial_balance, initial_balance_minor, system, allow_negative, is_active
             ) VALUES (3, 'Inactive', 'KZT', 0.0, 0, 0, 0, 0)",
            [],
        )
        .expect("wallet 3");
    }

    fn test_debt(contact_name: &str, amount_minor: i64) -> DebtPayload {
        DebtPayload {
            id: 1,
            contact_name: contact_name.to_owned(),
            kind: "debt".to_owned(),
            total_amount_minor: amount_minor,
            remaining_amount_minor: amount_minor,
            currency: "KZT".to_owned(),
            interest_rate: 0.0,
            status: "open".to_owned(),
            created_at: "2026-03-01".to_owned(),
            closed_at: None,
        }
    }

    fn test_debt_record(record_type: &str, amount_minor: i64) -> DebtRecordPayload {
        DebtRecordPayload {
            record_type: record_type.to_owned(),
            date: "2026-03-01".to_owned(),
            wallet_id: 1,
            amount_original: minor_to_money_value(amount_minor),
            amount_original_minor: amount_minor,
            currency: "KZT".to_owned(),
            rate_at_operation: 1.0,
            rate_at_operation_text: "1.000000".to_owned(),
            amount_base: minor_to_money_value(amount_minor),
            amount_base_minor: amount_minor,
            category: "Debt".to_owned(),
            description: "Alice".to_owned(),
            period: None,
        }
    }

    fn test_payment(debt_id: i64, amount_minor: i64, write_off: bool) -> DebtPaymentPayload {
        DebtPaymentPayload {
            id: 1,
            debt_id,
            record_id: None,
            operation_type: if write_off {
                "debt_forgive"
            } else {
                "debt_repay"
            }
            .to_owned(),
            principal_paid_minor: amount_minor,
            is_write_off: write_off,
            payment_date: "2026-03-05".to_owned(),
        }
    }

    #[test]
    fn distribution_crud_and_replace_structure_preserve_sequences() {
        let db_path = test_db_path("distribution_crud");
        init_distribution_schema(&db_path);
        let item =
            distribution_create_item(&db_path, "Needs", "", 0, 100.0, 10000).expect("create item");
        assert_eq!(item.id, 1);
        let subitem = distribution_create_subitem(&db_path, item.id, "Rent", 0, 100.0, 10000)
            .expect("create subitem");
        assert_eq!(subitem.id, 1);
        assert!(
            distribution_create_item(&db_path, "Needs", "", 1, 0.0, 0)
                .expect_err("duplicate")
                .contains("already exists")
        );
        let updated = distribution_update_item_name(&db_path, item.id, "Core").expect("rename");
        assert_eq!(updated.name, "Core");
        distribution_delete_subitem(&db_path, subitem.id).expect("delete subitem");
        assert!(
            distribution_subitem_rows(&db_path, item.id, false)
                .expect("subitems")
                .is_empty()
        );

        let replacement_item = DistributionItemPayload {
            id: 7,
            name: "Replacement".to_owned(),
            group_name: "".to_owned(),
            sort_order: 0,
            pct: 100.0,
            pct_minor: 10000,
            is_active: true,
            amount_base: 0.0,
            amount_minor: 0,
            subitems: Vec::new(),
        };
        let replacement_subitem = DistributionSubitemPayload {
            id: 9,
            item_id: 7,
            name: "Child".to_owned(),
            sort_order: 0,
            pct: 100.0,
            pct_minor: 10000,
            is_active: true,
            amount_base: 0.0,
            amount_minor: 0,
        };
        distribution_replace_structure(&db_path, &[replacement_item], &[replacement_subitem])
            .expect("replace");
        let created = distribution_create_item(&db_path, "Next", "", 1, 0.0, 0)
            .expect("create after replace");
        assert_eq!(created.id, 8);
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn distribution_frozen_rows_round_trip_and_auto_unfreeze_guard() {
        let db_path = test_db_path("distribution_snapshots");
        init_distribution_schema(&db_path);
        let row = FrozenDistributionPayload {
            month: "2026-03".to_owned(),
            column_order: vec!["month".to_owned(), "net_income".to_owned()],
            headings_by_column: vec![
                ("month".to_owned(), "Month".to_owned()),
                ("net_income".to_owned(), "Net income".to_owned()),
            ],
            values_by_column: vec![
                ("month".to_owned(), "2026-03".to_owned()),
                ("net_income".to_owned(), "1,000".to_owned()),
            ],
            is_negative: false,
            auto_fixed: true,
        };
        distribution_write_frozen_row(&db_path, &row).expect("write frozen");
        assert!(distribution_is_month_fixed(&db_path, "2026-03").expect("fixed"));
        assert!(distribution_is_month_auto_fixed(&db_path, "2026-03").expect("auto"));
        assert!(
            distribution_unfreeze_month(&db_path, "2026-03")
                .expect_err("auto-fixed")
                .contains("auto-fixed")
        );
        let rows = distribution_frozen_rows(&db_path, None, None).expect("frozen rows");
        assert_eq!(rows, vec![row]);
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn budget_crud_and_replace_rows_preserve_sequences() {
        let db_path = test_db_path("budget_crud");
        init_distribution_schema(&db_path);
        let budget = budget_create(
            &db_path,
            BudgetCreatePayload {
                category: "Food",
                scope_type: "category",
                scope_value: "Food",
                start_date: "2026-03-01",
                end_date: "2026-03-31",
                limit_base: 1000.0,
                limit_base_minor: 100000,
                include_mandatory: true,
            },
        )
        .expect("create budget");
        assert_eq!(budget.id, 1);
        assert_eq!(budget.limit_base_minor, 100000);
        let updated =
            budget_update_limit(&db_path, budget.id, 1250.0, 125000).expect("update limit");
        assert_eq!(updated.limit_base, 1250.0);
        assert_eq!(updated.limit_base_minor, 125000);
        assert!(
            budget_update_limit(&db_path, 999, 1.0, 100)
                .expect_err("missing update")
                .contains("Budget not found: 999")
        );
        budget_delete(&db_path, budget.id).expect("delete");
        assert!(budget_rows(&db_path).expect("rows").is_empty());
        assert!(
            budget_delete(&db_path, budget.id)
                .expect_err("missing delete")
                .contains("Budget not found: 1")
        );

        let replacement = BudgetPayload {
            id: 7,
            category: "Travel".to_owned(),
            start_date: "2026-04-01".to_owned(),
            end_date: "2026-04-30".to_owned(),
            limit_base: 500.0,
            limit_base_minor: 50000,
            include_mandatory: false,
            scope_type: "category".to_owned(),
            scope_value: "Travel".to_owned(),
        };
        budget_replace_rows(&db_path, &[replacement]).expect("replace");
        let created = budget_create(
            &db_path,
            BudgetCreatePayload {
                category: "Next",
                scope_type: "category",
                scope_value: "Next",
                start_date: "2026-05-01",
                end_date: "2026-05-31",
                limit_base: 100.0,
                limit_base_minor: 10000,
                include_mandatory: false,
            },
        )
        .expect("create after replace");
        assert_eq!(created.id, 8);
        let results = budget_results(&db_path, Some("2026-04-15")).expect("results");
        assert_eq!(results.len(), 2);
        let travel = results
            .iter()
            .find(|item| item.budget.id == 7)
            .expect("travel result");
        assert_eq!(travel.status, "active");
        assert_eq!(travel.pace_status, "on_track");
        assert_eq!(travel.spent_minor, 0);
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn budget_overlap_helper_matches_period_contract() {
        let db_path = test_db_path("budget_overlap");
        init_distribution_schema(&db_path);
        budget_create(
            &db_path,
            BudgetCreatePayload {
                category: "Food",
                scope_type: "category",
                scope_value: "Food",
                start_date: "2026-03-01",
                end_date: "2026-03-31",
                limit_base: 1000.0,
                limit_base_minor: 100000,
                include_mandatory: false,
            },
        )
        .expect("create budget");
        assert!(
            budget_overlap_exists(
                &db_path,
                "category",
                "Food",
                "2026-03-15",
                "2026-04-15",
                None,
            )
            .expect("overlap")
        );
        assert!(
            !budget_overlap_exists(
                &db_path,
                "category",
                "Food",
                "2026-04-01",
                "2026-04-30",
                None,
            )
            .expect("adjacent")
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn debt_create_payment_delete_and_replace_preserve_contracts() {
        let db_path = test_db_path("debt_write");
        init_distribution_schema(&db_path);
        let debt = debt_create_obligation(
            &db_path,
            &test_debt("Alice", 50_000),
            &test_debt_record("income", 50_000),
        )
        .expect("create debt");
        assert_eq!(debt.id, 1);
        assert_eq!(debt.remaining_amount_minor, 50_000);

        let payment = debt_register_payment(
            &db_path,
            debt.id,
            &test_payment(debt.id, 20_000, false),
            Some(&test_debt_record("expense", 20_000)),
        )
        .expect("register payment");
        assert_eq!(payment.id, 1);
        assert!(payment.record_id.is_some());
        let conn = Connection::open(&db_path).expect("open");
        assert_eq!(
            debt_from_conn(&conn, debt.id)
                .expect("debt")
                .remaining_amount_minor,
            30_000
        );
        let record_id = payment.record_id.expect("linked record");
        conn.execute(
            "INSERT INTO tags (id, name, color, usage_count, last_used_at)
             VALUES (1, 'debt-payment', '#5B8DEF', 1, '2026-03-05')",
            [],
        )
        .expect("tag");
        conn.execute(
            "INSERT INTO record_tags (record_id, tag_id) VALUES (?, 1)",
            [record_id],
        )
        .expect("record tag");
        drop(conn);

        let reopened = debt_delete_payment(&db_path, payment.id, true).expect("delete payment");
        assert_eq!(reopened.remaining_amount_minor, 50_000);
        assert!(
            debt_payment_rows(&db_path, Some(debt.id))
                .expect("payments")
                .is_empty()
        );
        let conn = Connection::open(&db_path).expect("open");
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM record_tags", [], |row| row
                .get::<_, i64>(0))
                .expect("record_tags"),
            0
        );
        assert_eq!(
            conn.query_row("SELECT COUNT(*) FROM tags", [], |row| row.get::<_, i64>(0))
                .expect("tags"),
            0
        );
        drop(conn);

        let write_off = debt_register_payment(
            &db_path,
            debt.id,
            &test_payment(debt.id, 50_000, true),
            None,
        )
        .expect("write off");
        assert!(write_off.record_id.is_none());
        let conn = Connection::open(&db_path).expect("open");
        assert_eq!(
            debt_from_conn(&conn, debt.id).expect("debt").status,
            "closed"
        );

        let replacement_debt = DebtPayload {
            id: 7,
            contact_name: "Bob".to_owned(),
            kind: "loan".to_owned(),
            total_amount_minor: 10_000,
            remaining_amount_minor: 10_000,
            currency: "KZT".to_owned(),
            interest_rate: 0.0,
            status: "open".to_owned(),
            created_at: "2026-04-01".to_owned(),
            closed_at: None,
        };
        debt_replace_rows(&db_path, std::slice::from_ref(&replacement_debt), &[])
            .expect("replace debts");
        let next = debt_create_obligation(
            &db_path,
            &test_debt("Next", 10_000),
            &test_debt_record("income", 10_000),
        )
        .expect("create after replace");
        assert_eq!(next.id, 1);
        let conn = Connection::open(&db_path).unwrap();
        let debt_ids: Vec<i64> = {
            let mut stmt = conn.prepare("SELECT id FROM debts ORDER BY id").unwrap();
            stmt.query_map([], |row| row.get(0))
                .unwrap()
                .collect::<Result<Vec<_>, _>>()
                .unwrap()
        };
        assert_eq!(debt_ids, vec![1, 2]);
        drop(conn);
        assert!(
            debt_delete(&db_path, 999)
                .expect_err("missing delete")
                .contains("Debt not found: 999")
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn debt_delete_payment_rejects_linked_record_owned_by_another_contract() {
        let db_path = test_db_path("debt_delete_payment_corrupt_link");
        init_distribution_schema(&db_path);
        let debt = debt_create_obligation(
            &db_path,
            &test_debt("Alice", 50_000),
            &test_debt_record("income", 50_000),
        )
        .expect("create debt");
        let payment = debt_register_payment(
            &db_path,
            debt.id,
            &test_payment(debt.id, 20_000, false),
            Some(&test_debt_record("expense", 20_000)),
        )
        .expect("register payment");
        let conn = Connection::open(&db_path).expect("open");
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, transfer_id, related_debt_id,
                amount_original, amount_original_minor, currency,
                rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category, description
             )
             VALUES (
                99, 'income', '2026-03-05', 1, NULL, NULL,
                10.0, 1000, 'KZT', 1.0, '1',
                10.0, 1000, 'Other', 'Standalone'
             )",
            [],
        )
        .expect("standalone record");
        conn.execute(
            "UPDATE debt_payments SET record_id = 99 WHERE id = ?",
            [payment.id],
        )
        .expect("corrupt backlink");
        drop(conn);

        let error = debt_delete_payment(&db_path, payment.id, true).expect_err("reject");

        assert!(error.contains("does not belong to debt"));
        let conn = Connection::open(&db_path).expect("open");
        let standalone_count: i64 = conn
            .query_row("SELECT COUNT(*) FROM records WHERE id = 99", [], |row| {
                row.get(0)
            })
            .expect("standalone survives");
        let payment_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM debt_payments WHERE id = ?",
                [payment.id],
                |row| row.get(0),
            )
            .expect("payment survives");
        let remaining: i64 = conn
            .query_row(
                "SELECT remaining_amount_minor FROM debts WHERE id = ?",
                [debt.id],
                |row| row.get(0),
            )
            .expect("remaining");
        assert_eq!(standalone_count, 1);
        assert_eq!(payment_count, 1);
        assert_eq!(remaining, 30_000);
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn debt_create_validates_and_links_open_records() {
        let db_path = test_db_path("debt_create_validated");
        init_distribution_schema(&db_path);

        let debt = debt_create(
            &db_path,
            &DebtCreatePayload {
                kind: "debt".to_owned(),
                contact_name: "Alice".to_owned(),
                wallet_id: 1,
                amount: "500.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            },
        )
        .expect("create debt");
        assert_eq!(debt.kind, "debt");
        assert_eq!(debt.total_amount_minor, 50_000);

        let conn = Connection::open(&db_path).expect("open");
        let linked: (String, i64, i64, String) = conn
            .query_row(
                "SELECT type, wallet_id, related_debt_id, category FROM records WHERE related_debt_id = ?",
                [debt.id],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
            )
            .expect("linked record");
        assert_eq!(linked, ("income".to_owned(), 1, debt.id, "Debt".to_owned()));
        drop(conn);

        let loan = debt_create(
            &db_path,
            &DebtCreatePayload {
                kind: "loan".to_owned(),
                contact_name: "Bob".to_owned(),
                wallet_id: 1,
                amount: "100.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-02".to_owned(),
                description: "Loan to Bob".to_owned(),
            },
        )
        .expect("create loan");
        let conn = Connection::open(&db_path).expect("open");
        let linked_type: String = conn
            .query_row(
                "SELECT type FROM records WHERE related_debt_id = ?",
                [loan.id],
                |row| row.get(0),
            )
            .expect("loan record");
        assert_eq!(linked_type, "expense");
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn debt_payment_facade_validates_and_links_rows() {
        let db_path = test_db_path("debt_payment_validated");
        init_distribution_schema(&db_path);
        let debt = debt_create(
            &db_path,
            &DebtCreatePayload {
                kind: "debt".to_owned(),
                contact_name: "Alice".to_owned(),
                wallet_id: 1,
                amount: "500.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            },
        )
        .expect("create debt");

        let payment = debt_register_payment_validated(
            &db_path,
            &DebtPaymentRequestPayload {
                debt_id: debt.id,
                wallet_id: Some(1),
                amount: "200.00".to_owned(),
                payment_date: "2026-03-05".to_owned(),
                description: "cash".to_owned(),
            },
        )
        .expect("payment");
        assert_eq!(payment.operation_type, "debt_repay");
        assert!(!payment.is_write_off);
        assert!(payment.record_id.is_some());
        let conn = Connection::open(&db_path).expect("open");
        assert_eq!(
            conn.query_row(
                "SELECT type, wallet_id, related_debt_id, category FROM records WHERE id = ?",
                [payment.record_id.expect("record")],
                |row| Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                )),
            )
            .expect("linked record"),
            ("expense".to_owned(), 1, debt.id, "Debt payment".to_owned())
        );
        drop(conn);
        assert_eq!(
            debt_from_conn(&Connection::open(&db_path).expect("open"), debt.id)
                .expect("debt")
                .remaining_amount_minor,
            30_000
        );

        let write_off = debt_register_write_off_validated(
            &db_path,
            &DebtPaymentRequestPayload {
                debt_id: debt.id,
                wallet_id: None,
                amount: "300.00".to_owned(),
                payment_date: "2026-03-06".to_owned(),
                description: "".to_owned(),
            },
        )
        .expect("write off");
        assert_eq!(write_off.operation_type, "debt_forgive");
        assert!(write_off.is_write_off);
        assert!(write_off.record_id.is_none());
        let closed = debt_from_conn(&Connection::open(&db_path).expect("open"), debt.id)
            .expect("closed debt");
        assert_eq!(closed.status, "closed");
        assert_eq!(closed.closed_at.as_deref(), Some("2026-03-06"));

        let loan = debt_create(
            &db_path,
            &DebtCreatePayload {
                kind: "loan".to_owned(),
                contact_name: "Bob".to_owned(),
                wallet_id: 1,
                amount: "100.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            },
        )
        .expect("create loan");
        let closed_loan = debt_close_validated(
            &db_path,
            &DebtPaymentRequestPayload {
                debt_id: loan.id,
                wallet_id: Some(1),
                amount: "1.00".to_owned(),
                payment_date: "2026-03-07".to_owned(),
                description: "close".to_owned(),
            },
        )
        .expect("close loan");
        assert_eq!(closed_loan.status, "closed");
        let loan_payment = debt_payment_rows(&db_path, Some(loan.id))
            .expect("loan payments")
            .into_iter()
            .next()
            .expect("loan payment");
        assert_eq!(loan_payment.operation_type, "loan_collect");

        fs::remove_file(db_path).ok();
    }

    #[test]
    fn debt_payment_facade_rejects_invalid_inputs() {
        let db_path = test_db_path("debt_payment_invalid");
        init_distribution_schema(&db_path);
        let debt = debt_create(
            &db_path,
            &DebtCreatePayload {
                kind: "debt".to_owned(),
                contact_name: "Alice".to_owned(),
                wallet_id: 1,
                amount: "200.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            },
        )
        .expect("create debt");
        let request =
            |amount: &str, wallet_id: Option<i64>, date: &str| DebtPaymentRequestPayload {
                debt_id: debt.id,
                wallet_id,
                amount: amount.to_owned(),
                payment_date: date.to_owned(),
                description: "".to_owned(),
            };
        assert!(
            debt_register_payment_validated(&db_path, &request("0", Some(1), "2026-03-05"))
                .expect_err("zero")
                .contains("positive")
        );
        assert!(
            debt_register_payment_validated(&db_path, &request("300.00", Some(1), "2026-03-05"))
                .expect_err("too much")
                .contains("exceeds")
        );
        assert!(
            debt_register_payment(
                &db_path,
                debt.id,
                &test_payment(debt.id, 30_000, false),
                None
            )
            .expect_err("raw too much")
            .contains("exceeds")
        );
        assert!(
            debt_register_payment(
                &db_path,
                debt.id,
                &test_payment(debt.id + 1, 1_000, false),
                None
            )
            .expect_err("raw mismatch")
            .contains("does not match")
        );
        assert!(
            debt_register_payment_validated(&db_path, &request("1.00", Some(1), "2999-01-01"))
                .expect_err("future")
                .contains("future")
        );
        assert!(
            debt_register_payment_validated(&db_path, &request("1.00", None, "2026-03-05"))
                .expect_err("wallet required")
                .contains("Wallet is required")
        );
        assert!(
            debt_register_payment_validated(&db_path, &request("1.00", Some(3), "2026-03-05"))
                .expect_err("inactive")
                .contains("inactive")
        );
        let conn = Connection::open(&db_path).expect("open");
        conn.execute(
            "INSERT INTO records (
                type, date, wallet_id, amount_original, amount_original_minor,
                currency, rate_at_operation, rate_at_operation_text,
                amount_base, amount_base_minor, category
             ) VALUES ('expense', '2026-03-02', 1, 1199.0, 119900, 'KZT', 1.0, '1', 1199.0, 119900, 'Drain')",
            [],
        )
        .expect("drain");
        drop(conn);
        assert!(
            debt_register_payment_validated(&db_path, &request("2.00", Some(1), "2026-03-05"))
                .expect_err("insufficient")
                .contains("Insufficient funds")
        );
        debt_register_write_off_validated(
            &db_path,
            &DebtPaymentRequestPayload {
                debt_id: debt.id,
                wallet_id: None,
                amount: "200.00".to_owned(),
                payment_date: "2026-03-06".to_owned(),
                description: "".to_owned(),
            },
        )
        .expect("close");
        assert!(
            debt_register_write_off_validated(
                &db_path,
                &DebtPaymentRequestPayload {
                    debt_id: debt.id,
                    wallet_id: None,
                    amount: "1.00".to_owned(),
                    payment_date: "2026-03-07".to_owned(),
                    description: "".to_owned(),
                },
            )
            .expect_err("closed")
            .contains("already closed")
        );

        fs::remove_file(db_path).ok();
    }

    #[test]
    fn debt_create_rejects_invalid_inputs() {
        let db_path = test_db_path("debt_create_invalid");
        init_distribution_schema(&db_path);
        let request = |kind: &str,
                       contact_name: &str,
                       wallet_id: i64,
                       amount: &str,
                       currency: &str,
                       created_at: &str| {
            DebtCreatePayload {
                kind: kind.to_owned(),
                contact_name: contact_name.to_owned(),
                wallet_id,
                amount: amount.to_owned(),
                currency: currency.to_owned(),
                created_at: created_at.to_owned(),
                description: "".to_owned(),
            }
        };
        assert!(
            debt_create(&db_path, &request("debt", "", 1, "10", "KZT", "2026-03-01"))
                .expect_err("blank contact")
                .contains("Contact name")
        );
        assert!(
            debt_create(&db_path, &request("debt", "A", 1, "0", "KZT", "2026-03-01"))
                .expect_err("zero amount")
                .contains("positive")
        );
        assert!(
            debt_create(
                &db_path,
                &request("debt", "A", 1, "10", "USD", "2026-03-01")
            )
            .expect_err("currency")
            .contains("base-currency")
        );
        assert!(
            debt_create(
                &db_path,
                &request("debt", "A", 3, "10", "KZT", "2026-03-01")
            )
            .expect_err("inactive")
            .contains("inactive")
        );
        assert!(
            debt_create(
                &db_path,
                &request("loan", "A", 1, "2000", "KZT", "2026-03-01")
            )
            .expect_err("insufficient")
            .contains("Insufficient funds")
        );
        assert!(
            debt_create(
                &db_path,
                &request("debt", "A", 1, "10", "KZT", "9999-01-01")
            )
            .expect_err("future")
            .contains("future")
        );
        fs::remove_file(db_path).ok();
    }
}
