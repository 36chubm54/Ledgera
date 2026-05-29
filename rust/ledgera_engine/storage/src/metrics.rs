use ledgera_engine_core::minor_to_money_value;
use rusqlite::Connection;
use std::cmp::Reverse;
use std::collections::{BTreeMap, HashMap};

use crate::{
    CategoryMetricRow, MetricsPeriodSnapshot, MetricsRefreshSnapshot, MonthlyCashflowRow,
    MonthlySummaryRow, StorageResult, TagCoverageRow, TagMetricRow, limit_clause,
    minor_amount_expr, round_money, sqlite_err, table_has_column, with_cached_read_connection,
};

fn sum_income_minor(conn: &Connection, start_date: &str, end_date: &str) -> StorageResult<i64> {
    let amount_expr = minor_amount_expr("amount_base");
    let sql = format!(
        "SELECT COALESCE(SUM({amount_expr}), 0) \
         FROM records \
         WHERE type = 'income' \
           AND transfer_id IS NULL \
           AND date >= ?1 AND date <= ?2"
    );
    conn.query_row(&sql, (start_date, end_date), |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)
}

fn sum_expense_minor(conn: &Connection, start_date: &str, end_date: &str) -> StorageResult<i64> {
    let amount_expr = minor_amount_expr("amount_base");
    let sql = format!(
        "SELECT COALESCE(SUM({amount_expr}), 0) \
         FROM records \
         WHERE type IN ('expense', 'mandatory_expense') \
           AND transfer_id IS NULL \
           AND date >= ?1 AND date <= ?2"
    );
    conn.query_row(&sql, (start_date, end_date), |row| row.get::<_, i64>(0))
        .map_err(sqlite_err)
}

fn savings_rate_for_conn(conn: &Connection, start_date: &str, end_date: &str) -> StorageResult<f64> {
    let income = minor_to_money_value(sum_income_minor(conn, start_date, end_date)?);
    let expenses = minor_to_money_value(sum_expense_minor(conn, start_date, end_date)?);
    Ok(savings_rate_from_totals(income, expenses))
}

fn savings_rate_from_totals(income: f64, expenses: f64) -> f64 {
    if income <= 0.0 {
        return 0.0;
    }
    round_money((income - expenses) / income * 100.0)
}

fn burn_rate_for_conn(
    conn: &Connection,
    start_date: &str,
    end_date: &str,
    days: i64,
) -> StorageResult<f64> {
    if days <= 0 {
        return Ok(0.0);
    }
    let expenses = minor_to_money_value(sum_expense_minor(conn, start_date, end_date)?);
    Ok(burn_rate_from_expenses(expenses, days))
}

fn burn_rate_from_expenses(expenses: f64, days: i64) -> f64 {
    if days <= 0 {
        return 0.0;
    }
    round_money(expenses / days as f64)
}

fn category_metric_rows_for_conn(
    conn: &Connection,
    record_type_filter: &str,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> StorageResult<Vec<CategoryMetricRow>> {
    let amount_expr = minor_amount_expr("amount_base");
    let sql = format!(
        "SELECT \
            category, \
            COALESCE(SUM({amount_expr}), 0) AS total_base, \
            COUNT(*) AS record_count \
         FROM records \
         WHERE {record_type_filter} \
           AND transfer_id IS NULL \
           AND date >= ?1 AND date <= ?2 \
         GROUP BY category \
         ORDER BY total_base DESC{}",
        limit_clause(limit)
    );
    let mut stmt = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = stmt
        .query_map((start_date, end_date), |row| {
            let total_minor: i64 = row.get(1)?;
            Ok(CategoryMetricRow {
                category: row.get(0)?,
                total_base: minor_to_money_value(total_minor),
                record_count: row.get(2)?,
            })
        })
        .map_err(sqlite_err)?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(sqlite_err)?);
    }
    Ok(result)
}

fn tag_metric_rows_for_conn(
    conn: &Connection,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> StorageResult<Vec<TagMetricRow>> {
    let amount_expr = minor_amount_expr("r.amount_base");
    let color_select = if table_has_column(conn, "tags", "color")? {
        "COALESCE(t.color, '')"
    } else {
        "''"
    };
    let color_group = if table_has_column(conn, "tags", "color")? {
        ", t.color"
    } else {
        ""
    };
    let sql = format!(
        "SELECT \
            t.name AS tag_name, \
            {color_select} AS color, \
            COALESCE(SUM({amount_expr}), 0) AS total_base, \
            COUNT(DISTINCT r.id) AS record_count \
         FROM records AS r \
         JOIN record_tags AS rt ON rt.record_id = r.id \
         JOIN tags AS t ON t.id = rt.tag_id \
         WHERE r.type IN ('expense', 'mandatory_expense') \
           AND r.transfer_id IS NULL \
           AND r.date >= ?1 AND r.date <= ?2 \
         GROUP BY t.id, t.name{color_group} \
         ORDER BY total_base DESC, t.name COLLATE NOCASE, t.name{}",
        limit_clause(limit)
    );
    let mut stmt = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = stmt
        .query_map((start_date, end_date), |row| {
            let total_minor: i64 = row.get(2)?;
            Ok(TagMetricRow {
                tag: row.get(0)?,
                color: row.get(1)?,
                total_base: minor_to_money_value(total_minor),
                record_count: row.get(3)?,
            })
        })
        .map_err(sqlite_err)?;

    let mut result = Vec::new();
    for row in rows {
        result.push(row.map_err(sqlite_err)?);
    }
    Ok(result)
}

fn has_record_tags(conn: &Connection) -> StorageResult<bool> {
    conn.query_row(
        "SELECT EXISTS(SELECT 1 FROM record_tags LIMIT 1)",
        [],
        |row| row.get::<_, bool>(0),
    )
    .map_err(sqlite_err)
}

type CategoryTotals = HashMap<String, (i64, i64, usize)>;

struct RefreshBaseRows {
    monthly_summary: Vec<MonthlySummaryRow>,
    spending_by_category: Vec<CategoryMetricRow>,
    income_by_category: Vec<CategoryMetricRow>,
    income_total: f64,
    expenses_total: f64,
}

fn category_rows_from_totals(
    totals: CategoryTotals,
    limit: Option<i64>,
) -> Vec<CategoryMetricRow> {
    let mut rows: Vec<(String, i64, i64, usize)> = totals
        .into_iter()
        .map(|(category, (total_minor, record_count, first_seen))| {
            (category, total_minor, record_count, first_seen)
        })
        .collect();
    rows.sort_by_key(|row| (Reverse(row.1), row.3));
    if let Some(max_len) = limit.and_then(|value| usize::try_from(value).ok()) {
        rows.truncate(max_len);
    }
    rows.into_iter()
        .map(|(category, total_minor, record_count, _first_seen)| CategoryMetricRow {
            category,
            total_base: minor_to_money_value(total_minor),
            record_count,
        })
        .collect()
}

fn metrics_refresh_base_for_conn(
    conn: &Connection,
    start_date: &str,
    end_date: &str,
    category_limit: Option<i64>,
) -> StorageResult<RefreshBaseRows> {
    let amount_expr = minor_amount_expr("amount_base");
    let sql = format!(
        "SELECT \
            CASE WHEN type = 'income' THEN 1 ELSE 0 END AS is_income, \
            substr(date, 1, 7) AS month, \
            category, \
            {amount_expr} AS amount_minor \
         FROM records \
         WHERE type IN ('income', 'expense', 'mandatory_expense') \
           AND transfer_id IS NULL \
           AND date >= ?1 AND date <= ?2"
    );
    let mut stmt = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = stmt
        .query_map((start_date, end_date), |row| {
            Ok((
                row.get::<_, bool>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })
        .map_err(sqlite_err)?;

    let mut monthly_totals: BTreeMap<String, (i64, i64)> = BTreeMap::new();
    let mut spending_totals: CategoryTotals = HashMap::new();
    let mut income_totals: CategoryTotals = HashMap::new();
    let mut income_total_minor = 0_i64;
    let mut expenses_total_minor = 0_i64;
    let mut category_order = 0_usize;

    for row in rows {
        let (is_income, month, category, amount_minor) = row.map_err(sqlite_err)?;
        let monthly = monthly_totals.entry(month).or_default();
        if is_income {
            monthly.0 += amount_minor;
            income_total_minor += amount_minor;
            let entry = income_totals.entry(category).or_insert_with(|| {
                let first_seen = category_order;
                category_order += 1;
                (0, 0, first_seen)
            });
            entry.0 += amount_minor;
            entry.1 += 1;
        } else {
            monthly.1 += amount_minor;
            expenses_total_minor += amount_minor;
            let entry = spending_totals.entry(category).or_insert_with(|| {
                let first_seen = category_order;
                category_order += 1;
                (0, 0, first_seen)
            });
            entry.0 += amount_minor;
            entry.1 += 1;
        }
    }

    let monthly_summary = monthly_totals
        .into_iter()
        .map(|(month, (income_minor, expenses_minor))| {
            let income = minor_to_money_value(income_minor);
            let expenses = minor_to_money_value(expenses_minor);
            let cashflow = round_money(income - expenses);
            let savings_rate = if income > 0.0 {
                round_money(cashflow / income * 100.0)
            } else {
                0.0
            };
            MonthlySummaryRow {
                month,
                income,
                expenses,
                cashflow,
                savings_rate,
            }
        })
        .collect();

    Ok(RefreshBaseRows {
        monthly_summary,
        spending_by_category: category_rows_from_totals(spending_totals, category_limit),
        income_by_category: category_rows_from_totals(income_totals, category_limit),
        income_total: minor_to_money_value(income_total_minor),
        expenses_total: minor_to_money_value(expenses_total_minor),
    })
}

fn tag_coverage_for_conn(
    conn: &Connection,
    start_date: &str,
    end_date: &str,
) -> StorageResult<TagCoverageRow> {
    let total_count = conn
        .query_row(
            "SELECT COUNT(*) \
             FROM records \
             WHERE type IN ('expense', 'mandatory_expense') \
               AND transfer_id IS NULL \
               AND date >= ?1 AND date <= ?2",
            (start_date, end_date),
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)?;
    let tagged_count = conn
        .query_row(
            "SELECT COUNT(DISTINCT r.id) \
             FROM records AS r \
             JOIN record_tags AS rt ON rt.record_id = r.id \
             WHERE r.type IN ('expense', 'mandatory_expense') \
               AND r.transfer_id IS NULL \
               AND r.date >= ?1 AND r.date <= ?2",
            (start_date, end_date),
            |row| row.get::<_, i64>(0),
        )
        .map_err(sqlite_err)?;
    let coverage_pct = if total_count > 0 {
        round_money(tagged_count as f64 / total_count as f64 * 100.0)
    } else {
        0.0
    };
    Ok(TagCoverageRow {
        tagged_count,
        total_count,
        coverage_pct,
    })
}

fn category_metric_groups_for_conn(
    conn: &Connection,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> StorageResult<(Vec<CategoryMetricRow>, Vec<CategoryMetricRow>)> {
    let amount_expr = minor_amount_expr("amount_base");
    let sql = format!(
        "SELECT \
            CASE WHEN type = 'income' THEN 'income' ELSE 'expense' END AS metric_kind, \
            category, \
            COALESCE(SUM({amount_expr}), 0) AS total_base, \
            COUNT(*) AS record_count \
         FROM records \
         WHERE type IN ('income', 'expense', 'mandatory_expense') \
           AND transfer_id IS NULL \
           AND date >= ?1 AND date <= ?2 \
         GROUP BY metric_kind, category \
         ORDER BY metric_kind, total_base DESC"
    );
    let mut stmt = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = stmt
        .query_map((start_date, end_date), |row| {
            let total_minor: i64 = row.get(2)?;
            Ok((
                row.get::<_, String>(0)?,
                CategoryMetricRow {
                    category: row.get(1)?,
                    total_base: minor_to_money_value(total_minor),
                    record_count: row.get(3)?,
                },
            ))
        })
        .map_err(sqlite_err)?;

    let mut spending = Vec::new();
    let mut income = Vec::new();
    let max_len = limit.and_then(|value| usize::try_from(value).ok());
    for row in rows {
        let (metric_kind, metric_row) = row.map_err(sqlite_err)?;
        let target = if metric_kind == "income" {
            &mut income
        } else {
            &mut spending
        };
        if max_len.is_none_or(|value| target.len() < value) {
            target.push(metric_row);
        }
    }
    Ok((spending, income))
}

pub(crate) fn monthly_summary_for_conn(
    conn: &Connection,
    start_date: Option<&str>,
    end_date: Option<&str>,
) -> StorageResult<Vec<MonthlySummaryRow>> {
    let amount_expr = minor_amount_expr("amount_base");
    let mut sql = format!(
        "SELECT \
            strftime('%Y-%m', date) AS month, \
            COALESCE(SUM(CASE type WHEN 'income' THEN {amount_expr} ELSE 0 END), 0) AS income, \
            COALESCE(SUM(CASE WHEN type IN ('expense', 'mandatory_expense') THEN {amount_expr} ELSE 0 END), 0) AS expenses \
         FROM records \
         WHERE transfer_id IS NULL"
    );
    if start_date.is_some() {
        sql.push_str(" AND date >= ?1");
    }
    if end_date.is_some() {
        sql.push_str(if start_date.is_some() {
            " AND date <= ?2"
        } else {
            " AND date <= ?1"
        });
    }
    sql.push_str(" GROUP BY strftime('%Y-%m', date) ORDER BY month");

    let mut stmt = conn.prepare(&sql).map_err(sqlite_err)?;
    let mapper = |row: &rusqlite::Row<'_>| -> rusqlite::Result<MonthlySummaryRow> {
        let income = minor_to_money_value(row.get::<_, i64>(1)?);
        let expenses = minor_to_money_value(row.get::<_, i64>(2)?);
        let cashflow = round_money(income - expenses);
        let savings_rate = if income > 0.0 {
            round_money(cashflow / income * 100.0)
        } else {
            0.0
        };
        Ok(MonthlySummaryRow {
            month: row.get(0)?,
            income,
            expenses,
            cashflow,
            savings_rate,
        })
    };
    let mut result = Vec::new();
    match (start_date, end_date) {
        (Some(start), Some(end)) => {
            for row in stmt.query_map((start, end), mapper).map_err(sqlite_err)? {
                result.push(row.map_err(sqlite_err)?);
            }
        }
        (Some(start), None) => {
            for row in stmt.query_map([start], mapper).map_err(sqlite_err)? {
                result.push(row.map_err(sqlite_err)?);
            }
        }
        (None, Some(end)) => {
            for row in stmt.query_map([end], mapper).map_err(sqlite_err)? {
                result.push(row.map_err(sqlite_err)?);
            }
        }
        (None, None) => {
            for row in stmt.query_map([], mapper).map_err(sqlite_err)? {
                result.push(row.map_err(sqlite_err)?);
            }
        }
    }
    Ok(result)
}

pub fn metrics_savings_rate(db_path: &str, start_date: &str, end_date: &str) -> StorageResult<f64> {
    with_cached_read_connection(db_path, |conn| {
        savings_rate_for_conn(conn, start_date, end_date)
    })
}

pub fn metrics_burn_rate(
    db_path: &str,
    start_date: &str,
    end_date: &str,
    days: i64,
) -> StorageResult<f64> {
    with_cached_read_connection(db_path, |conn| {
        burn_rate_for_conn(conn, start_date, end_date, days)
    })
}

pub fn metrics_spending_by_category(
    db_path: &str,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> StorageResult<Vec<CategoryMetricRow>> {
    with_cached_read_connection(db_path, |conn| {
        category_metric_rows_for_conn(
            conn,
            "type IN ('expense', 'mandatory_expense')",
            start_date,
            end_date,
            limit,
        )
    })
}

pub fn metrics_income_by_category(
    db_path: &str,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> StorageResult<Vec<CategoryMetricRow>> {
    with_cached_read_connection(db_path, |conn| {
        category_metric_rows_for_conn(conn, "type = 'income'", start_date, end_date, limit)
    })
}

pub fn metrics_spending_by_tag(
    db_path: &str,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> StorageResult<Vec<TagMetricRow>> {
    with_cached_read_connection(db_path, |conn| {
        tag_metric_rows_for_conn(conn, start_date, end_date, limit)
    })
}

pub fn metrics_tag_coverage(
    db_path: &str,
    start_date: &str,
    end_date: &str,
) -> StorageResult<TagCoverageRow> {
    with_cached_read_connection(db_path, |conn| {
        tag_coverage_for_conn(conn, start_date, end_date)
    })
}

pub fn metrics_monthly_summary(
    db_path: &str,
    start_date: Option<&str>,
    end_date: Option<&str>,
) -> StorageResult<Vec<MonthlySummaryRow>> {
    with_cached_read_connection(db_path, |conn| {
        monthly_summary_for_conn(conn, start_date, end_date)
    })
}

pub fn metrics_period_snapshot(
    db_path: &str,
    start_date: &str,
    end_date: &str,
    days: i64,
    category_limit: Option<i64>,
    tag_limit: Option<i64>,
) -> StorageResult<MetricsPeriodSnapshot> {
    with_cached_read_connection(db_path, |conn| {
        let monthly_summary = monthly_summary_for_conn(conn, Some(start_date), Some(end_date))?;
        let income_total: f64 = monthly_summary.iter().map(|row| row.income).sum();
        let expenses_total: f64 = monthly_summary.iter().map(|row| row.expenses).sum();
        let (spending_by_category, income_by_category) =
            category_metric_groups_for_conn(conn, start_date, end_date, category_limit)?;
        let monthly_cashflow = monthly_summary
            .iter()
            .map(|row| MonthlyCashflowRow {
                month: row.month.clone(),
                income: row.income,
                expenses: row.expenses,
                cashflow: row.cashflow,
            })
            .collect();
        Ok(MetricsPeriodSnapshot {
            savings_rate: savings_rate_from_totals(income_total, expenses_total),
            burn_rate: burn_rate_from_expenses(expenses_total, days),
            spending_by_category,
            income_by_category,
            spending_by_tag: tag_metric_rows_for_conn(conn, start_date, end_date, tag_limit)?,
            tag_coverage: tag_coverage_for_conn(conn, start_date, end_date)?,
            monthly_summary,
            monthly_cashflow,
        })
    })
}

pub fn metrics_refresh_snapshot(
    db_path: &str,
    start_date: &str,
    end_date: &str,
    days: i64,
    category_limit: Option<i64>,
    tag_limit: Option<i64>,
) -> StorageResult<MetricsRefreshSnapshot> {
    with_cached_read_connection(db_path, |conn| {
        let base = metrics_refresh_base_for_conn(conn, start_date, end_date, category_limit)?;
        let spending_by_tag = if has_record_tags(conn)? {
            tag_metric_rows_for_conn(conn, start_date, end_date, tag_limit)?
        } else {
            Vec::new()
        };
        Ok(MetricsRefreshSnapshot {
            savings_rate: savings_rate_from_totals(base.income_total, base.expenses_total),
            burn_rate: burn_rate_from_expenses(base.expenses_total, days),
            spending_by_category: base.spending_by_category,
            income_by_category: base.income_by_category,
            spending_by_tag,
            monthly_summary: base.monthly_summary,
        })
    })
}
