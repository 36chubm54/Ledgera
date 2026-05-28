use ledgera_engine_storage::{
    MandatoryExpenseRow, RecordRow, TransferRow, WalletRow, cashflow_sum as storage_cashflow_sum,
    mandatory_expense_row as storage_mandatory_expense_row,
    mandatory_expense_rows as storage_mandatory_expense_rows,
    record_get_row as storage_record_get_row, record_list_rows as storage_record_list_rows,
    record_rows_by_tag as storage_record_rows_by_tag,
    transfer_id_by_record_index as storage_transfer_id_by_record_index,
    transfer_list_rows as storage_transfer_list_rows, wallet_balance_parts as storage_wallet_balance_parts,
    wallet_balance_rows as storage_wallet_balance_rows, wallet_list_rows as storage_wallet_list_rows,
    WalletBalanceRow,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

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
fn wallet_balance_rows(
    db_path: &str,
    up_to_date: Option<&str>,
) -> PyResult<Vec<WalletBalanceRow>> {
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
    Ok(())
}
