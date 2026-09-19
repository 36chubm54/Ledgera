use crate::{
    AnalyticsBreakdownRow, AnalyticsCapitalPoint, AnalyticsDailyRow, AnalyticsFilters,
    AnalyticsMonthlyRow, AnalyticsSnapshot, AnalyticsSummary, StorageResult, minor_amount_expr,
    minor_to_money_value, round_money, signed_minor_amount_expr, sqlite_err,
    with_cached_read_connection,
};
use rusqlite::{Connection, params_from_iter, types::Value};

fn validate_period(start: &str, end: &str) -> StorageResult<()> {
    fn valid_date(value: &str) -> bool {
        if value.len() != 10 || !value.is_ascii() {
            return false;
        }
        let bytes = value.as_bytes();
        if bytes[4] != b'-' || bytes[7] != b'-' {
            return false;
        }
        let year = match value[0..4].parse::<i32>() {
            Ok(value) => value,
            Err(_) => return false,
        };
        let month = match value[5..7].parse::<u32>() {
            Ok(value) => value,
            Err(_) => return false,
        };
        let day = match value[8..10].parse::<u32>() {
            Ok(value) => value,
            Err(_) => return false,
        };
        let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
        let days_in_month = match month {
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            4 | 6 | 9 | 11 => 30,
            2 if leap => 29,
            2 => 28,
            _ => 0,
        };
        days_in_month > 0 && (1..=days_in_month).contains(&day)
    }

    if !valid_date(start) || !valid_date(end) {
        return Err("Analytics dates must use YYYY-MM-DD".to_owned());
    }
    if start > end {
        return Err("Analytics start date must not be after end date".to_owned());
    }
    Ok(())
}

fn group_other(mut rows: Vec<AnalyticsBreakdownRow>) -> Vec<AnalyticsBreakdownRow> {
    const MAX_SLICES: usize = 10;
    if rows.len() <= MAX_SLICES {
        return rows;
    }
    let tail = rows.split_off(MAX_SLICES - 1);
    let amount_base = tail.iter().map(|row| row.amount_base).sum();
    let record_count = tail.iter().map(|row| row.record_count).sum();
    rows.push(AnalyticsBreakdownRow {
        label: "Other".to_owned(),
        amount_base: round_money(amount_base),
        record_count,
        color: String::new(),
        is_other: true,
    });
    rows
}

fn record_predicate(filters: &AnalyticsFilters, alias: &str) -> (String, Vec<Value>) {
    let column = |name: &str| format!("{alias}{name}");
    let mut values = vec![
        Value::Text(filters.period_start.clone()),
        Value::Text(filters.period_end.clone()),
    ];
    let mut predicate = format!("{}date >= ?1 AND {}date <= ?2", column(""), column(""));
    if let Some(wallet_id) = filters.wallet_id {
        values.push(Value::Integer(wallet_id));
        predicate.push_str(&format!(" AND {}wallet_id = ?{}", column(""), values.len()));
    }
    if !filters.category.trim().is_empty() {
        values.push(Value::Text(filters.category.trim().to_owned()));
        predicate.push_str(&format!(" AND {}category = ?{}", column(""), values.len()));
    }
    let tags: Vec<String> = filters
        .tag
        .split(',')
        .map(str::trim)
        .filter(|tag| !tag.is_empty())
        .map(str::to_owned)
        .collect();
    if !tags.is_empty() {
        let mut clauses = Vec::with_capacity(tags.len());
        for tag in tags {
            values.push(Value::Text(tag));
            let placeholder = values.len();
            clauses.push(format!(
                "EXISTS (SELECT 1 FROM record_tags filter_rt JOIN tags filter_t ON filter_t.id = filter_rt.tag_id WHERE filter_rt.record_id = {}id AND filter_t.name = ?{})",
                column(""),
                placeholder
            ));
        }
        let joiner = if filters.tag_mode == "and" {
            " AND "
        } else {
            " OR "
        };
        predicate.push_str(" AND (");
        predicate.push_str(&clauses.join(joiner));
        predicate.push(')');
    }
    (predicate, values)
}

fn breakdown_rows(
    conn: &Connection,
    filters: &AnalyticsFilters,
    record_type: &str,
) -> StorageResult<Vec<AnalyticsBreakdownRow>> {
    let amount = minor_amount_expr("amount_base");
    let (predicate, params) = record_predicate(filters, "");
    let sql = format!(
        "SELECT category, COALESCE(SUM({amount}), 0), COUNT(*)\
         FROM records WHERE {record_type} AND transfer_id IS NULL\
         AND category <> 'Transfer' AND {predicate}\
         GROUP BY category ORDER BY 2 DESC, category COLLATE NOCASE, category"
    );
    let mut statement = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = statement
        .query_map(params_from_iter(params.iter()), |row| {
            let minor: i64 = row.get(1)?;
            Ok(AnalyticsBreakdownRow {
                label: row.get(0)?,
                amount_base: minor_to_money_value(minor),
                record_count: row.get(2)?,
                color: String::new(),
                is_other: false,
            })
        })
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn tag_rows(
    conn: &Connection,
    filters: &AnalyticsFilters,
) -> StorageResult<Vec<AnalyticsBreakdownRow>> {
    let amount = minor_amount_expr("r.amount_base");
    let (predicate, params) = record_predicate(filters, "r.");
    let sql = format!(
        "SELECT t.name, COALESCE(t.color, ''), COALESCE(SUM({amount}), 0), COUNT(DISTINCT r.id)\
         FROM records r JOIN record_tags rt ON rt.record_id = r.id JOIN tags t ON t.id = rt.tag_id\
         WHERE r.type IN ('expense', 'mandatory_expense') AND r.transfer_id IS NULL\
         AND r.category <> 'Transfer' AND {predicate}\
         GROUP BY t.id, t.name, t.color ORDER BY 3 DESC, t.name COLLATE NOCASE, t.name"
    );
    let mut statement = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = statement
        .query_map(params_from_iter(params.iter()), |row| {
            let minor: i64 = row.get(2)?;
            Ok(AnalyticsBreakdownRow {
                label: row.get(0)?,
                amount_base: minor_to_money_value(minor),
                record_count: row.get(3)?,
                color: row.get(1)?,
                is_other: false,
            })
        })
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn monthly_rows(
    conn: &Connection,
    filters: &AnalyticsFilters,
) -> StorageResult<Vec<AnalyticsMonthlyRow>> {
    let amount = minor_amount_expr("amount_base");
    let (predicate, params) = record_predicate(filters, "");
    let sql = format!(
        "SELECT substr(date, 1, 7),\
         COALESCE(SUM(CASE WHEN type = 'income' THEN {amount} ELSE 0 END), 0),\
         COALESCE(SUM(CASE WHEN type IN ('expense', 'mandatory_expense') THEN {amount} ELSE 0 END), 0)\
         FROM records WHERE transfer_id IS NULL AND category <> 'Transfer'\
         AND type IN ('income', 'expense', 'mandatory_expense')\
         AND {predicate} GROUP BY substr(date, 1, 7) ORDER BY 1"
    );
    let mut statement = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = statement
        .query_map(params_from_iter(params.iter()), |row| {
            let income = minor_to_money_value(row.get::<_, i64>(1)?);
            let expenses = minor_to_money_value(row.get::<_, i64>(2)?);
            let cashflow = round_money(income - expenses);
            Ok(AnalyticsMonthlyRow {
                month: row.get(0)?,
                income_base: income,
                expenses_base: expenses,
                cashflow_base: cashflow,
                savings_rate: if income > 0.0 {
                    round_money(cashflow / income * 100.0)
                } else {
                    0.0
                },
            })
        })
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn daily_rows(
    conn: &Connection,
    filters: &AnalyticsFilters,
) -> StorageResult<Vec<AnalyticsDailyRow>> {
    let amount = minor_amount_expr("amount_base");
    let (predicate, params) = record_predicate(filters, "");
    let sql = format!(
        "SELECT date, COALESCE(SUM(CASE WHEN type = 'income' THEN {amount} ELSE 0 END), 0),\
         COALESCE(SUM(CASE WHEN type IN ('expense', 'mandatory_expense') THEN {amount} ELSE 0 END), 0)\
         FROM records WHERE transfer_id IS NULL AND category <> 'Transfer'\
         AND type IN ('income', 'expense', 'mandatory_expense')\
         AND {predicate} GROUP BY date ORDER BY date"
    );
    let mut statement = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = statement
        .query_map(params_from_iter(params.iter()), |row| {
            Ok(AnalyticsDailyRow {
                day: row.get(0)?,
                income_base: minor_to_money_value(row.get::<_, i64>(1)?),
                expenses_base: minor_to_money_value(row.get::<_, i64>(2)?),
            })
        })
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn capital_rows(conn: &Connection) -> StorageResult<Vec<(String, i64)>> {
    let signed = signed_minor_amount_expr("amount_base", "type");
    let sql = format!(
        "SELECT month, SUM(monthly_delta) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)\
         FROM (SELECT substr(date, 1, 7) AS month, COALESCE(SUM({signed}), 0) AS monthly_delta\
         FROM records GROUP BY substr(date, 1, 7) ORDER BY month)"
    );
    let mut statement = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = statement
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn summary(
    conn: &Connection,
    filters: &AnalyticsFilters,
    monthly: &[AnalyticsMonthlyRow],
) -> StorageResult<AnalyticsSummary> {
    let amount = minor_amount_expr("amount_base");
    let (predicate, params) = record_predicate(filters, "");
    let (income_minor, expense_minor): (i64, i64) = conn
        .query_row(
            &format!("SELECT COALESCE(SUM(CASE WHEN type = 'income' THEN {amount} ELSE 0 END), 0), COALESCE(SUM(CASE WHEN type IN ('expense', 'mandatory_expense') THEN {amount} ELSE 0 END), 0) FROM records WHERE transfer_id IS NULL AND category <> 'Transfer' AND type IN ('income', 'expense', 'mandatory_expense') AND {predicate}"),
            params_from_iter(params.iter()),
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .map_err(sqlite_err)?;
    let income = minor_to_money_value(income_minor);
    let expenses = minor_to_money_value(expense_minor);
    let days: f64 = conn
        .query_row(
            "SELECT julianday(?2) - julianday(?1) + 1",
            (filters.period_start.as_str(), filters.period_end.as_str()),
            |row| row.get(0),
        )
        .map_err(sqlite_err)?;
    let initial_minor: i64 = conn
        .query_row("SELECT COALESCE(SUM(COALESCE(initial_balance_minor, CAST(ROUND(initial_balance * 100.0) AS INTEGER), 0)), 0) FROM wallets WHERE is_active = 1", [], |row| row.get(0))
        .map_err(sqlite_err)?;
    let signed = crate::signed_minor_amount_expr("r.amount_base", "r.type");
    let delta_minor: i64 = conn
        .query_row(
            &format!("SELECT COALESCE(SUM({signed}), 0) FROM records r WHERE r.date <= ?1"),
            [filters.period_end.as_str()],
            |row| row.get(0),
        )
        .map_err(sqlite_err)?;
    let year = filters.period_end.get(0..4).unwrap_or("");
    let year_income: i64 = conn.query_row(&format!("SELECT COALESCE(SUM(CASE WHEN type = 'income' THEN {amount} ELSE 0 END), 0) FROM records WHERE transfer_id IS NULL AND category <> 'Transfer' AND substr(date,1,4)=?1"), [year], |row| row.get(0)).map_err(sqlite_err)?;
    let year_expense: i64 = conn.query_row(&format!("SELECT COALESCE(SUM(CASE WHEN type IN ('expense','mandatory_expense') THEN {amount} ELSE 0 END), 0) FROM records WHERE transfer_id IS NULL AND category <> 'Transfer' AND substr(date,1,4)=?1"), [year], |row| row.get(0)).map_err(sqlite_err)?;
    Ok(AnalyticsSummary {
        net_worth_base: minor_to_money_value(initial_minor + delta_minor),
        savings_rate: if income > 0.0 {
            round_money((income - expenses) / income * 100.0)
        } else {
            0.0
        },
        burn_rate: if days > 0.0 {
            round_money(expenses / days)
        } else {
            0.0
        },
        average_monthly_income: if monthly.is_empty() {
            0.0
        } else {
            round_money(
                monthly.iter().map(|row| row.income_base).sum::<f64>() / monthly.len() as f64,
            )
        },
        average_monthly_expenses: if monthly.is_empty() {
            0.0
        } else {
            round_money(
                monthly.iter().map(|row| row.expenses_base).sum::<f64>() / monthly.len() as f64,
            )
        },
        year_income: minor_to_money_value(year_income),
        year_expense: minor_to_money_value(year_expense),
    })
}

pub fn analytics_generate(
    db_path: &str,
    filters: &AnalyticsFilters,
) -> StorageResult<AnalyticsSnapshot> {
    validate_period(&filters.period_start, &filters.period_end)?;
    if !matches!(filters.breakdown_mode.as_str(), "category" | "tag") {
        return Err("Analytics breakdown mode must be category or tag".to_owned());
    }
    with_cached_read_connection(db_path, |conn| {
        let monthly = monthly_rows(conn, filters)?;
        let categories = group_other(breakdown_rows(
            conn,
            filters,
            "type IN ('expense', 'mandatory_expense')",
        )?);
        let tags = group_other(tag_rows(conn, filters)?);
        let infographic_monthly = monthly.clone();
        let initial_minor: i64 = conn
            .query_row(
                "SELECT COALESCE(SUM(COALESCE(initial_balance_minor, CAST(ROUND(initial_balance * 100.0) AS INTEGER), 0)), 0) FROM wallets WHERE is_active = 1",
                [],
                |row| row.get(0),
            )
            .map_err(sqlite_err)?;
        let capital = capital_rows(conn)?
            .into_iter()
            .map(|row| AnalyticsCapitalPoint {
                month: row.0,
                balance_base: minor_to_money_value(initial_minor + row.1),
            })
            .collect();
        Ok(AnalyticsSnapshot {
            summary: summary(conn, filters, &monthly)?,
            capital,
            categories,
            tags,
            monthly,
            daily: daily_rows(conn, filters)?,
            infographic_monthly,
        })
    })
}

pub fn analytics_list_categories(
    db_path: &str,
    start: &str,
    end: &str,
) -> StorageResult<Vec<String>> {
    validate_period(start, end)?;
    with_cached_read_connection(db_path, |conn| {
        let mut statement = conn.prepare("SELECT DISTINCT category FROM records WHERE type IN ('income', 'expense', 'mandatory_expense') AND transfer_id IS NULL AND category <> 'Transfer' AND date >= ?1 AND date <= ?2 AND trim(category) <> '' ORDER BY category COLLATE NOCASE, category").map_err(sqlite_err)?;
        let rows = statement
            .query_map((start, end), |row| row.get(0))
            .map_err(sqlite_err)?;
        rows.map(|row| row.map_err(sqlite_err)).collect()
    })
}

pub fn analytics_list_tags(db_path: &str, start: &str, end: &str) -> StorageResult<Vec<String>> {
    validate_period(start, end)?;
    with_cached_read_connection(db_path, |conn| {
        let mut statement = conn.prepare("SELECT DISTINCT t.name FROM tags t JOIN record_tags rt ON rt.tag_id = t.id JOIN records r ON r.id = rt.record_id WHERE r.type IN ('expense', 'mandatory_expense') AND r.transfer_id IS NULL AND r.category <> 'Transfer' AND r.date >= ?1 AND r.date <= ?2 AND trim(t.name) <> '' ORDER BY t.name COLLATE NOCASE, t.name").map_err(sqlite_err)?;
        let rows = statement
            .query_map((start, end), |row| row.get(0))
            .map_err(sqlite_err)?;
        rows.map(|row| row.map_err(sqlite_err)).collect()
    })
}

#[cfg(test)]
mod tests {
    use super::{group_other, validate_period};
    use crate::AnalyticsBreakdownRow;

    #[test]
    fn rejects_impossible_calendar_dates() {
        assert!(validate_period("2024-02-29", "2024-03-01").is_ok());
        assert!(validate_period("2023-02-29", "2023-03-01").is_err());
        assert!(validate_period("2026-04-31", "2026-05-01").is_err());
    }

    #[test]
    fn groups_breakdown_after_nine_rows() {
        let rows = (0..11)
            .map(|index| AnalyticsBreakdownRow {
                label: format!("Category {index}"),
                amount_base: 1.0,
                record_count: 1,
                color: String::new(),
                is_other: false,
            })
            .collect();
        let grouped = group_other(rows);
        assert_eq!(grouped.len(), 10);
        assert_eq!(grouped[9].label, "Other");
        assert!(grouped[9].is_other);
        assert_eq!(grouped[9].amount_base, 2.0);
    }
}
