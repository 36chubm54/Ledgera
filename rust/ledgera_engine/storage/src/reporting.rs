use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use ledgera_engine_core::minor_to_money_value;
use rusqlite::Connection;
use rust_xlsxwriter::{Format, FormatAlign, FormatBorder, FormatPattern, Workbook, Worksheet};

use crate::{
    RecordRow, StorageResult, base_currency_code, current_local_date, record_list_rows,
    round_money, sqlite_err, with_cached_read_connection,
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
    pub final_balance_fixed: f64,
    pub final_balance_current: f64,
    pub fx_difference: f64,
    pub records_count: i64,
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
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportMonthlyRow {
    pub month: String,
    pub income: f64,
    pub expenses: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportCategoryRow {
    pub category: String,
    pub operations_count: i64,
    pub total_base: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportTagRow {
    pub tag: String,
    pub operations_count: i64,
    pub total_base: f64,
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
    let path = Path::new(db_path)
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("currency_rates.json");
    if !path.is_file() {
        return Ok(std::collections::HashMap::new());
    }
    let text = fs::read_to_string(&path)
        .map_err(|err| format!("Failed to read current currency rates: {err}"))?;
    serde_json::from_str(&text).map_err(|err| format!("Invalid current currency rates: {err}"))
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
) -> StorageResult<Vec<ReportDebtRow>> {
    let mut stmt = conn.prepare(
        "SELECT contact_name, kind, status, created_at, closed_at, currency, total_amount_minor, remaining_amount_minor FROM debts WHERE created_at <= ?2 AND (closed_at IS NULL OR closed_at >= ?1) ORDER BY created_at, id",
    ).map_err(sqlite_err)?;
    let rows = stmt
        .query_map((start, end), |row| {
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
    if !normalized.category.trim().is_empty() || !normalized.tag.trim().is_empty() {
        opening_balance = 0.0;
    }
    let rates = if normalized.totals_mode.eq_ignore_ascii_case("current") {
        load_cached_rates(db_path)?
    } else {
        std::collections::HashMap::new()
    };
    let mut fixed_total = 0.0;
    let mut current_total = 0.0;
    let mut operations = Vec::new();
    let mut category_totals: BTreeMap<String, (i64, f64)> = BTreeMap::new();
    let mut tag_totals: BTreeMap<String, (i64, f64)> = BTreeMap::new();
    let mut monthly: BTreeMap<String, (f64, f64)> = BTreeMap::new();
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
            description: record.description.clone(),
        });
        let entry = category_totals.entry(record.category.clone()).or_default();
        entry.0 += 1;
        entry.1 += fixed;
        for tag in tags {
            let entry = tag_totals.entry(tag.clone()).or_default();
            entry.0 += 1;
            entry.1 += fixed;
        }
        if let Some(month) = month_key(&record.date) {
            let entry = monthly.entry(month).or_default();
            if record.record_type == "income" {
                entry.0 += record.amount_base;
            } else {
                entry.1 += record.amount_base;
            }
        }
    }
    let initial = wallet_initial + opening_balance;
    let final_fixed = initial + fixed_total;
    let final_current = initial + current_total;
    let summary = ReportSummary {
        net_worth_fixed: final_fixed,
        net_worth_current: final_current,
        initial_balance: initial,
        records_total_fixed: fixed_total,
        final_balance_fixed: final_fixed,
        final_balance_current: final_current,
        fx_difference: current_total - fixed_total,
        records_count: operations.len() as i64,
        balance_label: if start.is_some() {
            "Opening balance".to_owned()
        } else {
            "Initial balance".to_owned()
        },
        active_tag: normalized.tag.clone(),
    };
    let monthly = monthly
        .into_iter()
        .map(|(month, (income, expenses))| ReportMonthlyRow {
            month,
            income,
            expenses,
        })
        .collect();
    let categories = category_totals
        .into_iter()
        .map(|(category, (count, total))| ReportCategoryRow {
            category,
            operations_count: count,
            total_base: total,
        })
        .collect();
    let tags = tag_totals
        .into_iter()
        .map(|(tag, (count, total))| ReportTagRow {
            tag,
            operations_count: count,
            total_base: total,
        })
        .collect();
    let debts = with_cached_read_connection(db_path, |conn| {
        debt_rows_for_period(
            conn,
            start.unwrap_or("0000-01-01"),
            end.unwrap_or("9999-12-31"),
        )
    })?;
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
        monthly,
        categories,
        tags,
        debts,
    })
}

fn atomic_replace(path: &Path, bytes: &[u8]) -> StorageResult<()> {
    let temp = path.with_extension(format!(
        "{}.tmp",
        path.extension()
            .and_then(|v| v.to_str())
            .unwrap_or("report")
    ));
    fs::write(&temp, bytes).map_err(|err| format!("Failed to write report export: {err}"))?;
    fs::rename(&temp, path).map_err(|err| format!("Failed to finalize report export: {err}"))
}

pub fn report_export_csv(
    db_path: &str,
    filters: &ReportFilters,
    path: &str,
) -> StorageResult<ReportExportResult> {
    let report = report_generate(db_path, filters)?;
    let mut writer = csv::Writer::from_writer(Vec::new());
    writer
        .write_record([report.title.as_str(), "", "", "", ""])
        .map_err(|err| err.to_string())?;
    writer
        .write_record([
            "Date",
            "Type",
            "Category",
            &format!("Amount ({})", report.base_currency),
            "Tags",
        ])
        .map_err(|err| err.to_string())?;
    writer
        .write_record([
            "",
            "",
            "",
            &report_amounts_note(&report.filters.totals_mode),
            "",
        ])
        .map_err(|err| err.to_string())?;
    writer
        .write_record([
            "",
            report.summary.balance_label.as_str(),
            "",
            &format!("{:.2}", report.summary.initial_balance),
            "",
        ])
        .map_err(|err| err.to_string())?;
    for row in &report.operations {
        writer
            .write_record([
                row.date.as_str(),
                row.type_label.as_str(),
                row.category.as_str(),
                &format!("{:.2}", row.amount_base),
                row.tags_text.as_str(),
            ])
            .map_err(|err| err.to_string())?;
    }
    writer
        .write_record([
            "",
            "Subtotal",
            "",
            &format!("{:.2}", report.summary.records_total_fixed),
            "",
        ])
        .map_err(|err| err.to_string())?;
    writer
        .write_record([
            "",
            "Final balance",
            "",
            &format!("{:.2}", report.summary.final_balance_fixed),
            "",
        ])
        .map_err(|err| err.to_string())?;
    let bytes = writer.into_inner().map_err(|err| err.to_string())?;
    atomic_replace(Path::new(path), &bytes)?;
    Ok(ReportExportResult {
        exported_rows: report.operations.len() as i64,
        path: path.to_owned(),
    })
}

pub fn report_export_xlsx(
    db_path: &str,
    filters: &ReportFilters,
    path: &str,
) -> StorageResult<ReportExportResult> {
    let report = report_generate(db_path, filters)?;
    let mut workbook = Workbook::new();
    let header = report_header_format();
    let data = report_data_format();
    let amount = report_amount_format();
    let total = report_total_format();
    let worksheet = workbook
        .add_worksheet()
        .set_name("Report")
        .map_err(|err| err.to_string())?;
    worksheet
        .write_string_with_format(0, 0, &report.title, &report_title_format())
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
        .write_string_with_format(subtotal_row, 1, "Subtotal", &total)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(subtotal_row, 3, report.summary.records_total_fixed, &amount)
        .map_err(|err| err.to_string())?;
    let final_row = subtotal_row + 1;
    worksheet
        .write_string_with_format(final_row, 1, "Final balance", &total)
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(final_row, 3, report.summary.final_balance_fixed, &amount)
        .map_err(|err| err.to_string())?;
    worksheet
        .set_freeze_panes(2, 0)
        .map_err(|err| err.to_string())?;
    worksheet
        .autofilter(1, 0, final_row, 4)
        .map_err(|err| err.to_string())?;
    set_report_column_widths(worksheet)?;

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
        exported_rows: report.operations.len() as i64,
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
}

fn report_data_format() -> Format {
    Format::new()
        .set_border(FormatBorder::Thin)
        .set_border_color("#D9D9D9")
        .set_align(FormatAlign::Left)
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

fn report_total_format() -> Format {
    report_data_format()
        .set_bold()
        .set_background_color("#E2F0D9")
        .set_pattern(FormatPattern::Solid)
}

fn set_report_column_widths(worksheet: &mut Worksheet) -> StorageResult<()> {
    for (column, width) in [14.0, 22.0, 26.0, 18.0, 32.0].into_iter().enumerate() {
        worksheet
            .set_column_width(column as u16, width)
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn write_report_summary_sheet(
    workbook: &mut Workbook,
    report: &ReportResult,
    header: &Format,
    data: &Format,
    amount: &Format,
    total: &Format,
) -> StorageResult<()> {
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
    for (index, row) in report.monthly.iter().enumerate() {
        let line = (index + 1) as u32;
        worksheet
            .write_string_with_format(line, 0, &row.month, data)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(line, 1, row.income, amount)
            .map_err(|err| err.to_string())?;
        worksheet
            .write_number_with_format(line, 2, row.expenses, amount)
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
            report.monthly.iter().map(|row| row.income).sum::<f64>(),
            amount,
        )
        .map_err(|err| err.to_string())?;
    worksheet
        .write_number_with_format(
            total_row,
            2,
            report.monthly.iter().map(|row| row.expenses).sum::<f64>(),
            amount,
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
            .write_number_with_format(line, 2, row.total_base, amount)
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
            .write_number_with_format(line, 2, row.total_base, amount)
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
    let mut lines = vec![
        report.title.clone(),
        String::new(),
        format!(
            "{}: {:.2} {}",
            report.summary.balance_label, report.summary.initial_balance, report.base_currency
        ),
        "Date | Type | Category | Amount | Tags".to_owned(),
    ];
    for row in &report.operations {
        lines.push(format!(
            "{} | {} | {} | {:.2} {} | {}",
            row.date,
            row.type_label,
            row.category,
            row.amount_base,
            report.base_currency,
            row.tags_text
        ));
    }
    lines.push(String::new());
    lines.push(format!(
        "Subtotal: {:.2} {}",
        report.summary.records_total_fixed, report.base_currency
    ));
    lines.push(format!(
        "Final balance: {:.2} {}",
        report.summary.final_balance_fixed, report.base_currency
    ));
    lines.push(String::new());
    lines.push("Monthly summary".to_owned());
    for row in &report.monthly {
        lines.push(format!(
            "{} | Income {:.2} | Expenses {:.2}",
            row.month, row.income, row.expenses
        ));
    }
    if !report.categories.is_empty() {
        lines.push(String::new());
        lines.push("Category summary".to_owned());
        for row in &report.categories {
            lines.push(format!(
                "{} | {} operations | {:.2} {}",
                row.category, row.operations_count, row.total_base, report.base_currency
            ));
        }
    }
    if !report.tags.is_empty() {
        lines.push(String::new());
        lines.push("Tag summary".to_owned());
        for row in &report.tags {
            lines.push(format!(
                "{} | {} operations | {:.2} {}",
                row.tag, row.operations_count, row.total_base, report.base_currency
            ));
        }
    }
    if !report.debts.is_empty() {
        lines.push(String::new());
        lines.push("Debts".to_owned());
        for row in &report.debts {
            lines.push(format!(
                "{} | {} | {} | {:.2} / {:.2} {}",
                row.contact_name,
                row.kind,
                row.status,
                row.remaining_amount,
                row.total_amount,
                row.currency
            ));
        }
    }
    let pdf = build_text_pdf(&lines);
    atomic_replace(Path::new(path), pdf.as_bytes())?;
    Ok(ReportExportResult {
        exported_rows: report.operations.len() as i64,
        path: path.to_owned(),
    })
}

fn build_text_pdf(lines: &[String]) -> String {
    const LINES_PER_PAGE: usize = 48;
    let pages = lines.chunks(LINES_PER_PAGE).collect::<Vec<_>>();
    let page_count = pages.len().max(1);
    let first_page_object = 3;
    let font_object = first_page_object + page_count;
    let first_content_object = font_object + 1;
    let mut objects = Vec::new();
    objects.push("<< /Type /Catalog /Pages 2 0 R >>".to_owned());
    let kids = (0..page_count)
        .map(|index| format!("{} 0 R", first_page_object + index))
        .collect::<Vec<_>>()
        .join(" ");
    objects.push(format!(
        "<< /Type /Pages /Kids [{kids}] /Count {page_count} >>"
    ));
    for index in 0..page_count {
        objects.push(format!(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_object} 0 R >> >> /Contents {} 0 R >>",
            first_content_object + index
        ));
    }
    objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>".to_owned());
    for page in pages.iter().take(page_count) {
        let mut content = String::from("BT /F1 9 Tf 36 806 Td ");
        for (index, line) in page.iter().enumerate() {
            if index > 0 {
                content.push_str("0 -14 Td ");
            }
            content.push('(');
            content.push_str(&escape_pdf_text(line));
            content.push_str(") Tj ");
        }
        content.push_str("ET");
        objects.push(format!(
            "<< /Length {} >>\nstream\n{}\nendstream",
            content.len(),
            content
        ));
    }
    let mut pdf = String::from("%PDF-1.4\n");
    let mut offsets = vec![0usize];
    for (index, object) in objects.iter().enumerate() {
        offsets.push(pdf.len());
        pdf.push_str(&format!("{} 0 obj\n{}\nendobj\n", index + 1, object));
    }
    let xref_offset = pdf.len();
    pdf.push_str(&format!(
        "xref\n0 {}\n0000000000 65535 f \n",
        objects.len() + 1
    ));
    for offset in offsets.iter().skip(1) {
        pdf.push_str(&format!("{offset:010} 00000 n \n"));
    }
    pdf.push_str(&format!(
        "trailer\n<< /Size {} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n",
        objects.len() + 1
    ));
    pdf
}

fn escape_pdf_text(value: &str) -> String {
    value
        .bytes()
        .map(|byte| {
            if byte.is_ascii_graphic() || byte == b' ' {
                byte as char
            } else {
                '?'
            }
        })
        .collect::<String>()
        .replace('\\', "\\\\")
        .replace('(', "\\(")
        .replace(')', "\\)")
}
