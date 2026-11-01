use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::Path;

use ledgera_engine_core::minor_to_money_value;
use printpdf::{
    Color, Mm, Op, PaintMode, ParsedFont, PdfDocument, PdfFontHandle, PdfPage, PdfSaveOptions,
    Point, Pt, Rect, Rgb, TextItem,
};
use rusqlite::Connection;
use rust_xlsxwriter::{Format, FormatAlign, FormatBorder, FormatPattern, Workbook, Worksheet};

use crate::{
    RecordRow, StorageResult, base_currency_code, current_local_date, record_list_rows, round_money,
    sqlite_err, table_columns_for_connection, with_cached_read_connection,
};

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ReportFilters {
    pub wallet_id: Option<i64>,
    pub period_start: Option<String>,
    pub period_end: Option<String>,
    pub category: String,
    pub tag: String,
    pub tag_mode: String,
    pub totals_mode: String,
    pub group_by_category: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportSummary {
    pub net_worth_fixed: f64,
    pub net_worth_current: f64,
    pub initial_balance: f64,
    pub records_total_fixed: f64,
    pub records_total_current: f64,
    pub final_balance_fixed: f64,
    pub final_balance_current: f64,
    pub fx_difference: f64,
    pub records_count: i64,
    pub transfers_count: i64,
    pub transfer_net_fixed: f64,
    pub transfer_net_current: f64,
    pub balance_label: String,
    pub active_tag: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportOperationRow {
    pub date: String,
    pub type_label: String,
    pub kind: String,
    pub category: String,
    pub tags_text: String,
    pub amount_base: f64,
    pub amount_current: f64,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportMonthlyRow {
    pub month: String,
    pub income: f64,
    pub expenses: f64,
    pub income_current: f64,
    pub expenses_current: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportCategoryRow {
    pub category: String,
    pub operations_count: i64,
    pub total_base: f64,
    pub total_current: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportTagRow {
    pub tag: String,
    pub operations_count: i64,
    pub total_base: f64,
    pub total_current: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportDebtRow {
    pub contact_name: String,
    pub kind: String,
    pub status: String,
    pub created_at: String,
    pub closed_at: Option<String>,
    pub currency: String,
    pub total_amount: f64,
    pub remaining_amount: f64,
    pub settled_amount: f64,
    pub progress_percent: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportResult {
    pub title: String,
    pub base_currency: String,
    pub display_currency: String,
    pub filters: ReportFilters,
    pub summary: ReportSummary,
    pub operations: Vec<ReportOperationRow>,
    pub transfers: Vec<ReportTransferRow>,
    pub monthly: Vec<ReportMonthlyRow>,
    pub categories: Vec<ReportCategoryRow>,
    pub tags: Vec<ReportTagRow>,
    pub debts: Vec<ReportDebtRow>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportExportResult {
    pub exported_rows: i64,
    pub path: String,
}

fn normalized_optional(value: &Option<String>) -> Option<String> {
    value
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_owned)
}

fn date_today_text() -> String {
    let (year, month, day) = current_local_date();
    format!("{year:04}-{month:02}-{day:02}")
}

fn signed_amount(record: &RecordRow) -> f64 {
    if record.record_type == "income" {
        record.amount_base
    } else {
        -record.amount_base
    }
}

fn current_amount(
    record: &RecordRow,
    rates: &std::collections::HashMap<String, f64>,
    base: &str,
) -> StorageResult<f64> {
    if record.currency.eq_ignore_ascii_case(base) {
        return Ok(record.amount_original);
    }
    let rate = rates.get(&record.currency).copied().ok_or_else(|| {
        format!(
            "Current report rate is unavailable for currency {}",
            record.currency
        )
    })?;
    Ok(record.amount_original * rate)
}

fn load_cached_rates(db_path: &str) -> StorageResult<std::collections::HashMap<String, f64>> {
    crate::current_currency_rates(db_path)
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportTransferRow {
    pub transfer_id: i64,
    pub date: String,
    pub from_wallet_id: i64,
    pub from_wallet_name: String,
    pub to_wallet_id: i64,
    pub to_wallet_name: String,
    pub source_amount: f64,
    pub source_currency: String,
    pub target_amount: f64,
    pub target_currency: String,
    pub historical_rate: String,
    pub source_amount_base: f64,
    pub target_amount_base: f64,
    pub source_amount_current: f64,
    pub target_amount_current: f64,
    pub commission_amount: f64,
    pub commission_currency: String,
    pub commission_amount_base: f64,
    pub commission_amount_current: f64,
    pub tags_text: String,
    pub description: String,
    pub integrity_status: String,
    pub integrity_message: String,
}

#[derive(Debug, Clone)]
struct TransferReportSource {
    id: i64,
    from_wallet_id: i64,
    to_wallet_id: i64,
    date: String,
    amount_original: f64,
    currency: String,
    amount_base: f64,
    source_amount: Option<f64>,
    source_currency: Option<String>,
    target_amount: Option<f64>,
    target_currency: Option<String>,
    conversion_rate: Option<String>,
    description: String,
}

fn transfer_report_sources(db_path: &str) -> StorageResult<Vec<TransferReportSource>> {
    with_cached_read_connection(db_path, |conn| {
        let columns = table_columns_for_connection(conn, "transfers")?;
        let optional_column = |name: &str| {
            if columns.iter().any(|column| column == name) {
                name.to_owned()
            } else {
                "NULL".to_owned()
            }
        };
        let mut stmt = conn
            .prepare(&format!(
                "SELECT id, from_wallet_id, to_wallet_id, date,
                        amount_original, currency, amount_base,
                        {source_amount} AS source_amount_original,
                        {source_currency} AS source_currency,
                        {target_amount} AS target_amount_original,
                        {target_currency} AS target_currency,
                        {conversion_rate} AS conversion_rate_text,
                        description
                 FROM transfers ORDER BY id",
                source_amount = optional_column("source_amount_original"),
                source_currency = optional_column("source_currency"),
                target_amount = optional_column("target_amount_original"),
                target_currency = optional_column("target_currency"),
                conversion_rate = optional_column("conversion_rate_text"),
            ))
            .map_err(sqlite_err)?;
        let rows = stmt
            .query_map([], |row| {
                Ok(TransferReportSource {
                    id: row.get(0)?,
                    from_wallet_id: row.get(1)?,
                    to_wallet_id: row.get(2)?,
                    date: row.get(3)?,
                    amount_original: row.get(4)?,
                    currency: row.get(5)?,
                    amount_base: row.get(6)?,
                    source_amount: row.get(7)?,
                    source_currency: row.get(8)?,
                    target_amount: row.get(9)?,
                    target_currency: row.get(10)?,
                    conversion_rate: row.get(11)?,
                    description: row.get(12)?,
                })
            })
            .map_err(sqlite_err)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_err)
    })
}

fn report_transfer_tags(records: &[&RecordRow]) -> Vec<String> {
    let mut tags = BTreeMap::<String, String>::new();
    for record in records {
        for tag in &record.tags {
            let normalized = tag.trim().to_lowercase();
            if !normalized.is_empty() {
                tags.entry(normalized).or_insert_with(|| tag.trim().to_owned());
            }
        }
    }
    tags.into_values().collect()
}

fn report_transfer_current_amount(
    amount: f64,
    currency: &str,
    rates: &HashMap<String, f64>,
    base: &str,
) -> StorageResult<f64> {
    if currency.eq_ignore_ascii_case(base) {
        return Ok(amount);
    }
    let rate = rates.get(&currency.to_uppercase()).copied().ok_or_else(|| {
        format!(
            "Current report rate is unavailable for currency {}",
            currency
        )
    })?;
    Ok(amount * rate)
}

fn build_report_transfers(
    db_path: &str,
    filters: &ReportFilters,
    all_records: &[RecordRow],
    rates: &HashMap<String, f64>,
    base_currency: &str,
) -> StorageResult<(Vec<ReportTransferRow>, f64, f64, f64)> {
    let wallets = crate::wallet_list_rows(db_path)?
        .into_iter()
        .map(|wallet| (wallet.id, wallet.name))
        .collect::<HashMap<_, _>>();
    let mut linked_by_transfer: HashMap<i64, Vec<&RecordRow>> = HashMap::new();
    let mut commissions_by_transfer: HashMap<i64, Vec<&RecordRow>> = HashMap::new();
    for record in all_records {
        if let Some(transfer_id) = record.transfer_id {
            linked_by_transfer.entry(transfer_id).or_default().push(record);
        } else if record.category.eq_ignore_ascii_case("commission") {
            if let Some(id) = record
                .description
                .strip_prefix("[transfer:")
                .and_then(|value| value.strip_suffix(']'))
                .and_then(|value| value.parse::<i64>().ok())
            {
                commissions_by_transfer.entry(id).or_default().push(record);
            }
        }
    }

    let start = filters.period_start.as_deref();
    let end = filters.period_end.as_deref();
    let use_current = filters.totals_mode.eq_ignore_ascii_case("current");
    let mut rows = Vec::new();
    let mut period_net_fixed = 0.0;
    let mut period_net_current = 0.0;
    let mut opening_net_fixed = 0.0;

    for transfer in transfer_report_sources(db_path)? {
        let linked = linked_by_transfer.get(&transfer.id).cloned().unwrap_or_default();
        let tags = report_transfer_tags(&linked);
        if !filters.category.trim().is_empty()
            && !"Transfer".eq_ignore_ascii_case(filters.category.trim())
        {
            continue;
        }
        if !tag_matches(&tags, &filters.tag, &filters.tag_mode) {
            continue;
        }
        if start.is_some_and(|value| transfer.date.as_str() < value)
            || end.is_some_and(|value| transfer.date.as_str() > value)
        {
            if start.is_some_and(|value| transfer.date.as_str() < value) {
                if filters.wallet_id.is_none() {
                    continue;
                }
                let has_wallet = linked.iter().any(|record| {
                    Some(record.wallet_id) == filters.wallet_id
                }) || transfer.from_wallet_id == filters.wallet_id.unwrap_or_default()
                    || transfer.to_wallet_id == filters.wallet_id.unwrap_or_default();
                if !has_wallet {
                    continue;
                }
                let source = linked.iter().find(|record| {
                    record.wallet_id == transfer.from_wallet_id && record.record_type == "expense"
                });
                let target = linked.iter().find(|record| {
                    record.wallet_id == transfer.to_wallet_id && record.record_type == "income"
                });
                if let (Some(source), Some(target)) = (source, target) {
                    opening_net_fixed += if filters.wallet_id == Some(transfer.from_wallet_id) {
                        -source.amount_base
                    } else if filters.wallet_id == Some(transfer.to_wallet_id) {
                        target.amount_base
                    } else {
                        0.0
                    };
                }
            }
            continue;
        }
        if filters
            .wallet_id
            .is_some_and(|wallet_id| wallet_id != transfer.from_wallet_id && wallet_id != transfer.to_wallet_id)
        {
            continue;
        }

        let source = linked.iter().find(|record| {
            record.wallet_id == transfer.from_wallet_id && record.record_type == "expense"
        });
        let target = linked.iter().find(|record| {
            record.wallet_id == transfer.to_wallet_id && record.record_type == "income"
        });
        let commissions = commissions_by_transfer.get(&transfer.id).cloned().unwrap_or_default();
        let commission = commissions.first().copied();
        let mut errors = Vec::new();
        if source.is_none() {
            errors.push("source leg is missing".to_owned());
        }
        if target.is_none() {
            errors.push("target leg is missing".to_owned());
        }
        if linked.iter().filter(|record| record.record_type == "expense").count() != 1 {
            errors.push("expected exactly one source leg".to_owned());
        }
        if linked.iter().filter(|record| record.record_type == "income").count() != 1 {
            errors.push("expected exactly one target leg".to_owned());
        }
        if commissions.len() > 1 {
            errors.push("multiple commission records found".to_owned());
        }

        let source_amount = source
            .map(|record| record.amount_original)
            .or(transfer.source_amount)
            .unwrap_or(transfer.amount_original);
        let target_amount = target
            .map(|record| record.amount_original)
            .or(transfer.target_amount)
            .unwrap_or(transfer.amount_original);
        let source_currency = source
            .map(|record| record.currency.clone())
            .or(transfer.source_currency.clone())
            .unwrap_or_else(|| transfer.currency.clone());
        let target_currency = target
            .map(|record| record.currency.clone())
            .or(transfer.target_currency.clone())
            .unwrap_or_else(|| source_currency.clone());
        let source_base = source
            .map(|record| record.amount_base)
            .unwrap_or(transfer.amount_base);
        let target_base = target
            .map(|record| record.amount_base)
            .unwrap_or(transfer.amount_base);
        if source.is_none() && transfer.source_amount.is_none() {
            errors.push("source amount is unavailable".to_owned());
        }
        if target.is_none() && transfer.target_amount.is_none() {
            errors.push("target amount is unavailable".to_owned());
        }
        let source_current = if use_current {
            report_transfer_current_amount(source_amount, &source_currency, rates, base_currency)?
        } else {
            source_base
        };
        let target_current = if use_current {
            report_transfer_current_amount(target_amount, &target_currency, rates, base_currency)?
        } else {
            target_base
        };
        let commission_amount = commission.map(|record| record.amount_original).unwrap_or(0.0);
        let commission_currency = commission
            .map(|record| record.currency.clone())
            .unwrap_or_default();
        let commission_base = commission.map(|record| record.amount_base).unwrap_or(0.0);
        let commission_current = if use_current && commission.is_some() {
            report_transfer_current_amount(
                commission_amount,
                &commission_currency,
                rates,
                base_currency,
            )?
        } else {
            commission_base
        };
        let valid = errors.is_empty();
        let wallet_net_fixed = if valid {
            match filters.wallet_id {
                Some(wallet_id) if wallet_id == transfer.from_wallet_id => -source_base,
                Some(wallet_id) if wallet_id == transfer.to_wallet_id => target_base,
                _ => 0.0,
            }
        } else {
            0.0
        };
        let wallet_net_current = if valid {
            match filters.wallet_id {
                Some(wallet_id) if wallet_id == transfer.from_wallet_id => -source_current,
                Some(wallet_id) if wallet_id == transfer.to_wallet_id => target_current,
                _ => 0.0,
            }
        } else {
            0.0
        };
        period_net_fixed += wallet_net_fixed;
        period_net_current += wallet_net_current;
        rows.push(ReportTransferRow {
            transfer_id: transfer.id,
            date: transfer.date,
            from_wallet_id: transfer.from_wallet_id,
            from_wallet_name: wallets.get(&transfer.from_wallet_id).cloned().unwrap_or_else(|| format!("Wallet #{}", transfer.from_wallet_id)),
            to_wallet_id: transfer.to_wallet_id,
            to_wallet_name: wallets.get(&transfer.to_wallet_id).cloned().unwrap_or_else(|| format!("Wallet #{}", transfer.to_wallet_id)),
            source_amount,
            source_currency,
            target_amount,
            target_currency,
            historical_rate: transfer.conversion_rate.unwrap_or_else(|| "1".to_owned()),
            source_amount_base: source_base,
            target_amount_base: target_base,
            source_amount_current: source_current,
            target_amount_current: target_current,
            commission_amount,
            commission_currency,
            commission_amount_base: commission_base,
            commission_amount_current: commission_current,
            tags_text: tags.join(" "),
            description: transfer.description,
            integrity_status: if valid { "ok".to_owned() } else { "error".to_owned() },
            integrity_message: errors.join("; "),
        });
    }
    rows.sort_by(|left, right| right.date.cmp(&left.date).then_with(|| right.transfer_id.cmp(&left.transfer_id)));
    Ok((rows, period_net_fixed, period_net_current, opening_net_fixed))
}

fn tags_for_records(
    conn: &Connection,
    ids: &[i64],
) -> StorageResult<std::collections::HashMap<i64, Vec<String>>> {
    let mut result = std::collections::HashMap::new();
    for id in ids {
        let mut stmt = conn.prepare(
            "SELECT t.name FROM record_tags rt JOIN tags t ON t.id = rt.tag_id WHERE rt.record_id = ?1 ORDER BY t.name COLLATE NOCASE, t.name",
        ).map_err(sqlite_err)?;
        let rows = stmt
            .query_map([id], |row| row.get::<_, String>(0))
            .map_err(sqlite_err)?;
        let mut tags = Vec::new();
        for row in rows {
            tags.push(row.map_err(sqlite_err)?);
        }
        result.insert(*id, tags);
    }
    Ok(result)
}

fn tag_matches(tags: &[String], raw_filter: &str, mode: &str) -> bool {
    if raw_filter.trim().is_empty() {
        return true;
    }
    let wanted: Vec<String> = raw_filter
        .replace('|', ",")
        .split(',')
        .map(|v| v.trim().to_lowercase())
        .filter(|v| !v.is_empty())
        .collect();
    if wanted.is_empty() {
        return true;
    }
    let actual: Vec<String> = tags.iter().map(|v| v.trim().to_lowercase()).collect();
    if mode.eq_ignore_ascii_case("and") {
        wanted.iter().all(|v| actual.contains(v))
    } else {
        wanted.iter().any(|v| actual.contains(v))
    }
}

fn month_key(date: &str) -> Option<String> {
    if date.len() >= 7 && date.as_bytes().get(4) == Some(&b'-') {
        Some(date[..7].to_owned())
    } else {
        None
    }
}

fn debt_rows_for_period(
    conn: &Connection,
    start: &str,
    end: &str,
    wallet_id: Option<i64>,
) -> StorageResult<Vec<ReportDebtRow>> {
    let mut stmt = conn.prepare(
        "SELECT contact_name, kind, status, created_at, closed_at, currency, total_amount_minor, remaining_amount_minor FROM debts WHERE created_at <= ?2 AND (closed_at IS NULL OR closed_at >= ?1) AND (?3 IS NULL OR EXISTS (SELECT 1 FROM records WHERE records.related_debt_id = debts.id AND records.wallet_id = ?3)) ORDER BY created_at, id",
    ).map_err(sqlite_err)?;
    let rows = stmt
        .query_map((start, end, wallet_id), |row| {
            let total: i64 = row.get(6)?;
            let remaining: i64 = row.get(7)?;
            let total_f = minor_to_money_value(total);
            let remaining_f = minor_to_money_value(remaining);
            let settled = (total_f - remaining_f).max(0.0);
            Ok(ReportDebtRow {
                contact_name: row.get(0)?,
                kind: row.get(1)?,
                status: row.get(2)?,
                created_at: row.get(3)?,
                closed_at: row.get(4)?,
                currency: row.get(5)?,
                total_amount: total_f,
                remaining_amount: remaining_f,
                settled_amount: settled,
                progress_percent: if total_f > 0.0 {
                    round_money(settled / total_f * 100.0)
                } else {
                    0.0
                },
            })
        })
        .map_err(sqlite_err)?;
    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(sqlite_err)?);
    }
    Ok(result)
}

pub fn report_generate(db_path: &str, filters: &ReportFilters) -> StorageResult<ReportResult> {
    let mut normalized = filters.clone();
    normalized.period_start = normalized_optional(&filters.period_start);
    normalized.period_end = normalized_optional(&filters.period_end);
    if normalized.period_end.is_some() && normalized.period_start.is_none() {
        return Err("Report end date requires a start date".to_owned());
    }
    if normalized.period_start.is_some() && normalized.period_end.is_none() {
        normalized.period_end = Some(date_today_text());
    }
    if let (Some(start), Some(end)) = (&normalized.period_start, &normalized.period_end) {
        crate::validate_ymd_date(start)?;
        crate::validate_ymd_date(end)?;
        if end < start {
            return Err("Report end date cannot be before start date".to_owned());
        }
        if end.as_str() > date_today_text().as_str() {
            return Err("Report dates cannot be in the future".to_owned());
        }
    }

    let base_currency = base_currency_code(db_path)?;
    let all_records = record_list_rows(db_path)?;
    let ids: Vec<i64> = all_records
        .iter()
        .filter(|r| r.transfer_id.is_none())
        .map(|r| r.id)
        .collect();
    let raw_tags = with_cached_read_connection(db_path, |conn| tags_for_records(conn, &ids))?;
    let start = normalized.period_start.as_deref();
    let end = normalized.period_end.as_deref();
    let mut period_records = Vec::new();
    let mut opening_balance = 0.0;
    let wallet_initial = with_cached_read_connection(db_path, |conn| {
        if let Some(wallet_id) = normalized.wallet_id {
            conn.query_row("SELECT COALESCE(initial_balance_minor, ROUND(initial_balance * 100.0), 0) FROM wallets WHERE id = ?1", [wallet_id], |row| row.get::<_, i64>(0))
                .map(minor_to_money_value).map_err(sqlite_err)
        } else {
            conn.query_row("SELECT COALESCE(SUM(COALESCE(initial_balance_minor, ROUND(initial_balance * 100.0), 0)), 0) FROM wallets WHERE is_active = 1", [], |row| row.get::<_, i64>(0))
                .map(minor_to_money_value).map_err(sqlite_err)
        }
    })?;
    for record in all_records.iter().filter(|r| r.transfer_id.is_none()) {
        if normalized
            .wallet_id
            .is_some_and(|id| record.wallet_id != id)
        {
            continue;
        }
        if let Some(start_date) = start {
            if record.date.as_str() < start_date {
                opening_balance += signed_amount(record);
                continue;
            }
        }
        if let Some(start_date) = start {
            if record.date.as_str() < start_date {
                continue;
            }
        }
        if let Some(end_date) = end {
            if record.date.as_str() > end_date {
                continue;
            }
        }
        let tags = raw_tags.get(&record.id).cloned().unwrap_or_default();
        if !normalized.category.trim().is_empty()
            && !record
                .category
                .eq_ignore_ascii_case(normalized.category.trim())
        {
            continue;
        }
        if !tag_matches(&tags, &normalized.tag, &normalized.tag_mode) {
            continue;
        }
        period_records.push((record, tags));
    }
    period_records.sort_by(|left, right| {
        right
            .0
            .date
            .cmp(&left.0.date)
            .then_with(|| right.0.id.cmp(&left.0.id))
    });
    let rates = if normalized.totals_mode.eq_ignore_ascii_case("current") {
        load_cached_rates(db_path)?
    } else {
        std::collections::HashMap::new()
    };
    let mut fixed_total = 0.0;
    let mut current_total = 0.0;
    let mut operations = Vec::new();
    let mut category_totals: BTreeMap<String, (i64, f64, f64)> = BTreeMap::new();
    let mut tag_totals: BTreeMap<String, (i64, f64, f64)> = BTreeMap::new();
    let mut monthly: BTreeMap<String, (f64, f64, f64, f64)> = BTreeMap::new();
    for (record, tags) in &period_records {
        let fixed = signed_amount(record);
        let current = if normalized.totals_mode.eq_ignore_ascii_case("current") {
            let amount = current_amount(record, &rates, &base_currency)?;
            if record.record_type == "income" {
                amount
            } else {
                -amount
            }
        } else {
            fixed
        };
        fixed_total += fixed;
        current_total += current;
        let type_label = match record.record_type.as_str() {
            "income" => "Income",
            "mandatory_expense" => "Mandatory Expense",
            _ => "Expense",
        };
        let kind = match record.record_type.as_str() {
            "income" => "income",
            "mandatory_expense" => "mandatory",
            _ => "expense",
        };
        operations.push(ReportOperationRow {
            date: record.date.clone(),
            type_label: type_label.to_owned(),
            kind: kind.to_owned(),
            category: record.category.clone(),
            tags_text: tags.join(" "),
            amount_base: fixed,
            amount_current: current,
            description: record.description.clone(),
        });
        let entry = category_totals.entry(record.category.clone()).or_default();
        entry.0 += 1;
        entry.1 += fixed;
        entry.2 += current;
        for tag in tags {
            let entry = tag_totals.entry(tag.clone()).or_default();
            entry.0 += 1;
            entry.1 += fixed;
            entry.2 += current;
        }
        if let Some(month) = month_key(&record.date) {
            let entry = monthly.entry(month).or_default();
            if record.record_type == "income" {
                entry.0 += record.amount_base;
                entry.2 += current;
            } else {
                entry.1 += record.amount_base;
                entry.3 += -current;
            }
        }
    }
    let (transfers, transfer_net_fixed, transfer_net_current, transfer_opening_fixed) =
        build_report_transfers(db_path, &normalized, &all_records, &rates, &base_currency)?;
    let initial = wallet_initial + opening_balance + transfer_opening_fixed;
    let final_fixed = initial + fixed_total + transfer_net_fixed;
    let final_current = initial + current_total + transfer_net_current;
    let summary = ReportSummary {
        net_worth_fixed: final_fixed,
        net_worth_current: final_current,
        initial_balance: initial,
        records_total_fixed: fixed_total,
        records_total_current: current_total,
        final_balance_fixed: final_fixed,
        final_balance_current: final_current,
        fx_difference: (current_total - fixed_total)
            + (transfer_net_current - transfer_net_fixed),
        records_count: operations.len() as i64,
        transfers_count: transfers.len() as i64,
        transfer_net_fixed,
        transfer_net_current,
        balance_label: if start.is_some() {
            "Opening balance".to_owned()
        } else {
            "Initial balance".to_owned()
        },
        active_tag: normalized.tag.clone(),
    };
    let monthly = monthly
        .into_iter()
        .map(
            |(month, (income, expenses, income_current, expenses_current))| ReportMonthlyRow {
                month,
                income,
                expenses,
                income_current,
                expenses_current,
            },
        )
        .collect();
    let categories = category_totals
        .into_iter()
        .map(
            |(category, (count, total, total_current))| ReportCategoryRow {
                category,
                operations_count: count,
                total_base: total,
                total_current,
            },
        )
        .collect();
    let tags = tag_totals
        .into_iter()
        .map(|(tag, (count, total, total_current))| ReportTagRow {
            tag,
            operations_count: count,
            total_base: total,
            total_current,
        })
        .collect();
    let debts = with_cached_read_connection(db_path, |conn| {
        debt_rows_for_period(
            conn,
            start.unwrap_or("0000-01-01"),
            end.unwrap_or("9999-12-31"),
            normalized.wallet_id,
        )
    })?;
    let include_categories = normalized.group_by_category;
    let title = match (start, end) {
        (Some(a), Some(b)) => format!("Transaction statement ({a} - {b})"),
        _ => "Transaction statement".to_owned(),
    };
    Ok(ReportResult {
        title,
        base_currency: base_currency.clone(),
        display_currency: base_currency,
        filters: normalized,
        summary,
        operations,
        transfers,
        monthly,
        categories: if include_categories {
            categories
        } else {
            Vec::new()
        },
        tags,
        debts,
    })
}

fn atomic_replace(path: &Path, bytes: &[u8]) -> StorageResult<()> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| "Export path must include a file name".to_owned())?;
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_nanos();
    let temp = parent.join(format!(".{file_name}.{unique}.tmp"));
    if let Err(error) = fs::write(&temp, bytes) {
        let _ = fs::remove_file(&temp);
        return Err(format!("Failed to write report export: {error}"));
    }
    if let Err(error) = crate::replace_export_file(&temp, path) {
        let _ = fs::remove_file(&temp);
        return Err(format!("Failed to finalize report export: {error}"));
    }
    Ok(())
}

fn csv_transfer_section(
    writer: &mut csv::Writer<Vec<u8>>,
    report: &ReportResult,
    use_current: bool,
) -> StorageResult<()> {
    if report.transfers.is_empty() {
        return Ok(());
    }
    write_report_csv_row(writer, &["", "Transfers"], 13)?;
    writer
        .write_record([
            "Date",
            "Transfer ID",
            "From wallet",
            "Source amount",
            "To wallet",
            "Target amount",
            "Historical rate",
            "Commission",
            "Base source",
            "Base target",
            "Status",
            "Description",
            "Tags",
        ])
        .map_err(|err| err.to_string())?;
    for row in &report.transfers {
        let source_base = if use_current {
            row.source_amount_current
        } else {
            row.source_amount_base
        };
        let target_base = if use_current {
            row.target_amount_current
        } else {
            row.target_amount_base
        };
        let commission = if row.commission_amount > 0.0 {
            format!("{:.2} {}", row.commission_amount, row.commission_currency)
        } else {
            "-".to_owned()
        };
        writer
            .write_record([
                row.date.as_str(),
                &row.transfer_id.to_string(),
                &format!("{} (#{})", row.from_wallet_name, row.from_wallet_id),
                &format!("{:.2} {}", row.source_amount, row.source_currency),
                &format!("{} (#{})", row.to_wallet_name, row.to_wallet_id),
                &format!("{:.2} {}", row.target_amount, row.target_currency),
                row.historical_rate.as_str(),
                commission.as_str(),
                &format!("{source_base:.2}"),
                &format!("{target_base:.2}"),
                if row.integrity_status == "ok" {
                    "OK"
                } else {
                    row.integrity_status.as_str()
                },
                row.description.as_str(),
                row.tags_text.as_str(),
            ])
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn write_report_csv_row(
    writer: &mut csv::Writer<Vec<u8>>,
    values: &[&str],
    width: usize,
) -> StorageResult<()> {
    let mut row = values.to_vec();
    row.resize(width, "");
    writer.write_record(row).map_err(|err| err.to_string())
}

pub fn report_export_csv(
    db_path: &str,
    filters: &ReportFilters,
    path: &str,
) -> StorageResult<ReportExportResult> {
    let report = report_generate(db_path, filters)?;
    let use_current = report.filters.totals_mode.eq_ignore_ascii_case("current");
    if report.filters.group_by_category {
        let mut writer = csv::Writer::from_writer(Vec::new());
        let csv_width = if report.transfers.is_empty() { 3 } else { 13 };
        write_report_csv_row(&mut writer, &[report.title.as_str(), "", ""], csv_width)?;
        write_report_csv_row(
            &mut writer,
            &[
                "Category",
                "Operations",
                &format!("Amount ({})", report.base_currency),
            ],
            csv_width,
        )?;
        write_report_csv_row(
            &mut writer,
            &["", "", &report_amounts_note(&report.filters.totals_mode)],
            csv_width,
        )?;
        let mut total = 0.0;
        for row in &report.categories {
            let amount = if use_current {
                row.total_current
            } else {
                row.total_base
            };
            total += amount;
            write_report_csv_row(
                &mut writer,
                &[
                    row.category.as_str(),
                    &row.operations_count.to_string(),
                    &format!("{amount:.2}"),
                ],
                csv_width,
            )?;
        }
        write_report_csv_row(
            &mut writer,
            &["Total", "", &format!("{total:.2}")],
            csv_width,
        )?;
        csv_transfer_section(&mut writer, &report, use_current)?;
        let bytes = writer.into_inner().map_err(|err| err.to_string())?;
        atomic_replace(Path::new(path), &bytes)?;
        return Ok(ReportExportResult {
            exported_rows: (report.categories.len() + report.transfers.len()) as i64,
            path: path.to_owned(),
        });
    }
    let mut writer = csv::Writer::from_writer(Vec::new());
    let csv_width = if report.transfers.is_empty() { 5 } else { 13 };
    write_report_csv_row(
        &mut writer,
        &[report.title.as_str(), "", "", "", ""],
        csv_width,
    )?;
    write_report_csv_row(
        &mut writer,
        &[
            "Date",
            "Type",
            "Category",
            &format!("Amount ({})", report.base_currency),
            "Tags",
        ],
        csv_width,
    )?;
    write_report_csv_row(
        &mut writer,
        &[
            "",
            "",
            "",
            &report_amounts_note(&report.filters.totals_mode),
            "",
        ],
        csv_width,
    )?;
    write_report_csv_row(
        &mut writer,
        &[
            "",
            report.summary.balance_label.as_str(),
            "",
            &format!("{:.2}", report.summary.initial_balance),
            "",
        ],
        csv_width,
    )?;
    for row in &report.operations {
        write_report_csv_row(
            &mut writer,
            &[
                row.date.as_str(),
                row.type_label.as_str(),
                row.category.as_str(),
                &format!(
                    "{:.2}",
                    if use_current {
                        row.amount_current
                    } else {
                        row.amount_base
                    }
                ),
                row.tags_text.as_str(),
            ],
            csv_width,
        )?;
    }
    write_report_csv_row(
        &mut writer,
        &[
            "",
            "Subtotal",
            "",
            &format!(
                "{:.2}",
                if use_current {
                    report.summary.records_total_current
                } else {
                    report.summary.records_total_fixed
                }
            ),
            "",
        ],
        csv_width,
    )?;
    write_report_csv_row(
        &mut writer,
        &[
            "",
            "Final balance",
            "",
            &format!(
                "{:.2}",
                if use_current {
                    report.summary.final_balance_current
                } else {
                    report.summary.final_balance_fixed
                }
            ),
            "",
        ],
        csv_width,
    )?;
    csv_transfer_section(&mut writer, &report, use_current)?;
    let bytes = writer.into_inner().map_err(|err| err.to_string())?;
    atomic_replace(Path::new(path), &bytes)?;
    Ok(ReportExportResult {
        exported_rows: (report.operations.len() + report.transfers.len()) as i64,
        path: path.to_owned(),
    })
}

pub fn report_export_xlsx(
    db_path: &str,
    filters: &ReportFilters,
    path: &str,
) -> StorageResult<ReportExportResult> {
    let report = report_generate(db_path, filters)?;
    let use_current = report.filters.totals_mode.eq_ignore_ascii_case("current");
    if report.filters.group_by_category {
        return report_export_grouped_xlsx(&report, path, use_current);
    }
    let mut workbook = Workbook::new();
    let header = report_header_format();
    let data = report_data_format();
    let amount = report_amount_format();
    let subtotal = report_subtotal_format();
    let total = report_final_format();
    let subtotal_amount = report_subtotal_amount_format();
    let total_amount = report_final_amount_format();
    let worksheet = workbook
        .add_worksheet()
        .set_name("Report")
        .map_err(|err| err.to_string())?;
    worksheet
        .merge_range(0, 0, 0, 4, &report.title, &report_title_format())
        .map_err(|err| err.to_string())?;
    worksheet
        .set_row_height(0, 18.0)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(1, 0, "Date", &header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(1, 1, "Type", &header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(1, 2, "Category", &header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(1, 3, &format!("Amount ({})", report.base_currency), &header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(1, 4, "Tags", &header)
        .map_err(|err| err.to_string())?;
    worksheet
        .set_row_height(1, 20.0)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(
            2,
            3,
            &report_amounts_note(&report.filters.totals_mode),
            &report_note_format(),
        )
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(3, 1, &report.summary.balance_label, &data)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(3, 3, report.summary.initial_balance, &amount)
        .map_err(|err| err.to_string())?;
    for (index, row) in report.operations.iter().enumerate() {
        let line = (index + 4) as u32;
        worksheet
            .write_string_with_format(line, 0, &row.date, &data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_string_with_format(line, 1, &row.type_label, &data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_string_with_format(line, 2, &row.category, &data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(line, 3, row.amount_base, &amount)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_string_with_format(line, 4, &row.tags_text, &data)
            .map_err(|err| err.to_string())?;
    }
    let subtotal_row = (report.operations.len() + 4) as u32;
    worksheet
        .write_string_with_format(subtotal_row, 1, "Subtotal", &subtotal)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(
            subtotal_row,
            3,
            if use_current {
                report.summary.records_total_current
            } else {
                report.summary.records_total_fixed
            },
            &subtotal_amount,
        )
        .map_err(|err| err.to_string())?;
    worksheet
        .write_blank(subtotal_row, 0, &subtotal)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_blank(subtotal_row, 2, &subtotal)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_blank(subtotal_row, 4, &subtotal)
        .map_err(|err| err.to_string())?;
    let final_row = subtotal_row + 1;
    worksheet
        .write_string_with_format(final_row, 1, "Final balance", &total)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_blank(final_row, 0, &total)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_blank(final_row, 2, &total)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_blank(final_row, 4, &total)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(
            final_row,
            3,
            if use_current {
                report.summary.final_balance_current
            } else {
                report.summary.final_balance_fixed
            },
            &total_amount,
        )
        .map_err(|err| err.to_string())?;
    worksheet
        .set_freeze_panes(2, 0)
        .map_err(|err| err.to_string())?;
    worksheet
        .autofilter(1, 0, final_row, 4)
        .map_err(|err| err.to_string())?;
    set_report_column_widths(worksheet)?;
    write_report_transfer_sheet(&mut workbook, &report, &header, &data, use_current)?;

    if !report.categories.is_empty() {
        write_report_category_sheet(&mut workbook, &report, &header, &data, &amount)?;
    }
    if !report.tags.is_empty() {
        write_report_tag_sheet(&mut workbook, &report, &header, &data, &amount)?;
    }
    write_report_summary_sheet(&mut workbook, &report, &header, &data, &amount, &total)?;
    if !report.debts.is_empty() {
        write_report_debt_sheet(&mut workbook, &report, &header, &data, &amount)?;
    }
    let bytes = workbook.save_to_buffer().map_err(|err| err.to_string())?;
    atomic_replace(Path::new(path), &bytes)?;
    Ok(ReportExportResult {
        exported_rows: (report.operations.len() + report.transfers.len()) as i64,
        path: path.to_owned(),
    })
}

fn report_title_format() -> Format {
    Format::new()
        .set_bold()
        .set_font_size(14.0)
        .set_background_color("#D9EAD3")
        .set_pattern(FormatPattern::Solid)
        .set_border(FormatBorder::Thin)
        .set_border_color("#D9D9D9")
        .set_align(FormatAlign::VerticalCenter)
}

fn report_header_format() -> Format {
    Format::new()
        .set_bold()
        .set_font_color("#FFFFFF")
        .set_background_color("#1F4E78")
        .set_pattern(FormatPattern::Solid)
        .set_border(FormatBorder::Thin)
        .set_border_color("#D9D9D9")
        .set_align(FormatAlign::Left)
        .set_align(FormatAlign::VerticalCenter)
}

fn report_data_format() -> Format {
    Format::new()
        .set_border(FormatBorder::Thin)
        .set_border_color("#D9D9D9")
        .set_align(FormatAlign::Left)
        .set_align(FormatAlign::VerticalCenter)
}

fn report_note_format() -> Format {
    report_data_format().set_italic().set_font_color("#666666")
}

fn report_amounts_note(totals_mode: &str) -> String {
    if totals_mode.eq_ignore_ascii_case("current") {
        "Current amounts using export-time rates".to_owned()
    } else {
        "Fixed amounts using operation-time rates".to_owned()
    }
}

fn report_amount_format() -> Format {
    report_data_format()
        .set_num_format("#,##0.00")
        .set_align(FormatAlign::Right)
}

fn report_subtotal_format() -> Format {
    report_data_format()
        .set_bold()
        .set_background_color("#E2F0D9")
        .set_pattern(FormatPattern::Solid)
}

fn report_final_format() -> Format {
    report_data_format()
        .set_bold()
        .set_background_color("#FFF2CC")
        .set_pattern(FormatPattern::Solid)
}

fn report_subtotal_amount_format() -> Format {
    report_subtotal_format()
        .set_num_format("#,##0.00")
        .set_align(FormatAlign::Right)
}

fn report_final_amount_format() -> Format {
    report_final_format()
        .set_num_format("#,##0.00")
        .set_align(FormatAlign::Right)
}

fn set_report_column_widths(worksheet: &mut Worksheet) -> StorageResult<()> {
    for (column, width) in [14.0, 22.0, 26.0, 18.0, 32.0].into_iter().enumerate() {
        worksheet
            .set_column_width(column as u16, width)
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn write_report_transfer_sheet(
    workbook: &mut Workbook,
    report: &ReportResult,
    header: &Format,
    data: &Format,
    use_current: bool,
) -> StorageResult<()> {
    if report.transfers.is_empty() {
        return Ok(());
    }
    let worksheet = workbook
        .add_worksheet()
        .set_name("Transfers")
        .map_err(|err| err.to_string())?;
    let columns = [
        "Date", "Transfer ID", "From wallet", "Source amount", "To wallet",
        "Target amount", "Historical rate", "Commission", "Base source",
        "Base target", "Status", "Description", "Tags",
    ];
    for (column, title) in columns.into_iter().enumerate() {
        worksheet
            .write_string_with_format(0, column as u16, title, header)
            .map_err(|err| err.to_string())?;
    }
    for (index, row) in report.transfers.iter().enumerate() {
        let line = (index + 1) as u32;
        let source_base = if use_current { row.source_amount_current } else { row.source_amount_base };
        let target_base = if use_current { row.target_amount_current } else { row.target_amount_base };
        let commission = if row.commission_amount > 0.0 {
            format!("{:.2} {}", row.commission_amount, row.commission_currency)
        } else {
            "-".to_owned()
        };
        let values = [
            row.date.clone(),
            row.transfer_id.to_string(),
            format!("{} (#{})", row.from_wallet_name, row.from_wallet_id),
            format!("{:.2} {}", row.source_amount, row.source_currency),
            format!("{} (#{})", row.to_wallet_name, row.to_wallet_id),
            format!("{:.2} {}", row.target_amount, row.target_currency),
            row.historical_rate.clone(),
            commission,
            format!("{source_base:.2}"),
            format!("{target_base:.2}"),
            if row.integrity_status == "ok" { "OK".to_owned() } else { format!("{}: {}", row.integrity_status, row.integrity_message) },
            row.description.clone(),
            row.tags_text.clone(),
        ];
        for (column, value) in values.into_iter().enumerate() {
            worksheet
                .write_string_with_format(line, column as u16, &value, data)
                .map_err(|err| err.to_string())?;
        }
    }
    worksheet
        .set_freeze_panes(1, 0)
        .map_err(|err| err.to_string())?;
    worksheet
        .autofilter(0, 0, report.transfers.len() as u32, (columns.len() - 1) as u16)
        .map_err(|err| err.to_string())?;
    for (column, width) in [
        14.0, 12.0, 28.0, 20.0, 28.0, 20.0, 18.0, 18.0, 16.0, 16.0,
        28.0, 36.0, 28.0,
    ]
    .into_iter()
    .enumerate()
    {
        worksheet
            .set_column_width(column as u16, width)
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn report_export_grouped_xlsx(
    report: &ReportResult,
    path: &str,
    use_current: bool,
) -> StorageResult<ReportExportResult> {
    let mut workbook = Workbook::new();
    let worksheet = workbook
        .add_worksheet()
        .set_name("Report")
        .map_err(|err| err.to_string())?;
    let title = report_title_format();
    let header = report_header_format();
    let data = report_data_format();
    let amount = report_amount_format();
    let total = report_final_amount_format();
    worksheet
        .merge_range(0, 0, 0, 2, &report.title, &title)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(1, 0, "Category", &header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(1, 1, "Operations", &header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(1, 2, &format!("Amount ({})", report.base_currency), &header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(
            2,
            2,
            &report_amounts_note(&report.filters.totals_mode),
            &report_note_format(),
        )
        .map_err(|err| err.to_string())?;
    let mut total_value = 0.0;
    for (index, row) in report.categories.iter().enumerate() {
        let line = (index + 3) as u32;
        let amount_value = if use_current {
            row.total_current
        } else {
            row.total_base
        };
        total_value += amount_value;
        worksheet
            .write_string_with_format(line, 0, &row.category, &data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(line, 1, row.operations_count as f64, &data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(line, 2, amount_value, &amount)
            .map_err(|err| err.to_string())?;
    }
    let total_row = (report.categories.len() + 3) as u32;
    worksheet
        .write_string_with_format(total_row, 0, "Total", &total)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(total_row, 2, total_value, &total)
        .map_err(|err| err.to_string())?;
    worksheet
        .set_freeze_panes(2, 0)
        .map_err(|err| err.to_string())?;
    worksheet
        .autofilter(1, 0, total_row, 2)
        .map_err(|err| err.to_string())?;
    for (column, width) in [30.0, 16.0, 18.0].into_iter().enumerate() {
        worksheet
            .set_column_width(column as u16, width)
            .map_err(|err| err.to_string())?;
    }
    write_report_transfer_sheet(&mut workbook, report, &header, &data, use_current)?;
    let bytes = workbook.save_to_buffer().map_err(|err| err.to_string())?;
    atomic_replace(Path::new(path), &bytes)?;
    Ok(ReportExportResult {
        exported_rows: (report.categories.len() + report.transfers.len()) as i64,
        path: path.to_owned(),
    })
}

fn write_report_summary_sheet(
    workbook: &mut Workbook,
    report: &ReportResult,
    header: &Format,
    data: &Format,
    amount: &Format,
    total: &Format,
) -> StorageResult<()> {
    let total_amount = report_final_amount_format();
    let use_current = report.filters.totals_mode.eq_ignore_ascii_case("current");
    let worksheet = workbook
        .add_worksheet()
        .set_name("Yearly Report")
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(0, 0, "Month", header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(0, 1, &format!("Income ({})", report.base_currency), header)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(
            0,
            2,
            &format!("Expenses ({})", report.base_currency),
            header,
        )
        .map_err(|err| err.to_string())?;
    worksheet
        .set_row_height(0, 20.0)
        .map_err(|err| err.to_string())?;
    for (index, row) in report.monthly.iter().enumerate() {
        let line = (index + 1) as u32;
        worksheet
            .write_string_with_format(line, 0, &row.month, data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(
                line,
                1,
                if use_current {
                    row.income_current
                } else {
                    row.income
                },
                amount,
            )
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(
                line,
                2,
                if use_current {
                    row.expenses_current
                } else {
                    row.expenses
                },
                amount,
            )
            .map_err(|err| err.to_string())?;
    }
    let total_row = (report.monthly.len() + 1) as u32;
    worksheet
        .write_string_with_format(total_row, 0, "Total", total)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(
            total_row,
            1,
            report
                .monthly
                .iter()
                .map(|row| {
                    if use_current {
                        row.income_current
                    } else {
                        row.income
                    }
                })
                .sum::<f64>(),
            &total_amount,
        )
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(
            total_row,
            2,
            report
                .monthly
                .iter()
                .map(|row| {
                    if use_current {
                        row.expenses_current
                    } else {
                        row.expenses
                    }
                })
                .sum::<f64>(),
            &total_amount,
        )
        .map_err(|err| err.to_string())?;
    worksheet
        .set_freeze_panes(1, 0)
        .map_err(|err| err.to_string())?;
    worksheet
        .autofilter(0, 0, total_row, 2)
        .map_err(|err| err.to_string())?;
    for (column, width) in [16.0, 18.0, 20.0].into_iter().enumerate() {
        worksheet
            .set_column_width(column as u16, width)
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn write_report_category_sheet(
    workbook: &mut Workbook,
    report: &ReportResult,
    header: &Format,
    data: &Format,
    amount: &Format,
) -> StorageResult<()> {
    let use_current = report.filters.totals_mode.eq_ignore_ascii_case("current");
    let worksheet = workbook
        .add_worksheet()
        .set_name("By Category")
        .map_err(|err| err.to_string())?;
    for (column, value) in ["Category", "Operations", "Amount"].into_iter().enumerate() {
        worksheet
            .write_string_with_format(0, column as u16, value, header)
            .map_err(|err| err.to_string())?;
    }
    for (index, row) in report.categories.iter().enumerate() {
        let line = (index + 1) as u32;
        worksheet
            .write_string_with_format(line, 0, &row.category, data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(line, 1, row.operations_count as f64, data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(
                line,
                2,
                if use_current {
                    row.total_current
                } else {
                    row.total_base
                },
                amount,
            )
            .map_err(|err| err.to_string())?;
    }
    worksheet
        .set_freeze_panes(1, 0)
        .map_err(|err| err.to_string())?;
    worksheet
        .autofilter(0, 0, report.categories.len() as u32, 2)
        .map_err(|err| err.to_string())?;
    for (column, width) in [30.0, 16.0, 18.0].into_iter().enumerate() {
        worksheet
            .set_column_width(column as u16, width)
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn write_report_tag_sheet(
    workbook: &mut Workbook,
    report: &ReportResult,
    header: &Format,
    data: &Format,
    amount: &Format,
) -> StorageResult<()> {
    let use_current = report.filters.totals_mode.eq_ignore_ascii_case("current");
    let worksheet = workbook
        .add_worksheet()
        .set_name("By Tag")
        .map_err(|err| err.to_string())?;
    for (column, value) in ["Tag", "Operations", "Amount"].into_iter().enumerate() {
        worksheet
            .write_string_with_format(0, column as u16, value, header)
            .map_err(|err| err.to_string())?;
    }
    for (index, row) in report.tags.iter().enumerate() {
        let line = (index + 1) as u32;
        worksheet
            .write_string_with_format(line, 0, &row.tag, data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(line, 1, row.operations_count as f64, data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(
                line,
                2,
                if use_current {
                    row.total_current
                } else {
                    row.total_base
                },
                amount,
            )
            .map_err(|err| err.to_string())?;
    }
    worksheet
        .set_freeze_panes(1, 0)
        .map_err(|err| err.to_string())?;
    worksheet
        .autofilter(0, 0, report.tags.len() as u32, 2)
        .map_err(|err| err.to_string())?;
    for (column, width) in [30.0, 16.0, 18.0].into_iter().enumerate() {
        worksheet
            .set_column_width(column as u16, width)
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn write_report_debt_sheet(
    workbook: &mut Workbook,
    report: &ReportResult,
    header: &Format,
    data: &Format,
    amount: &Format,
) -> StorageResult<()> {
    let worksheet = workbook
        .add_worksheet()
        .set_name("Debts")
        .map_err(|err| err.to_string())?;
    let headers = [
        "Contact",
        "Type",
        "Status",
        "Created",
        "Closed",
        "Currency",
        "Total",
        "Remaining",
        "Settled",
        "Progress %",
    ];
    for (column, value) in headers.into_iter().enumerate() {
        worksheet
            .write_string_with_format(0, column as u16, value, header)
            .map_err(|err| err.to_string())?;
    }
    for (index, row) in report.debts.iter().enumerate() {
        let line = (index + 1) as u32;
        let values = [
            &row.contact_name,
            &row.kind,
            &row.status,
            &row.created_at,
            row.closed_at.as_deref().unwrap_or("-"),
            &row.currency,
        ];
        for (column, value) in values.into_iter().enumerate() {
            worksheet
                .write_string_with_format(line, column as u16, value, data)
                .map_err(|err| err.to_string())?;
        }
        for (column, value) in [
            (6, row.total_amount),
            (7, row.remaining_amount),
            (8, row.settled_amount),
            (9, row.progress_percent),
        ] {
            worksheet
                .write_number_with_format(line, column, value, amount)
                .map_err(|err| err.to_string())?;
        }
    }
    worksheet
        .set_freeze_panes(1, 0)
        .map_err(|err| err.to_string())?;
    worksheet
        .autofilter(0, 0, report.debts.len() as u32, 9)
        .map_err(|err| err.to_string())?;
    for (column, width) in [24.0, 14.0, 14.0, 14.0, 14.0, 12.0, 16.0, 16.0, 16.0, 14.0]
        .into_iter()
        .enumerate()
    {
        worksheet
            .set_column_width(column as u16, width)
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

pub fn report_export_pdf(
    db_path: &str,
    filters: &ReportFilters,
    path: &str,
) -> StorageResult<ReportExportResult> {
    let report = report_generate(db_path, filters)?;
    let use_current = report.filters.totals_mode.eq_ignore_ascii_case("current");
    if report.filters.group_by_category {
        return report_export_grouped_pdf(&report, path, use_current);
    }
    let mut rows = vec![
        PdfReportRow::merged(report.title.clone(), PdfRowStyle::Title),
        PdfReportRow::new(
            ["Date", "Type", "Category", "Amount", "Tags"],
            PdfRowStyle::Header,
        ),
        PdfReportRow::merged(
            report_amounts_note(&report.filters.totals_mode),
            PdfRowStyle::Note,
        ),
    ];
    rows.push(PdfReportRow::new(
        [
            String::new(),
            report.summary.balance_label.clone(),
            String::new(),
            format!("{:.2}", report.summary.initial_balance),
            String::new(),
        ],
        PdfRowStyle::Balance,
    ));
    for row in &report.operations {
        rows.push(PdfReportRow::new(
            [
                row.date.clone(),
                row.type_label.clone(),
                row.category.clone(),
                format!(
                    "{:.2}",
                    if use_current {
                        row.amount_current
                    } else {
                        row.amount_base
                    }
                ),
                row.tags_text.clone(),
            ],
            PdfRowStyle::Data,
        ));
    }
    rows.push(PdfReportRow::new(
        [
            String::new(),
            "Subtotal".to_owned(),
            String::new(),
            format!(
                "{:.2}",
                if use_current {
                    report.summary.records_total_current
                } else {
                    report.summary.records_total_fixed
                }
            ),
            String::new(),
        ],
        PdfRowStyle::Subtotal,
    ));
    rows.push(PdfReportRow::new(
        [
            String::new(),
            "Final balance".to_owned(),
            String::new(),
            format!(
                "{:.2}",
                if use_current {
                    report.summary.final_balance_current
                } else {
                    report.summary.final_balance_fixed
                }
            ),
            String::new(),
        ],
        PdfRowStyle::Final,
    ));
    append_pdf_transfer_section(&mut rows, &report, use_current);
    rows.push(PdfReportRow::merged(
        "Monthly summary".to_owned(),
        PdfRowStyle::Section,
    ));
    rows.push(PdfReportRow::new(
        ["Month", "Income", "Expenses", "", ""],
        PdfRowStyle::Header,
    ));
    for row in &report.monthly {
        rows.push(PdfReportRow::new(
            [
                row.month.clone(),
                format!(
                    "{:.2}",
                    if use_current {
                        row.income_current
                    } else {
                        row.income
                    }
                ),
                format!(
                    "{:.2}",
                    if use_current {
                        row.expenses_current
                    } else {
                        row.expenses
                    }
                ),
                String::new(),
                String::new(),
            ],
            PdfRowStyle::Data,
        ));
    }
    if !report.categories.is_empty() {
        rows.push(PdfReportRow::merged(
            "Category summary".to_owned(),
            PdfRowStyle::Section,
        ));
        rows.push(PdfReportRow::new(
            ["Category", "Operations", "Amount", "", ""],
            PdfRowStyle::Header,
        ));
        for row in &report.categories {
            rows.push(PdfReportRow::new(
                [
                    row.category.clone(),
                    row.operations_count.to_string(),
                    format!(
                        "{:.2}",
                        if use_current {
                            row.total_current
                        } else {
                            row.total_base
                        }
                    ),
                    String::new(),
                    String::new(),
                ],
                PdfRowStyle::Data,
            ));
        }
    }
    if !report.tags.is_empty() {
        rows.push(PdfReportRow::merged(
            "Tag summary".to_owned(),
            PdfRowStyle::Section,
        ));
        rows.push(PdfReportRow::new(
            ["Tag", "Operations", "Amount", "", ""],
            PdfRowStyle::Header,
        ));
        for row in &report.tags {
            rows.push(PdfReportRow::new(
                [
                    row.tag.clone(),
                    row.operations_count.to_string(),
                    format!(
                        "{:.2}",
                        if use_current {
                            row.total_current
                        } else {
                            row.total_base
                        }
                    ),
                    String::new(),
                    String::new(),
                ],
                PdfRowStyle::Data,
            ));
        }
    }
    if !report.debts.is_empty() {
        rows.push(PdfReportRow::merged(
            "Debts".to_owned(),
            PdfRowStyle::Section,
        ));
        rows.push(PdfReportRow::new(
            ["Contact", "Type", "Status", "Total", "Remaining"],
            PdfRowStyle::Header,
        ));
        for row in &report.debts {
            rows.push(PdfReportRow::new(
                [
                    row.contact_name.clone(),
                    row.kind.clone(),
                    row.status.clone(),
                    format!("{:.2} {}", row.total_amount, row.currency),
                    format!("{:.2} {}", row.remaining_amount, row.currency),
                ],
                PdfRowStyle::Data,
            ));
        }
    }
    let font_bytes = load_report_font()?;
    let font = ParsedFont::from_bytes(&font_bytes, 0, &mut Vec::new())
        .ok_or_else(|| "unable to parse report font".to_owned())?;
    let mut document = PdfDocument::new(&report.title);
    let font_id = document.add_font(&font);
    let pages = render_pdf_report_pages(&rows, &font_id);
    let pages = if pages.is_empty() {
        vec![PdfPage::new(Mm(210.0), Mm(297.0), vec![])]
    } else {
        pages
    };
    let pdf = document
        .with_pages(pages)
        .save(&PdfSaveOptions::default(), &mut Vec::new());
    atomic_replace(Path::new(path), &pdf)?;
    Ok(ReportExportResult {
        exported_rows: (report.operations.len() + report.transfers.len()) as i64,
        path: path.to_owned(),
    })
}

fn append_pdf_transfer_section(rows: &mut Vec<PdfReportRow>, report: &ReportResult, use_current: bool) {
    if report.transfers.is_empty() {
        return;
    }
    rows.push(PdfReportRow::merged("Transfers".to_owned(), PdfRowStyle::Section));
    rows.push(PdfReportRow::new(
        ["Date", "Transfer", "Source -> Target", "Rate / Commission", "Status"],
        PdfRowStyle::Header,
    ));
    for row in &report.transfers {
        let source_base = if use_current { row.source_amount_current } else { row.source_amount_base };
        let target_base = if use_current { row.target_amount_current } else { row.target_amount_base };
        let commission = if row.commission_amount > 0.0 {
            format!("{:.2} {}", row.commission_amount, row.commission_currency)
        } else {
            "-".to_owned()
        };
        let status = if row.integrity_status == "ok" {
            "OK".to_owned()
        } else {
            format!("{}: {}", row.integrity_status, row.integrity_message)
        };
        rows.push(PdfReportRow::new(
            [
                row.date.clone(),
                format!("#{}", row.transfer_id),
                format!(
                    "{}: {:.2} {} -> {}: {:.2} {} (base {:.2} / {:.2})",
                    row.from_wallet_name,
                    row.source_amount,
                    row.source_currency,
                    row.to_wallet_name,
                    row.target_amount,
                    row.target_currency,
                    source_base,
                    target_base,
                ),
                format!("{} / commission {}", row.historical_rate, commission),
                status,
            ],
            PdfRowStyle::Data,
        ));
        if !row.description.is_empty() || !row.tags_text.is_empty() {
            rows.push(PdfReportRow::merged(
                format!("  {} {}", row.description, row.tags_text),
                PdfRowStyle::Note,
            ));
        }
    }
}

fn report_export_grouped_pdf(
    report: &ReportResult,
    path: &str,
    use_current: bool,
) -> StorageResult<ReportExportResult> {
    let mut rows = vec![
        PdfReportRow::merged(report.title.clone(), PdfRowStyle::Title),
        PdfReportRow::new(
            ["Category", "Operations", "Amount", "", ""],
            PdfRowStyle::Header,
        ),
        PdfReportRow::merged(
            report_amounts_note(&report.filters.totals_mode),
            PdfRowStyle::Note,
        ),
    ];
    let mut total = 0.0;
    for row in &report.categories {
        let amount = if use_current {
            row.total_current
        } else {
            row.total_base
        };
        total += amount;
        rows.push(PdfReportRow::new(
            [
                row.category.clone(),
                row.operations_count.to_string(),
                format!("{amount:.2}"),
                String::new(),
                String::new(),
            ],
            PdfRowStyle::Data,
        ));
    }
    rows.push(PdfReportRow::new(
        [
            "Total".to_owned(),
            String::new(),
            format!("{total:.2}"),
            String::new(),
            String::new(),
        ],
        PdfRowStyle::Final,
    ));
    append_pdf_transfer_section(&mut rows, report, use_current);
    let font_bytes = load_report_font()?;
    let font = ParsedFont::from_bytes(&font_bytes, 0, &mut Vec::new())
        .ok_or_else(|| "unable to parse report font".to_owned())?;
    let mut document = PdfDocument::new(&report.title);
    let font_id = document.add_font(&font);
    let pages = render_pdf_report_pages(&rows, &font_id);
    let pdf = document
        .with_pages(pages)
        .save(&PdfSaveOptions::default(), &mut Vec::new());
    atomic_replace(Path::new(path), &pdf)?;
    Ok(ReportExportResult {
        exported_rows: (report.categories.len() + report.transfers.len()) as i64,
        path: path.to_owned(),
    })
}

#[derive(Debug, Clone, Copy)]
enum PdfRowStyle {
    Title,
    Header,
    Note,
    Data,
    Balance,
    Subtotal,
    Final,
    Section,
}

#[derive(Debug, Clone)]
struct PdfReportRow {
    cells: Vec<String>,
    style: PdfRowStyle,
    merged: bool,
}

impl PdfReportRow {
    fn new<const N: usize>(cells: [impl Into<String>; N], style: PdfRowStyle) -> Self {
        Self {
            cells: cells.into_iter().map(Into::into).collect(),
            style,
            merged: false,
        }
    }

    fn merged(value: String, style: PdfRowStyle) -> Self {
        Self {
            cells: vec![value],
            style,
            merged: true,
        }
    }
}

fn render_pdf_report_pages(rows: &[PdfReportRow], font_id: &printpdf::FontId) -> Vec<PdfPage> {
    const LEFT: f32 = 36.0;
    const TOP: f32 = 806.0;
    const BOTTOM: f32 = 36.0;
    const WIDTHS: [f32; 5] = [84.0, 94.0, 147.0, 105.0, 93.0];
    const TOTAL_WIDTH: f32 = 523.0;

    let mut pages = Vec::new();
    let mut current = Vec::new();
    let mut y = TOP;
    let mut row_index = 0usize;
    let mut repeat_header: Option<&PdfReportRow> = None;
    while row_index < rows.len() {
        let row = &rows[row_index];
        let height = pdf_row_height(row, &WIDTHS);
        if y - height < BOTTOM && !current.is_empty() {
            pages.push(PdfPage::new(Mm(210.0), Mm(297.0), current));
            current = Vec::new();
            y = TOP;
            if !matches!(
                row.style,
                PdfRowStyle::Header | PdfRowStyle::Title | PdfRowStyle::Section
            ) {
                if let Some(header) = repeat_header {
                    append_pdf_row(&mut current, header, LEFT, y, &WIDTHS, TOTAL_WIDTH, font_id);
                    y -= pdf_row_height(header, &WIDTHS);
                }
            }
        }
        append_pdf_row(&mut current, row, LEFT, y, &WIDTHS, TOTAL_WIDTH, font_id);
        y -= height;
        if matches!(row.style, PdfRowStyle::Header) {
            repeat_header = Some(row);
        }
        row_index += 1;
    }
    if !current.is_empty() {
        pages.push(PdfPage::new(Mm(210.0), Mm(297.0), current));
    }
    if pages.is_empty() {
        pages.push(PdfPage::new(Mm(210.0), Mm(297.0), vec![]));
    }
    pages
}

fn pdf_row_height(row: &PdfReportRow, widths: &[f32; 5]) -> f32 {
    let base = match row.style {
        PdfRowStyle::Title => 24.0,
        PdfRowStyle::Section => 20.0,
        PdfRowStyle::Header | PdfRowStyle::Note => 18.0,
        _ => 17.0,
    };
    if row.merged {
        return base;
    }
    row.cells
        .iter()
        .zip(widths.iter())
        .map(|(cell, width)| wrap_pdf_line(cell, ((*width / 4.4) as usize).max(8)).len())
        .max()
        .unwrap_or(1)
        .max(1) as f32
        * 10.0
        + 7.0
}

fn append_pdf_row(
    ops: &mut Vec<Op>,
    row: &PdfReportRow,
    left: f32,
    top: f32,
    widths: &[f32; 5],
    total_width: f32,
    font_id: &printpdf::FontId,
) {
    let height = pdf_row_height(row, widths);
    let fill = match row.style {
        PdfRowStyle::Title => (217.0, 234.0, 211.0),
        PdfRowStyle::Header => (211.0, 211.0, 211.0),
        PdfRowStyle::Note => (255.0, 255.0, 255.0),
        PdfRowStyle::Balance => (242.0, 242.0, 242.0),
        PdfRowStyle::Subtotal => (226.0, 240.0, 217.0),
        PdfRowStyle::Final => (255.0, 242.0, 204.0),
        PdfRowStyle::Section => (217.0, 234.0, 247.0),
        PdfRowStyle::Data => (255.0, 255.0, 255.0),
    };
    let text_color = if matches!(row.style, PdfRowStyle::Header) {
        (31.0, 31.0, 31.0)
    } else {
        (0.0, 0.0, 0.0)
    };
    let cell_count = if row.merged { 1 } else { 5 };
    let cell_widths = if row.merged {
        vec![total_width]
    } else {
        widths.to_vec()
    };
    let mut x = left;
    for cell_index in 0..cell_count {
        let width = cell_widths[cell_index];
        ops.push(Op::SetFillColor {
            col: Color::Rgb(Rgb::new(
                fill.0 / 255.0,
                fill.1 / 255.0,
                fill.2 / 255.0,
                None,
            )),
        });
        ops.push(Op::SetOutlineColor {
            col: Color::Rgb(Rgb::new(0.55, 0.55, 0.55, None)),
        });
        ops.push(Op::SetOutlineThickness { pt: Pt(0.45) });
        ops.push(Op::DrawRectangle {
            rectangle: Rect {
                x: Pt(x),
                y: Pt(top - height),
                width: Pt(width),
                height: Pt(height),
                mode: Some(PaintMode::FillStroke),
                winding_order: None,
            },
        });
        let value = row.cells.get(cell_index).cloned().unwrap_or_default();
        let max_chars = ((width / 4.4) as usize).max(8);
        let lines = wrap_pdf_line(&value, max_chars);
        ops.push(Op::SetFillColor {
            col: Color::Rgb(Rgb::new(
                text_color.0 / 255.0,
                text_color.1 / 255.0,
                text_color.2 / 255.0,
                None,
            )),
        });
        let font_size = match row.style {
            PdfRowStyle::Title => 12.0,
            PdfRowStyle::Header => 8.5,
            PdfRowStyle::Section => 9.5,
            _ => 7.5,
        };
        ops.push(Op::SetFont {
            font: PdfFontHandle::External(font_id.clone()),
            size: Pt(font_size),
        });
        ops.push(Op::StartTextSection);
        for (line_index, line) in lines.iter().enumerate() {
            let align_center = row.merged || matches!(row.style, PdfRowStyle::Header);
            let align_right = !align_center && !row.merged && cell_index >= 3;
            let text_width = line.chars().count() as f32 * font_size * 0.48;
            let text_x = if row.merged {
                left + (total_width - text_width).max(0.0) / 2.0
            } else if align_center {
                x + (width - text_width).max(0.0) / 2.0
            } else if align_right {
                x + width - 4.0 - text_width
            } else {
                x + 4.0
            };
            let text_y = if align_center {
                top - height / 2.0 - font_size / 2.0 - line_index as f32 * 9.0
            } else {
                top - 11.0 - line_index as f32 * 9.0
            };
            ops.push(Op::SetTextCursor {
                pos: Point::new(Pt(text_x).into(), Pt(text_y).into()),
            });
            ops.push(Op::ShowText {
                items: vec![TextItem::Text(line.clone())],
            });
        }
        ops.push(Op::EndTextSection);
        x += width;
    }
}

fn load_report_font() -> StorageResult<Vec<u8>> {
    const BUNDLED_FONT: &[u8] = include_bytes!("../assets/DejaVuSans.ttf");
    if !BUNDLED_FONT.is_empty() {
        return Ok(BUNDLED_FONT.to_vec());
    }
    let mut candidates = Vec::new();
    if let Ok(path) = std::env::var("LEDGER_REPORT_FONT") {
        candidates.push(path);
    }
    candidates.extend([
        "C:/Windows/Fonts/arial.ttf".to_owned(),
        "C:/Windows/Fonts/segoeui.ttf".to_owned(),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf".to_owned(),
        "/usr/share/fonts/dejavu/DejaVuSans.ttf".to_owned(),
    ]);
    for path in candidates {
        if let Ok(bytes) = fs::read(path) {
            return Ok(bytes);
        }
    }
    Err("no Unicode report font found; set LEDGER_REPORT_FONT".to_owned())
}

fn wrap_pdf_line(value: &str, max_chars: usize) -> Vec<String> {
    if value.chars().count() <= max_chars {
        return vec![value.to_owned()];
    }
    let mut lines = Vec::new();
    let mut current = String::new();
    for word in value.split_whitespace() {
        let separator = if current.is_empty() { 0 } else { 1 };
        if current.chars().count() + separator + word.chars().count() > max_chars
            && !current.is_empty()
        {
            lines.push(std::mem::take(&mut current));
        }
        if !current.is_empty() {
            current.push(' ');
        }
        current.push_str(word);
    }
    if !current.is_empty() {
        lines.push(current);
    }
    if lines.is_empty() {
        vec![String::new()]
    } else {
        lines
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        create_currency_transfer, create_transfer, create_wallet, initialize_database,
        upsert_currency_rate, CurrencyRatePayload, CurrencyTransferCreatePayload,
        TransferCreatePayload, WalletCreatePayload,
    };
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn report_exposes_one_logical_transfer_without_double_counting() {
        let path = std::env::temp_dir().join(format!(
            "ledgera_report_transfer_{}.db",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        let db_path = path.to_string_lossy().to_string();
        initialize_database(&db_path).expect("initialize database");
        let source = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Source".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "100".to_owned(),
                allow_negative: false,
            },
        )
        .expect("create source");
        let target = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "Target".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .expect("create target");
        create_transfer(
            &db_path,
            &TransferCreatePayload {
                from_wallet_id: source.id,
                to_wallet_id: target.id,
                date: "2026-01-02".to_owned(),
                amount: "25".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move to target".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .expect("create transfer");

        let all_wallets = report_generate(&db_path, &ReportFilters::default()).expect("report");
        assert_eq!(all_wallets.operations.len(), 0);
        assert_eq!(all_wallets.transfers.len(), 1);
        assert_eq!(all_wallets.summary.records_total_fixed, 0.0);
        assert_eq!(all_wallets.summary.transfer_net_fixed, 0.0);
        assert_eq!(all_wallets.summary.final_balance_fixed, 100.0);
        assert_eq!(all_wallets.transfers[0].historical_rate, "1");
        assert_eq!(all_wallets.transfers[0].source_amount, 25.0);
        assert_eq!(all_wallets.transfers[0].target_amount, 25.0);

        let source_report = report_generate(
            &db_path,
            &ReportFilters {
                wallet_id: Some(source.id),
                ..ReportFilters::default()
            },
        )
        .expect("source report");
        assert_eq!(source_report.summary.transfer_net_fixed, -25.0);
        assert_eq!(source_report.summary.final_balance_fixed, 75.0);

        std::fs::remove_file(path).ok();
    }

    #[test]
    fn report_keeps_both_sides_of_a_foreign_currency_transfer() {
        let path = std::env::temp_dir().join(format!(
            "ledgera_report_fx_transfer_{}.db",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        let db_path = path.to_string_lossy().to_string();
        initialize_database(&db_path).expect("initialize database");
        let source = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "KZT source".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "100000".to_owned(),
                allow_negative: false,
            },
        )
        .expect("create source");
        let target = create_wallet(
            &db_path,
            &WalletCreatePayload {
                name: "USD target".to_owned(),
                currency: "USD".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            },
        )
        .expect("create target");
        upsert_currency_rate(
            &db_path,
            &CurrencyRatePayload {
                base_currency: "KZT".to_owned(),
                currency: "USD".to_owned(),
                rate: "500".to_owned(),
                effective_date: "2026-01-01".to_owned(),
                source: "manual".to_owned(),
            },
        )
        .expect("save USD rate");
        create_currency_transfer(
            &db_path,
            &CurrencyTransferCreatePayload {
                from_wallet_id: source.id,
                to_wallet_id: target.id,
                date: "2026-01-02".to_owned(),
                amount: "1000".to_owned(),
                amount_currency: "KZT".to_owned(),
                description: "Foreign transfer".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            },
        )
        .expect("create foreign transfer");

        let report = report_generate(&db_path, &ReportFilters::default()).expect("report");
        let row = report.transfers.first().expect("transfer row");
        assert_eq!(report.transfers.len(), 1);
        assert_eq!(row.source_currency, "KZT");
        assert_eq!(row.target_currency, "USD");
        assert_eq!(row.source_amount, 1000.0);
        assert_eq!(row.target_amount, 2.0);
        assert_eq!(row.source_amount_base, 1000.0);
        assert_eq!(row.target_amount_base, 1000.0);
        assert_eq!(row.integrity_status, "ok");
        assert_eq!(report.summary.records_total_fixed, 0.0);
        assert_eq!(report.summary.transfer_net_fixed, 0.0);

        std::fs::remove_file(path).ok();
    }
}
