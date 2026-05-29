use ledgera_engine_storage::{
    CategoryMetricRow, MandatoryExpenseRow, MonthlyCashflowRow, MonthlyCumulativeRow,
    MonthlySummaryRow, NetWorthDeltaRow, RecordRow, TagCoverageRow, TagMetricRow, TransferRow,
    WalletBalanceRow, WalletRow, cashflow_sum as storage_cashflow_sum,
    mandatory_expense_row as storage_mandatory_expense_row,
    mandatory_expense_rows as storage_mandatory_expense_rows,
    metrics_period_snapshot as storage_metrics_period_snapshot,
    metrics_burn_rate as storage_metrics_burn_rate,
    metrics_income_by_category as storage_metrics_income_by_category,
    metrics_monthly_summary as storage_metrics_monthly_summary,
    metrics_savings_rate as storage_metrics_savings_rate,
    metrics_spending_by_category as storage_metrics_spending_by_category,
    metrics_spending_by_tag as storage_metrics_spending_by_tag,
    metrics_tag_coverage as storage_metrics_tag_coverage, record_get_row as storage_record_get_row,
    record_list_rows as storage_record_list_rows, record_rows_by_tag as storage_record_rows_by_tag,
    timeline_cumulative_income_expense as storage_timeline_cumulative_income_expense,
    timeline_monthly_cashflow as storage_timeline_monthly_cashflow,
    timeline_net_worth_monthly_deltas as storage_timeline_net_worth_monthly_deltas,
    transfer_id_by_record_index as storage_transfer_id_by_record_index,
    transfer_list_rows as storage_transfer_list_rows,
    storage_clear_read_connection_cache,
    wallet_balance_parts as storage_wallet_balance_parts,
    wallet_balance_rows as storage_wallet_balance_rows,
    wallet_list_rows as storage_wallet_list_rows,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

type CompactCategoryRows = Vec<(String, f64, i64)>;
type CompactTagRows = Vec<(String, String, f64, i64)>;
type CompactMonthlySummaryRows = Vec<(String, f64, f64, f64, f64)>;
type CompactMonthlyCashflowRows = Vec<(String, f64, f64, f64)>;
type CompactMetricsPeriodSnapshot = (
    f64,
    f64,
    CompactCategoryRows,
    CompactCategoryRows,
    CompactTagRows,
    (i64, i64, f64),
    CompactMonthlySummaryRows,
    CompactMonthlyCashflowRows,
);

fn core_err(err: String) -> PyErr {
    PyValueError::new_err(err)
}

fn py_value_to_text(value: &Bound<'_, PyAny>, default: &str) -> PyResult<String> {
    if value.is_none() {
        return Ok(default.to_owned());
    }
    Ok(value.str()?.to_str()?.trim().to_owned())
}

#[pyfunction]
fn convert_amount(amount: f64, rate: f64) -> PyResult<f64> {
    Ok(ledgera_engine_core::convert_amount(amount, rate))
}

#[pyfunction]
fn calculate_daily_burn(total_spent: f64, days_passed: i32) -> PyResult<f64> {
    Ok(ledgera_engine_core::calculate_daily_burn(
        total_spent,
        days_passed,
    ))
}

#[pyfunction]
fn to_money_float(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    ledgera_engine_core::to_money_float(&py_value_to_text(value, "0")?).map_err(core_err)
}

#[pyfunction]
fn to_rate_float(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    ledgera_engine_core::to_rate_float(&py_value_to_text(value, "0")?).map_err(core_err)
}

#[pyfunction]
fn to_minor_units(value: &Bound<'_, PyAny>) -> PyResult<i64> {
    ledgera_engine_core::to_minor_units(&py_value_to_text(value, "0")?).map_err(core_err)
}

#[pyfunction]
fn minor_to_money(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    ledgera_engine_core::minor_to_money(&py_value_to_text(value, "0")?).map_err(core_err)
}

#[pyfunction]
fn build_rate(
    amount_original: &Bound<'_, PyAny>,
    amount_base: &Bound<'_, PyAny>,
    currency: &str,
) -> PyResult<f64> {
    ledgera_engine_core::build_rate(
        &py_value_to_text(amount_original, "0")?,
        &py_value_to_text(amount_base, "0")?,
        currency,
    )
    .map_err(core_err)
}

#[pyfunction]
fn money_abs(value: &Bound<'_, PyAny>) -> PyResult<f64> {
    ledgera_engine_core::money_abs(&py_value_to_text(value, "0")?).map_err(core_err)
}

#[pyfunction]
fn quantize_money_text(value: &Bound<'_, PyAny>) -> PyResult<String> {
    ledgera_engine_core::quantize_money_text(&py_value_to_text(value, "0")?).map_err(core_err)
}

#[pyfunction]
fn quantize_rate_text(value: &Bound<'_, PyAny>) -> PyResult<String> {
    ledgera_engine_core::quantize_rate_text(&py_value_to_text(value, "0")?).map_err(core_err)
}

#[pyfunction]
fn rate_to_text(value: &Bound<'_, PyAny>) -> PyResult<String> {
    ledgera_engine_core::rate_to_text(&py_value_to_text(value, "0")?).map_err(core_err)
}

#[pyfunction]
fn money_diff_text(left: &Bound<'_, PyAny>, right: &Bound<'_, PyAny>) -> PyResult<String> {
    ledgera_engine_core::money_diff_text(
        &py_value_to_text(left, "0")?,
        &py_value_to_text(right, "0")?,
    )
    .map_err(core_err)
}

#[pyfunction]
fn rate_diff_text(left: &Bound<'_, PyAny>, right: &Bound<'_, PyAny>) -> PyResult<String> {
    ledgera_engine_core::rate_diff_text(
        &py_value_to_text(left, "0")?,
        &py_value_to_text(right, "0")?,
    )
    .map_err(core_err)
}

#[pyfunction]
fn wallet_balance_parts(
    db_path: &str,
    wallet_id: i64,
    up_to_date: Option<&str>,
) -> PyResult<Option<(f64, String, f64)>> {
    storage_wallet_balance_parts(db_path, wallet_id, up_to_date).map_err(core_err)
}

#[pyfunction]
fn wallet_balance_rows(db_path: &str, up_to_date: Option<&str>) -> PyResult<Vec<WalletBalanceRow>> {
    storage_wallet_balance_rows(db_path, up_to_date).map_err(core_err)
}

#[pyfunction]
fn cashflow_sum(
    db_path: &str,
    record_type: &str,
    start_date: &str,
    end_date: &str,
) -> PyResult<f64> {
    storage_cashflow_sum(db_path, record_type, start_date, end_date).map_err(core_err)
}

fn wallet_to_dict(py: Python<'_>, row: WalletRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("name", row.name)?;
    payload.set_item("currency", row.currency)?;
    payload.set_item("initial_balance", row.initial_balance)?;
    payload.set_item("system", row.system)?;
    payload.set_item("allow_negative", row.allow_negative)?;
    payload.set_item("is_active", row.is_active)?;
    Ok(payload.into_any().unbind())
}

fn transfer_to_dict(py: Python<'_>, row: TransferRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("from_wallet_id", row.from_wallet_id)?;
    payload.set_item("to_wallet_id", row.to_wallet_id)?;
    payload.set_item("date", row.date)?;
    payload.set_item("amount_original", row.amount_original)?;
    payload.set_item("currency", row.currency)?;
    payload.set_item("rate_at_operation", row.rate_at_operation)?;
    payload.set_item("amount_base", row.amount_base)?;
    payload.set_item("description", row.description)?;
    Ok(payload.into_any().unbind())
}

fn mandatory_expense_to_dict(py: Python<'_>, row: MandatoryExpenseRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("wallet_id", row.wallet_id)?;
    payload.set_item("amount_original", row.amount_original)?;
    payload.set_item("currency", row.currency)?;
    payload.set_item("rate_at_operation", row.rate_at_operation)?;
    payload.set_item("amount_base", row.amount_base)?;
    payload.set_item("category", row.category)?;
    payload.set_item("description", row.description)?;
    payload.set_item("period", row.period)?;
    payload.set_item("date", row.date)?;
    payload.set_item("auto_pay", row.auto_pay)?;
    Ok(payload.into_any().unbind())
}

fn record_to_dict(py: Python<'_>, row: RecordRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("type", row.record_type)?;
    payload.set_item("date", row.date)?;
    payload.set_item("wallet_id", row.wallet_id)?;
    payload.set_item("transfer_id", row.transfer_id)?;
    payload.set_item("related_debt_id", row.related_debt_id)?;
    payload.set_item("amount_original", row.amount_original)?;
    payload.set_item("currency", row.currency)?;
    payload.set_item("rate_at_operation", row.rate_at_operation)?;
    payload.set_item("amount_base", row.amount_base)?;
    payload.set_item("category", row.category)?;
    payload.set_item("description", row.description)?;
    payload.set_item("period", row.period)?;
    payload.set_item("tags", row.tags)?;
    Ok(payload.into_any().unbind())
}

fn category_metric_to_dict(py: Python<'_>, row: CategoryMetricRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("category", row.category)?;
    payload.set_item("total_base", row.total_base)?;
    payload.set_item("record_count", row.record_count)?;
    Ok(payload.into_any().unbind())
}

fn tag_metric_to_dict(py: Python<'_>, row: TagMetricRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("tag", row.tag)?;
    payload.set_item("color", row.color)?;
    payload.set_item("total_base", row.total_base)?;
    payload.set_item("record_count", row.record_count)?;
    Ok(payload.into_any().unbind())
}

fn tag_coverage_to_dict(py: Python<'_>, row: TagCoverageRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("tagged_count", row.tagged_count)?;
    payload.set_item("total_count", row.total_count)?;
    payload.set_item("coverage_pct", row.coverage_pct)?;
    Ok(payload.into_any().unbind())
}

fn monthly_summary_to_dict(py: Python<'_>, row: MonthlySummaryRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("month", row.month)?;
    payload.set_item("income", row.income)?;
    payload.set_item("expenses", row.expenses)?;
    payload.set_item("cashflow", row.cashflow)?;
    payload.set_item("savings_rate", row.savings_rate)?;
    Ok(payload.into_any().unbind())
}

fn monthly_cashflow_to_dict(py: Python<'_>, row: MonthlyCashflowRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("month", row.month)?;
    payload.set_item("income", row.income)?;
    payload.set_item("expenses", row.expenses)?;
    payload.set_item("cashflow", row.cashflow)?;
    Ok(payload.into_any().unbind())
}

fn monthly_cumulative_to_dict(py: Python<'_>, row: MonthlyCumulativeRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("month", row.month)?;
    payload.set_item("cumulative_income", row.cumulative_income)?;
    payload.set_item("cumulative_expenses", row.cumulative_expenses)?;
    Ok(payload.into_any().unbind())
}

fn net_worth_delta_to_dict(py: Python<'_>, row: NetWorthDeltaRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("month", row.month)?;
    payload.set_item("running_delta", row.running_delta)?;
    Ok(payload.into_any().unbind())
}

fn category_metrics_to_py(
    py: Python<'_>,
    rows: Vec<CategoryMetricRow>,
) -> PyResult<Vec<Py<PyAny>>> {
    rows.into_iter()
        .map(|row| category_metric_to_dict(py, row))
        .collect()
}

fn tag_metrics_to_py(py: Python<'_>, rows: Vec<TagMetricRow>) -> PyResult<Vec<Py<PyAny>>> {
    rows.into_iter()
        .map(|row| tag_metric_to_dict(py, row))
        .collect()
}

fn monthly_summary_to_py(
    py: Python<'_>,
    rows: Vec<MonthlySummaryRow>,
) -> PyResult<Vec<Py<PyAny>>> {
    rows.into_iter()
        .map(|row| monthly_summary_to_dict(py, row))
        .collect()
}

fn monthly_cashflow_to_py(
    py: Python<'_>,
    rows: Vec<MonthlyCashflowRow>,
) -> PyResult<Vec<Py<PyAny>>> {
    rows.into_iter()
        .map(|row| monthly_cashflow_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn wallet_list_rows(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_wallet_list_rows(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| wallet_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn transfer_list_rows(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_transfer_list_rows(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| transfer_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn transfer_id_by_record_index(db_path: &str, index: i64) -> PyResult<Option<i64>> {
    storage_transfer_id_by_record_index(db_path, index).map_err(core_err)
}

#[pyfunction]
fn mandatory_expense_rows(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_mandatory_expense_rows(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| mandatory_expense_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn mandatory_expense_row(
    py: Python<'_>,
    db_path: &str,
    expense_id: i64,
) -> PyResult<Option<Py<PyAny>>> {
    storage_mandatory_expense_row(db_path, expense_id)
        .map_err(core_err)?
        .map(|row| mandatory_expense_to_dict(py, row))
        .transpose()
}

#[pyfunction]
fn record_list_rows(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_record_list_rows(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| record_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn record_get_row(py: Python<'_>, db_path: &str, record_id: i64) -> PyResult<Option<Py<PyAny>>> {
    storage_record_get_row(db_path, record_id)
        .map_err(core_err)?
        .map(|row| record_to_dict(py, row))
        .transpose()
}

#[pyfunction]
fn record_rows_by_tag(py: Python<'_>, db_path: &str, tag_name: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_record_rows_by_tag(db_path, tag_name)
        .map_err(core_err)?
        .into_iter()
        .map(|row| record_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn metrics_savings_rate(db_path: &str, start_date: &str, end_date: &str) -> PyResult<f64> {
    storage_metrics_savings_rate(db_path, start_date, end_date).map_err(core_err)
}

#[pyfunction]
fn metrics_burn_rate(db_path: &str, start_date: &str, end_date: &str, days: i64) -> PyResult<f64> {
    storage_metrics_burn_rate(db_path, start_date, end_date, days).map_err(core_err)
}

#[pyfunction]
fn metrics_spending_by_category(
    py: Python<'_>,
    db_path: &str,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_metrics_spending_by_category(db_path, start_date, end_date, limit)
        .map_err(core_err)?
        .into_iter()
        .map(|row| category_metric_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn metrics_income_by_category(
    py: Python<'_>,
    db_path: &str,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_metrics_income_by_category(db_path, start_date, end_date, limit)
        .map_err(core_err)?
        .into_iter()
        .map(|row| category_metric_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn metrics_spending_by_tag(
    py: Python<'_>,
    db_path: &str,
    start_date: &str,
    end_date: &str,
    limit: Option<i64>,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_metrics_spending_by_tag(db_path, start_date, end_date, limit)
        .map_err(core_err)?
        .into_iter()
        .map(|row| tag_metric_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn metrics_tag_coverage(
    py: Python<'_>,
    db_path: &str,
    start_date: &str,
    end_date: &str,
) -> PyResult<Py<PyAny>> {
    storage_metrics_tag_coverage(db_path, start_date, end_date)
        .map_err(core_err)
        .and_then(|row| tag_coverage_to_dict(py, row))
}

#[pyfunction]
fn metrics_period_snapshot(
    py: Python<'_>,
    db_path: &str,
    start_date: &str,
    end_date: &str,
    days: i64,
    category_limit: Option<i64>,
    tag_limit: Option<i64>,
) -> PyResult<Py<PyAny>> {
    let snapshot = storage_metrics_period_snapshot(
        db_path,
        start_date,
        end_date,
        days,
        category_limit,
        tag_limit,
    )
    .map_err(core_err)?;
    let payload = PyDict::new(py);
    payload.set_item("savings_rate", snapshot.savings_rate)?;
    payload.set_item("burn_rate", snapshot.burn_rate)?;
    payload.set_item(
        "spending_by_category",
        category_metrics_to_py(py, snapshot.spending_by_category)?,
    )?;
    payload.set_item(
        "income_by_category",
        category_metrics_to_py(py, snapshot.income_by_category)?,
    )?;
    payload.set_item(
        "spending_by_tag",
        tag_metrics_to_py(py, snapshot.spending_by_tag)?,
    )?;
    payload.set_item("tag_coverage", tag_coverage_to_dict(py, snapshot.tag_coverage)?)?;
    payload.set_item(
        "monthly_summary",
        monthly_summary_to_py(py, snapshot.monthly_summary)?,
    )?;
    payload.set_item(
        "monthly_cashflow",
        monthly_cashflow_to_py(py, snapshot.monthly_cashflow)?,
    )?;
    Ok(payload.into_any().unbind())
}

#[pyfunction]
fn metrics_period_snapshot_compact(
    db_path: &str,
    start_date: &str,
    end_date: &str,
    days: i64,
    category_limit: Option<i64>,
    tag_limit: Option<i64>,
) -> PyResult<CompactMetricsPeriodSnapshot> {
    let snapshot = storage_metrics_period_snapshot(
        db_path,
        start_date,
        end_date,
        days,
        category_limit,
        tag_limit,
    )
    .map_err(core_err)?;
    Ok((
        snapshot.savings_rate,
        snapshot.burn_rate,
        snapshot
            .spending_by_category
            .into_iter()
            .map(|row| (row.category, row.total_base, row.record_count))
            .collect(),
        snapshot
            .income_by_category
            .into_iter()
            .map(|row| (row.category, row.total_base, row.record_count))
            .collect(),
        snapshot
            .spending_by_tag
            .into_iter()
            .map(|row| (row.tag, row.color, row.total_base, row.record_count))
            .collect(),
        (
            snapshot.tag_coverage.tagged_count,
            snapshot.tag_coverage.total_count,
            snapshot.tag_coverage.coverage_pct,
        ),
        snapshot
            .monthly_summary
            .into_iter()
            .map(|row| {
                (
                    row.month,
                    row.income,
                    row.expenses,
                    row.cashflow,
                    row.savings_rate,
                )
            })
            .collect(),
        snapshot
            .monthly_cashflow
            .into_iter()
            .map(|row| (row.month, row.income, row.expenses, row.cashflow))
            .collect(),
    ))
}

#[pyfunction]
fn metrics_monthly_summary(
    py: Python<'_>,
    db_path: &str,
    start_date: Option<&str>,
    end_date: Option<&str>,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_metrics_monthly_summary(db_path, start_date, end_date)
        .map_err(core_err)?
        .into_iter()
        .map(|row| monthly_summary_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn storage_clear_read_cache() -> PyResult<()> {
    storage_clear_read_connection_cache();
    Ok(())
}

#[pyfunction]
fn timeline_monthly_cashflow(
    py: Python<'_>,
    db_path: &str,
    start_date: Option<&str>,
    end_date: Option<&str>,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_timeline_monthly_cashflow(db_path, start_date, end_date)
        .map_err(core_err)?
        .into_iter()
        .map(|row| monthly_cashflow_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn timeline_cumulative_income_expense(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_timeline_cumulative_income_expense(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| monthly_cumulative_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn timeline_net_worth_monthly_deltas(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_timeline_net_worth_monthly_deltas(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| net_worth_delta_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn currency_rate_for(
    currency: &str,
    base_currency: &str,
    rates: &Bound<'_, PyAny>,
) -> PyResult<f64> {
    let rates_map = rates.extract::<std::collections::HashMap<String, f64>>()?;
    ledgera_engine_core::currency_rate_for(currency, base_currency, &rates_map).map_err(core_err)
}

#[pyfunction]
fn currency_default_rates_for_base(
    py: Python<'_>,
    base_currency: &str,
    rates: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let rates_map = rates.extract::<std::collections::HashMap<String, f64>>()?;
    let payload = PyDict::new(py);
    for (code, rate) in
        ledgera_engine_core::currency_default_rates_for_base(base_currency, &rates_map)
            .map_err(core_err)?
    {
        payload.set_item(code, rate)?;
    }
    Ok(payload.into_any().unbind())
}

#[pyfunction]
fn currency_resolve_provider_order(
    base_currency: &str,
    provider_mode: &str,
    primary_provider: &str,
    fallback_provider: &str,
    commercial_fallback_provider: &str,
    enable_cbr: bool,
    provider_order: Option<Vec<String>>,
) -> PyResult<Vec<String>> {
    Ok(ledgera_engine_core::currency_resolve_provider_order(
        base_currency,
        provider_mode,
        primary_provider,
        fallback_provider,
        commercial_fallback_provider,
        enable_cbr,
        provider_order,
    ))
}

#[pymodule]
fn ledgera_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(convert_amount, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_daily_burn, m)?)?;
    m.add_function(wrap_pyfunction!(to_money_float, m)?)?;
    m.add_function(wrap_pyfunction!(to_rate_float, m)?)?;
    m.add_function(wrap_pyfunction!(to_minor_units, m)?)?;
    m.add_function(wrap_pyfunction!(minor_to_money, m)?)?;
    m.add_function(wrap_pyfunction!(build_rate, m)?)?;
    m.add_function(wrap_pyfunction!(money_abs, m)?)?;
    m.add_function(wrap_pyfunction!(quantize_money_text, m)?)?;
    m.add_function(wrap_pyfunction!(quantize_rate_text, m)?)?;
    m.add_function(wrap_pyfunction!(rate_to_text, m)?)?;
    m.add_function(wrap_pyfunction!(money_diff_text, m)?)?;
    m.add_function(wrap_pyfunction!(rate_diff_text, m)?)?;
    m.add_function(wrap_pyfunction!(wallet_balance_parts, m)?)?;
    m.add_function(wrap_pyfunction!(wallet_balance_rows, m)?)?;
    m.add_function(wrap_pyfunction!(cashflow_sum, m)?)?;
    m.add_function(wrap_pyfunction!(wallet_list_rows, m)?)?;
    m.add_function(wrap_pyfunction!(transfer_list_rows, m)?)?;
    m.add_function(wrap_pyfunction!(transfer_id_by_record_index, m)?)?;
    m.add_function(wrap_pyfunction!(mandatory_expense_rows, m)?)?;
    m.add_function(wrap_pyfunction!(mandatory_expense_row, m)?)?;
    m.add_function(wrap_pyfunction!(record_list_rows, m)?)?;
    m.add_function(wrap_pyfunction!(record_get_row, m)?)?;
    m.add_function(wrap_pyfunction!(record_rows_by_tag, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_savings_rate, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_burn_rate, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_spending_by_category, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_income_by_category, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_spending_by_tag, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_tag_coverage, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_period_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_period_snapshot_compact, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_monthly_summary, m)?)?;
    m.add_function(wrap_pyfunction!(timeline_monthly_cashflow, m)?)?;
    m.add_function(wrap_pyfunction!(timeline_cumulative_income_expense, m)?)?;
    m.add_function(wrap_pyfunction!(timeline_net_worth_monthly_deltas, m)?)?;
    m.add_function(wrap_pyfunction!(currency_rate_for, m)?)?;
    m.add_function(wrap_pyfunction!(currency_default_rates_for_base, m)?)?;
    m.add_function(wrap_pyfunction!(currency_resolve_provider_order, m)?)?;
    m.add_function(wrap_pyfunction!(storage_clear_read_cache, m)?)?;
    Ok(())
}
