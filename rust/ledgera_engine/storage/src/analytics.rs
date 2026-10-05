use std::collections::HashMap;

use crate::{
    minor_amount_expr, minor_to_money_value, round_money, sqlite_err, with_cached_read_connection,
    AnalyticsBreakdownDetail, AnalyticsBreakdownRow, AnalyticsCapitalPoint, AnalyticsDailyRow,
    AnalyticsFilters, AnalyticsMonthlyRow, AnalyticsSnapshot, AnalyticsSummary, StorageResult,
};
use rusqlite::{params_from_iter, types::Value, Connection};

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
    let details = tail
        .iter()
        .map(|row| AnalyticsBreakdownDetail {
            label: row.label.clone(),
            amount_base: row.amount_base,
            record_count: row.record_count,
        })
        .collect();
    rows.push(AnalyticsBreakdownRow {
        label: "Other".to_owned(),
        amount_base: round_money(amount_base),
        record_count,
        color: String::new(),
        is_other: true,
        details,
    });
    rows
}

fn current_rate_case(column: &str, rates: &HashMap<String, f64>) -> String {
    let mut cases = String::new();
    for (currency, rate) in rates {
        cases.push_str(&format!(
            " WHEN '{}' THEN {rate:.12}",
            currency.replace('\'', "''")
        ));
    }
    format!("CASE UPPER({column}){cases} ELSE NULL END")
}

fn amount_expression(
    filters: &AnalyticsFilters,
    prefix: &str,
    current_rates: Option<&HashMap<String, f64>>,
) -> String {
    if filters.totals_mode == "current" {
        format!(
            "CAST(ROUND({prefix}amount_original * 100.0 * {}) AS INTEGER)",
            current_rate_case(
                &format!("{prefix}currency"),
                current_rates.expect("current rates are validated before analytics queries"),
            )
        )
    } else {
        minor_amount_expr(&format!("{prefix}amount_base"))
    }
}

fn signed_amount_expression(
    filters: &AnalyticsFilters,
    prefix: &str,
    current_rates: Option<&HashMap<String, f64>>,
) -> String {
    let amount = amount_expression(filters, prefix, current_rates);
    format!("CASE WHEN {prefix}type = 'income' THEN {amount} ELSE -{amount} END")
}

fn period_for(value: &str) -> (String, String) {
    if value.is_empty() || value.eq_ignore_ascii_case("all_time") {
        return ("0000-01-01".to_owned(), "9999-12-31".to_owned());
    }
    if value.len() == 7 {
        let year = value
            .get(0..4)
            .and_then(|year| year.parse::<i32>().ok())
            .unwrap_or(0);
        let month = value
            .get(5..7)
            .and_then(|month| month.parse::<u32>().ok())
            .unwrap_or(1);
        let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
        let end_day = match month {
            2 if leap => 29,
            2 => 28,
            4 | 6 | 9 | 11 => 30,
            _ => 31,
        };
        return (format!("{value}-01"), format!("{value}-{end_day:02}"));
    }
    (format!("{value}-01-01"), format!("{value}-12-31"))
}

fn validate_infographic_periods(filters: &AnalyticsFilters) -> StorageResult<()> {
    let pie = filters.pie_period.trim();
    if !pie.is_empty() && !pie.eq_ignore_ascii_case("all_time") {
        if pie.len() != 7 {
            return Err("Analytics pie period must use YYYY-MM or all_time".to_owned());
        }
        let range = period_for(pie);
        validate_period(&range.0, &range.1)?;
    }
    let daily = filters.daily_month.trim();
    if !daily.is_empty() {
        if daily.len() != 7 {
            return Err("Analytics daily month must use YYYY-MM".to_owned());
        }
        let range = period_for(daily);
        validate_period(&range.0, &range.1)?;
    }
    let yearly = filters.monthly_year.trim();
    if !yearly.is_empty() {
        if yearly.len() != 4 {
            return Err("Analytics monthly year must use YYYY".to_owned());
        }
        let range = period_for(yearly);
        validate_period(&range.0, &range.1)?;
    }
    Ok(())
}

fn with_period(filters: &AnalyticsFilters, start: String, end: String) -> AnalyticsFilters {
    let mut copy = filters.clone();
    copy.period_start = start;
    copy.period_end = end;
    copy.category.clear();
    copy.tag.clear();
    copy.wallet_id = None;
    copy
}

fn categories_from_conn(conn: &Connection, start: &str, end: &str) -> StorageResult<Vec<String>> {
    let mut statement = conn.prepare("SELECT DISTINCT category FROM records WHERE type IN ('income', 'expense', 'mandatory_expense') AND transfer_id IS NULL AND category <> 'Transfer' AND date >= ?1 AND date <= ?2 AND trim(category) <> '' ORDER BY category COLLATE NOCASE, category").map_err(sqlite_err)?;
    let rows = statement
        .query_map((start, end), |row| row.get(0))
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn tags_from_conn(conn: &Connection, start: &str, end: &str) -> StorageResult<Vec<String>> {
    let mut statement = conn.prepare("SELECT DISTINCT t.name FROM tags t JOIN record_tags rt ON rt.tag_id = t.id JOIN records r ON r.id = rt.record_id WHERE r.type IN ('expense', 'mandatory_expense') AND r.transfer_id IS NULL AND r.category <> 'Transfer' AND r.date >= ?1 AND r.date <= ?2 AND trim(t.name) <> '' ORDER BY t.name COLLATE NOCASE, t.name").map_err(sqlite_err)?;
    let rows = statement
        .query_map((start, end), |row| row.get(0))
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn months_from_conn(conn: &Connection) -> StorageResult<Vec<String>> {
    let mut statement = conn
        .prepare("SELECT DISTINCT substr(date, 1, 7) FROM records ORDER BY 1")
        .map_err(sqlite_err)?;
    let rows = statement
        .query_map([], |row| row.get(0))
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn years_from_conn(conn: &Connection) -> StorageResult<Vec<String>> {
    let mut statement = conn
        .prepare("SELECT DISTINCT substr(date, 1, 4) FROM records ORDER BY 1")
        .map_err(sqlite_err)?;
    let rows = statement
        .query_map([], |row| row.get(0))
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn load_current_rates(
    db_path: &str,
    conn: &Connection,
    filters: &AnalyticsFilters,
) -> StorageResult<HashMap<String, f64>> {
    let rates = crate::current_currency_rates(db_path)?;
    let rates = rates;
    let mut statement = conn
        .prepare("SELECT DISTINCT UPPER(currency) FROM records WHERE trim(currency) <> '' AND date <= ?1")
        .map_err(sqlite_err)?;
    let currencies = statement
        .query_map([filters.period_end.as_str()], |row| row.get::<_, String>(0))
        .map_err(sqlite_err)?;
    for currency in currencies {
        let currency = currency.map_err(sqlite_err)?;
        if !rates.contains_key(&currency) {
            return Err(format!(
                "Current-rate analytics has no usable rate for currency {currency}"
            ));
        }
    }
    Ok(rates)
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
    current_rates: Option<&HashMap<String, f64>>,
) -> StorageResult<Vec<AnalyticsBreakdownRow>> {
    let amount = amount_expression(filters, "", current_rates);
    let (predicate, params) = record_predicate(filters, "");
    let sql = format!(
        "SELECT category, COALESCE(SUM({amount}), 0), COUNT(*) \
         FROM records WHERE {record_type} AND transfer_id IS NULL \
         AND category <> 'Transfer' AND {predicate} \
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
                details: Vec::new(),
            })
        })
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn tag_rows(
    conn: &Connection,
    filters: &AnalyticsFilters,
    current_rates: Option<&HashMap<String, f64>>,
) -> StorageResult<Vec<AnalyticsBreakdownRow>> {
    let amount = amount_expression(filters, "r.", current_rates);
    let (predicate, params) = record_predicate(filters, "r.");
    let sql = format!(
        "SELECT t.name, COALESCE(t.color, ''), COALESCE(SUM({amount}), 0), COUNT(DISTINCT r.id) \
         FROM records r JOIN record_tags rt ON rt.record_id = r.id JOIN tags t ON t.id = rt.tag_id \
         WHERE r.type IN ('expense', 'mandatory_expense') AND r.transfer_id IS NULL \
         AND r.category <> 'Transfer' AND {predicate} \
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
                details: Vec::new(),
            })
        })
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn monthly_rows(
    conn: &Connection,
    filters: &AnalyticsFilters,
    current_rates: Option<&HashMap<String, f64>>,
) -> StorageResult<Vec<AnalyticsMonthlyRow>> {
    let amount = amount_expression(filters, "", current_rates);
    let (predicate, params) = record_predicate(filters, "");
    let sql = format!(
        r#"WITH RECURSIVE months(month_start) AS (
             SELECT date(?1, 'start of month')
             UNION ALL
             SELECT date(month_start, '+1 month') FROM months
             WHERE month_start < date(?2, 'start of month')
         ), aggregated AS (
             SELECT substr(date, 1, 7) AS month,
             COALESCE(SUM(CASE WHEN type = 'income' THEN {amount} ELSE 0 END), 0) AS income,
             COALESCE(SUM(CASE WHEN type IN ('expense', 'mandatory_expense') THEN {amount} ELSE 0 END), 0) AS expenses
             FROM records WHERE transfer_id IS NULL AND category <> 'Transfer'
             AND type IN ('income', 'expense', 'mandatory_expense')
             AND {predicate} GROUP BY substr(date, 1, 7)
         )
         SELECT strftime('%Y-%m', months.month_start),
         COALESCE(aggregated.income, 0), COALESCE(aggregated.expenses, 0)
         FROM months LEFT JOIN aggregated
         ON aggregated.month = strftime('%Y-%m', months.month_start)
         ORDER BY months.month_start"#
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
    current_rates: Option<&HashMap<String, f64>>,
) -> StorageResult<Vec<AnalyticsDailyRow>> {
    let amount = amount_expression(filters, "", current_rates);
    let (predicate, params) = record_predicate(filters, "");
    let sql = format!(
        r#"WITH RECURSIVE days(day) AS (
             SELECT ?1
             UNION ALL
             SELECT date(day, '+1 day') FROM days WHERE day < ?2
         ), aggregated AS (
             SELECT date,
             COALESCE(SUM(CASE WHEN type = 'income' THEN {amount} ELSE 0 END), 0) AS income,
             COALESCE(SUM(CASE WHEN type IN ('expense', 'mandatory_expense') THEN {amount} ELSE 0 END), 0) AS expenses
             FROM records WHERE transfer_id IS NULL AND category <> 'Transfer'
             AND type IN ('income', 'expense', 'mandatory_expense')
             AND {predicate} GROUP BY date
         )
         SELECT days.day, COALESCE(aggregated.income, 0), COALESCE(aggregated.expenses, 0)
         FROM days LEFT JOIN aggregated ON aggregated.date = days.day
         ORDER BY days.day"#
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

fn capital_rows(
    conn: &Connection,
    filters: &AnalyticsFilters,
    current_rates: Option<&HashMap<String, f64>>,
) -> StorageResult<Vec<(String, i64)>> {
    let signed = signed_amount_expression(filters, "", current_rates);
    let sql = format!(
        "SELECT month, SUM(monthly_delta) OVER (ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) \
         FROM (SELECT substr(date, 1, 7) AS month, COALESCE(SUM({signed}), 0) AS monthly_delta \
         FROM records WHERE date <= ?2 GROUP BY substr(date, 1, 7) ORDER BY month) \
         WHERE month >= substr(?1, 1, 7)"
    );
    let mut statement = conn.prepare(&sql).map_err(sqlite_err)?;
    let rows = statement
        .query_map(
            (filters.period_start.as_str(), filters.period_end.as_str()),
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .map_err(sqlite_err)?;
    rows.map(|row| row.map_err(sqlite_err)).collect()
}

fn summary(
    conn: &Connection,
    filters: &AnalyticsFilters,
    monthly: &[AnalyticsMonthlyRow],
    current_rates: Option<&HashMap<String, f64>>,
) -> StorageResult<AnalyticsSummary> {
    let amount = amount_expression(filters, "", current_rates);
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
    let signed = signed_amount_expression(filters, "r.", current_rates);
    let delta_minor: i64 = conn
        .query_row(
            &format!("SELECT COALESCE(SUM({signed}), 0) FROM records r WHERE r.date <= ?1"),
            [filters.period_end.as_str()],
            |row| row.get(0),
        )
        .map_err(sqlite_err)?;
    let year = filters.period_end.get(0..4).unwrap_or("");
    let year_income: i64 = conn.query_row(&format!("SELECT COALESCE(SUM(CASE WHEN type = 'income' THEN {amount} ELSE 0 END), 0) FROM records WHERE transfer_id IS NULL AND category <> 'Transfer' AND substr(date,1,4)=?1 AND date <= ?2"), (year, filters.period_end.as_str()), |row| row.get(0)).map_err(sqlite_err)?;
    let year_expense: i64 = conn.query_row(&format!("SELECT COALESCE(SUM(CASE WHEN type IN ('expense','mandatory_expense') THEN {amount} ELSE 0 END), 0) FROM records WHERE transfer_id IS NULL AND category <> 'Transfer' AND substr(date,1,4)=?1 AND date <= ?2"), (year, filters.period_end.as_str()), |row| row.get(0)).map_err(sqlite_err)?;
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
    if !matches!(filters.totals_mode.as_str(), "fixed" | "current") {
        return Err("Analytics totals mode must be fixed or current".to_owned());
    }
    validate_infographic_periods(filters)?;
    with_cached_read_connection(db_path, |conn| {
        let current_rates = if filters.totals_mode == "current" {
            Some(load_current_rates(db_path, conn, filters)?)
        } else {
            None
        };
        let rates = current_rates.as_ref();
        let monthly = monthly_rows(conn, filters, rates)?;
        let category_rows = breakdown_rows(
            conn,
            filters,
            "type IN ('expense', 'mandatory_expense')",
            rates,
        )?;
        let grouped_categories = group_other(category_rows.clone());
        let tags = group_other(tag_rows(conn, filters, rates)?);
        let pie_range = period_for(filters.pie_period.trim());
        let pie_filters = with_period(filters, pie_range.0, pie_range.1);
        let infographic_categories = group_other(breakdown_rows(
            conn,
            &pie_filters,
            "type IN ('expense', 'mandatory_expense')",
            rates,
        )?);
        let daily_month = if filters.daily_month.trim().is_empty() {
            filters
                .period_start
                .get(0..7)
                .unwrap_or("0000-01")
                .to_owned()
        } else {
            filters.daily_month.trim().to_owned()
        };
        let daily_range = period_for(&daily_month);
        let daily_filters = with_period(filters, daily_range.0, daily_range.1);
        let monthly_year = if filters.monthly_year.trim().is_empty() {
            filters.period_end.get(0..4).unwrap_or("0000").to_owned()
        } else {
            filters.monthly_year.trim().to_owned()
        };
        let monthly_range = period_for(&monthly_year);
        let monthly_filters = with_period(filters, monthly_range.0, monthly_range.1);
        let infographic_daily = daily_rows(conn, &daily_filters, rates)?;
        let infographic_monthly = monthly_rows(conn, &monthly_filters, rates)?;
        let initial_minor: i64 = conn
            .query_row(
                "SELECT COALESCE(SUM(COALESCE(initial_balance_minor, CAST(ROUND(initial_balance * 100.0) AS INTEGER), 0)), 0) FROM wallets WHERE is_active = 1",
                [],
                |row| row.get(0),
            )
            .map_err(sqlite_err)?;
        let capital = capital_rows(conn, filters, rates)?
            .into_iter()
            .map(|row| AnalyticsCapitalPoint {
                month: row.0,
                balance_base: minor_to_money_value(initial_minor + row.1),
            })
            .collect();
        let suggested_categories =
            categories_from_conn(conn, &filters.period_start, &filters.period_end)?;
        let suggested_tags = tags_from_conn(conn, &filters.period_start, &filters.period_end)?;
        let infographic_months = months_from_conn(conn)?;
        let infographic_years = years_from_conn(conn)?;
        Ok(AnalyticsSnapshot {
            summary: summary(conn, filters, &monthly, rates)?,
            capital,
            categories: category_rows,
            grouped_categories,
            tags,
            infographic_categories,
            monthly,
            daily: daily_rows(conn, filters, rates)?,
            infographic_monthly,
            infographic_daily,
            suggested_categories,
            suggested_tags,
            infographic_months,
            infographic_years,
        })
    })
}

pub fn analytics_list_categories(
    db_path: &str,
    start: &str,
    end: &str,
) -> StorageResult<Vec<String>> {
    validate_period(start, end)?;
    with_cached_read_connection(db_path, |conn| categories_from_conn(conn, start, end))
}

pub fn analytics_list_tags(db_path: &str, start: &str, end: &str) -> StorageResult<Vec<String>> {
    validate_period(start, end)?;
    with_cached_read_connection(db_path, |conn| tags_from_conn(conn, start, end))
}

pub fn analytics_list_months(db_path: &str) -> StorageResult<Vec<String>> {
    with_cached_read_connection(db_path, months_from_conn)
}

pub fn analytics_list_years(db_path: &str) -> StorageResult<Vec<String>> {
    with_cached_read_connection(db_path, years_from_conn)
}

#[cfg(test)]
mod tests {
    use super::{analytics_generate, group_other, period_for, validate_period};
    use crate::{storage_clear_read_connection_cache, AnalyticsBreakdownRow, AnalyticsFilters};
    use rusqlite::Connection;

    #[test]
    fn rejects_impossible_calendar_dates() {
        assert!(validate_period("2024-02-29", "2024-03-01").is_ok());
        assert!(validate_period("2023-02-29", "2023-03-01").is_err());
        assert!(validate_period("2026-04-31", "2026-05-01").is_err());
    }

    #[test]
    fn uses_leap_day_for_february_infographic_period() {
        assert_eq!(period_for("2024-02").1, "2024-02-29");
        assert_eq!(period_for("2023-02").1, "2023-02-28");
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
                details: Vec::new(),
            })
            .collect();
        let grouped = group_other(rows);
        assert_eq!(grouped.len(), 10);
        assert_eq!(grouped[9].label, "Other");
        assert!(grouped[9].is_other);
        assert_eq!(grouped[9].amount_base, 2.0);
        assert_eq!(grouped[9].details.len(), 2);
        assert_eq!(grouped[9].details[0].label, "Category 9");
    }

    #[test]
    fn generates_category_breakdown_with_valid_sql_spacing() {
        let path = std::env::temp_dir().join(format!(
            "ledgera_analytics_sql_{}_{}.db",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("system clock before unix epoch")
                .as_nanos()
        ));
        let path_text = path.to_string_lossy().into_owned();
        let connection = Connection::open(&path).expect("open test database");
        connection
            .execute_batch(include_str!("../../../../db/schema.sql"))
            .expect("create test schema");
        connection
            .execute(
                "INSERT INTO wallets (name, currency, initial_balance, initial_balance_minor, system, allow_negative, is_active)
                 VALUES ('Main Wallet', 'KZT', 0, 0, 1, 0, 1)",
                [],
            )
            .expect("insert wallet");
        connection
            .execute(
                "INSERT INTO records (type, date, wallet_id, amount_original, amount_original_minor, currency,
                 rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor, category, description)
                 VALUES ('expense', '2026-01-10', 1, 12.34, 1234, 'KZT', 1, '1', 12.34, 1234, 'Food', '')",
                [],
            )
            .expect("insert record");
        drop(connection);

        let snapshot = analytics_generate(
            &path_text,
            &AnalyticsFilters {
                period_start: "2026-01-01".to_owned(),
                period_end: "2026-01-31".to_owned(),
                wallet_id: None,
                category: String::new(),
                tag: String::new(),
                tag_mode: "or".to_owned(),
                totals_mode: "fixed".to_owned(),
                group_by_category: false,
                breakdown_mode: "category".to_owned(),
                pie_period: "all_time".to_owned(),
                daily_month: "2026-01".to_owned(),
                monthly_year: "2026".to_owned(),
            },
        )
        .expect("generate analytics snapshot");

        assert_eq!(snapshot.categories.len(), 1);
        assert_eq!(snapshot.categories[0].label, "Food");
        assert_eq!(snapshot.categories[0].amount_base, 12.34);
        assert_eq!(snapshot.summary.year_expense, 12.34);
        storage_clear_read_connection_cache();
        let connection = Connection::open(&path).expect("reopen test database");
        connection
            .execute(
                "INSERT INTO records (type, date, wallet_id, amount_original, amount_original_minor, currency,
                 rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor, category, description)
                 VALUES ('expense', '2026-01-11', 1, 1.00, 100, 'USD', 450, '450', 4.50, 450, 'Foreign', '')",
                [],
            )
            .expect("insert unsupported current-rate record");
        drop(connection);
        let current_error = analytics_generate(
            &path_text,
            &AnalyticsFilters {
                totals_mode: "current".to_owned(),
                ..AnalyticsFilters {
                    period_start: "2026-01-01".to_owned(),
                    period_end: "2026-01-31".to_owned(),
                    wallet_id: None,
                    category: String::new(),
                    tag: String::new(),
                    tag_mode: "or".to_owned(),
                    totals_mode: "fixed".to_owned(),
                    group_by_category: false,
                    breakdown_mode: "category".to_owned(),
                    pie_period: "all_time".to_owned(),
                    daily_month: "2026-01".to_owned(),
                    monthly_year: "2026".to_owned(),
                }
            },
        )
        .expect_err("current totals must fail without a usable rate");
        assert!(current_error.contains("no usable rate for currency USD"));
        storage_clear_read_connection_cache();
        std::fs::remove_file(path).expect("remove test database");
    }
}
