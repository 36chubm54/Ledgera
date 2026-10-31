use ledgera_engine_storage::{
    AuditFindingRow, BudgetCreatePayload, BudgetPayload, CategoryMetricRow, DebtPayload,
    DebtPaymentPayload, DebtRecordPayload, DistributionItemPayload, DistributionSubitemPayload,
    FrozenDistributionPayload, MandatoryExpenseRow, MonthlyCashflowRow, MonthlyCumulativeRow,
    MonthlySummaryRow, NetWorthDeltaRow, RecordRow, TagCoverageRow, TagMetricRow, TransferRow,
    WalletBalanceRow, WalletRow, audit_run as storage_audit_run,
    audit_run_for_date as storage_audit_run_for_date,
    budget_batch_spent_minor as storage_budget_batch_spent_minor,
    budget_create as storage_budget_create, budget_delete as storage_budget_delete,
    budget_overlap_exists as storage_budget_overlap_exists,
    budget_replace_rows as storage_budget_replace_rows, budget_rows as storage_budget_rows,
    budget_spent_minor as storage_budget_spent_minor,
    budget_update_limit as storage_budget_update_limit, cashflow_sum as storage_cashflow_sum,
    debt_create_obligation as storage_debt_create_obligation, debt_delete as storage_debt_delete,
    debt_delete_payment as storage_debt_delete_payment,
    debt_payment_rows as storage_debt_payment_rows,
    debt_payment_total_minor as storage_debt_payment_total_minor,
    debt_recalculate_payload as storage_debt_recalculate_payload,
    debt_register_payment as storage_debt_register_payment,
    debt_replace_rows as storage_debt_replace_rows, debt_rows as storage_debt_rows,
    debt_validate_payment_amount as storage_debt_validate_payment_amount,
    distribution_available_months as storage_distribution_available_months,
    distribution_create_item as storage_distribution_create_item,
    distribution_create_subitem as storage_distribution_create_subitem,
    distribution_delete_item as storage_distribution_delete_item,
    distribution_delete_subitem as storage_distribution_delete_subitem,
    distribution_frozen_rows as storage_distribution_frozen_rows,
    distribution_history_months as storage_distribution_history_months,
    distribution_is_month_auto_fixed as storage_distribution_is_month_auto_fixed,
    distribution_is_month_fixed as storage_distribution_is_month_fixed,
    distribution_item_rows as storage_distribution_item_rows,
    distribution_monthly_payload as storage_distribution_monthly_payload,
    distribution_net_income_for_period as storage_distribution_net_income_for_period,
    distribution_replace_frozen_rows as storage_distribution_replace_frozen_rows,
    distribution_replace_structure as storage_distribution_replace_structure,
    distribution_subitem_rows as storage_distribution_subitem_rows,
    distribution_unfreeze_month as storage_distribution_unfreeze_month,
    distribution_update_item_name as storage_distribution_update_item_name,
    distribution_update_item_order as storage_distribution_update_item_order,
    distribution_update_item_pct as storage_distribution_update_item_pct,
    distribution_update_subitem_name as storage_distribution_update_subitem_name,
    distribution_update_subitem_order as storage_distribution_update_subitem_order,
    distribution_update_subitem_pct as storage_distribution_update_subitem_pct,
    distribution_validate_structure as storage_distribution_validate_structure,
    distribution_write_frozen_row as storage_distribution_write_frozen_row,
    mandatory_expense_row as storage_mandatory_expense_row,
    mandatory_expense_rows as storage_mandatory_expense_rows,
    metrics_burn_rate as storage_metrics_burn_rate,
    metrics_income_by_category as storage_metrics_income_by_category,
    metrics_monthly_summary as storage_metrics_monthly_summary,
    metrics_period_snapshot as storage_metrics_period_snapshot,
    metrics_refresh_snapshot as storage_metrics_refresh_snapshot,
    metrics_savings_rate as storage_metrics_savings_rate,
    metrics_spending_by_category as storage_metrics_spending_by_category,
    metrics_spending_by_tag as storage_metrics_spending_by_tag,
    metrics_tag_coverage as storage_metrics_tag_coverage, record_get_row as storage_record_get_row,
    record_list_rows as storage_record_list_rows, record_rows_by_tag as storage_record_rows_by_tag,
    storage_clear_read_connection_cache,
    timeline_cumulative_income_expense as storage_timeline_cumulative_income_expense,
    timeline_monthly_cashflow as storage_timeline_monthly_cashflow,
    timeline_net_worth_monthly_deltas as storage_timeline_net_worth_monthly_deltas,
    transfer_id_by_record_index as storage_transfer_id_by_record_index,
    transfer_list_rows as storage_transfer_list_rows,
    wallet_balance_parts as storage_wallet_balance_parts,
    wallet_balance_rows as storage_wallet_balance_rows,
    wallet_list_rows as storage_wallet_list_rows,
};
use ledgera_engine_sync::{
    SyncApplyResult, SyncConfig, SyncPeer, SyncStatus,
    sync_discover_peers as engine_sync_discover_peers, sync_push_once as engine_sync_push_once,
    sync_start_daemon as engine_sync_start_daemon, sync_status as engine_sync_status,
    sync_stop_daemon as engine_sync_stop_daemon,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

type CompactCategoryRows = Vec<(String, f64, i64)>;
type CompactTagRows = Vec<(String, String, f64, i64)>;
type CompactMonthlySummaryRows = Vec<(String, f64, f64, f64, f64)>;
type CompactMonthlyCashflowRows = Vec<(String, f64, f64, f64)>;
type BudgetRowPayload = (i64, String, String, String, f64, i64, bool, String, String);
type FrozenDistributionRowPayload = (
    String,
    Vec<String>,
    Vec<(String, String)>,
    Vec<(String, String)>,
    bool,
    bool,
);
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
type CompactMetricsRefreshSnapshot = (
    f64,
    f64,
    CompactCategoryRows,
    CompactCategoryRows,
    CompactTagRows,
    CompactMonthlySummaryRows,
);

fn core_err(err: String) -> PyErr {
    PyValueError::new_err(err)
}

fn dict_required<T>(payload: &Bound<'_, PyDict>, key: &str) -> PyResult<T>
where
    T: for<'py> FromPyObject<'py, 'py, Error = PyErr>,
{
    payload
        .get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("Missing payload key: {key}")))?
        .extract::<T>()
}

fn dict_optional<T>(payload: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<T>>
where
    T: for<'py> FromPyObject<'py, 'py, Error = PyErr>,
{
    match payload.get_item(key)? {
        Some(value) if !value.is_none() => Ok(Some(value.extract::<T>()?)),
        _ => Ok(None),
    }
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
    payload.set_item("color", row.color)?;
    payload.set_item("icon", row.icon)?;
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

fn audit_finding_to_dict(py: Python<'_>, row: AuditFindingRow) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("check", row.check)?;
    payload.set_item("severity", row.severity)?;
    payload.set_item("message", row.message)?;
    payload.set_item("detail", row.detail)?;
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

fn budget_to_dict(py: Python<'_>, row: BudgetPayload) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("category", row.category)?;
    payload.set_item("start_date", row.start_date)?;
    payload.set_item("end_date", row.end_date)?;
    payload.set_item("limit_base", row.limit_base)?;
    payload.set_item("limit_base_minor", row.limit_base_minor)?;
    payload.set_item("include_mandatory", row.include_mandatory)?;
    payload.set_item("scope_type", row.scope_type)?;
    payload.set_item("scope_value", row.scope_value)?;
    Ok(payload.into_any().unbind())
}

fn budget_tuple_to_payload(row: BudgetRowPayload) -> BudgetPayload {
    BudgetPayload {
        id: row.0,
        category: row.1,
        start_date: row.2,
        end_date: row.3,
        limit_base: row.4,
        limit_base_minor: row.5,
        include_mandatory: row.6,
        scope_type: row.7,
        scope_value: row.8,
    }
}

fn debt_to_dict(py: Python<'_>, row: DebtPayload) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("contact_name", row.contact_name)?;
    payload.set_item("kind", row.kind)?;
    payload.set_item("total_amount_minor", row.total_amount_minor)?;
    payload.set_item("remaining_amount_minor", row.remaining_amount_minor)?;
    payload.set_item("currency", row.currency)?;
    payload.set_item("interest_rate", row.interest_rate)?;
    payload.set_item("status", row.status)?;
    payload.set_item("created_at", row.created_at)?;
    payload.set_item("closed_at", row.closed_at)?;
    Ok(payload.into_any().unbind())
}

fn debt_payment_to_dict(py: Python<'_>, row: DebtPaymentPayload) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("debt_id", row.debt_id)?;
    payload.set_item("record_id", row.record_id)?;
    payload.set_item("operation_type", row.operation_type)?;
    payload.set_item("principal_paid_minor", row.principal_paid_minor)?;
    payload.set_item("is_write_off", row.is_write_off)?;
    payload.set_item("payment_date", row.payment_date)?;
    Ok(payload.into_any().unbind())
}

fn debt_from_dict(payload: &Bound<'_, PyDict>) -> PyResult<DebtPayload> {
    Ok(DebtPayload {
        id: dict_required(payload, "id")?,
        contact_name: dict_required(payload, "contact_name")?,
        kind: dict_required(payload, "kind")?,
        total_amount_minor: dict_required(payload, "total_amount_minor")?,
        remaining_amount_minor: dict_required(payload, "remaining_amount_minor")?,
        currency: dict_required(payload, "currency")?,
        interest_rate: dict_required(payload, "interest_rate")?,
        status: dict_required(payload, "status")?,
        created_at: dict_required(payload, "created_at")?,
        closed_at: dict_optional(payload, "closed_at")?,
    })
}

fn debt_payment_from_dict(payload: &Bound<'_, PyDict>) -> PyResult<DebtPaymentPayload> {
    Ok(DebtPaymentPayload {
        id: dict_required(payload, "id")?,
        debt_id: dict_required(payload, "debt_id")?,
        record_id: dict_optional(payload, "record_id")?,
        operation_type: dict_required(payload, "operation_type")?,
        principal_paid_minor: dict_required(payload, "principal_paid_minor")?,
        is_write_off: dict_required(payload, "is_write_off")?,
        payment_date: dict_required(payload, "payment_date")?,
    })
}

fn debt_record_from_dict(payload: &Bound<'_, PyDict>) -> PyResult<DebtRecordPayload> {
    Ok(DebtRecordPayload {
        record_type: dict_required(payload, "type")?,
        date: dict_required(payload, "date")?,
        wallet_id: dict_required(payload, "wallet_id")?,
        amount_original: dict_required(payload, "amount_original")?,
        amount_original_minor: dict_required(payload, "amount_original_minor")?,
        currency: dict_required(payload, "currency")?,
        rate_at_operation: dict_required(payload, "rate_at_operation")?,
        rate_at_operation_text: dict_required(payload, "rate_at_operation_text")?,
        amount_base: dict_required(payload, "amount_base")?,
        amount_base_minor: dict_required(payload, "amount_base_minor")?,
        category: dict_required(payload, "category")?,
        description: dict_required(payload, "description")?,
        period: dict_optional(payload, "period")?,
    })
}

fn distribution_validation_to_dict(
    py: Python<'_>,
    row: ledgera_engine_storage::DistributionValidationRow,
) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("level", row.level)?;
    payload.set_item("message", row.message)?;
    Ok(payload.into_any().unbind())
}

fn distribution_subitem_to_dict(
    py: Python<'_>,
    row: ledgera_engine_storage::DistributionSubitemPayload,
) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("item_id", row.item_id)?;
    payload.set_item("name", row.name)?;
    payload.set_item("sort_order", row.sort_order)?;
    payload.set_item("pct", row.pct)?;
    payload.set_item("pct_minor", row.pct_minor)?;
    payload.set_item("is_active", row.is_active)?;
    payload.set_item("amount_base", row.amount_base)?;
    payload.set_item("amount_minor", row.amount_minor)?;
    Ok(payload.into_any().unbind())
}

fn distribution_item_to_dict(
    py: Python<'_>,
    row: ledgera_engine_storage::DistributionItemPayload,
) -> PyResult<Py<PyAny>> {
    let subitems = row
        .subitems
        .into_iter()
        .map(|subitem| distribution_subitem_to_dict(py, subitem))
        .collect::<PyResult<Vec<_>>>()?;
    let payload = PyDict::new(py);
    payload.set_item("id", row.id)?;
    payload.set_item("name", row.name)?;
    payload.set_item("group_name", row.group_name)?;
    payload.set_item("sort_order", row.sort_order)?;
    payload.set_item("pct", row.pct)?;
    payload.set_item("pct_minor", row.pct_minor)?;
    payload.set_item("is_active", row.is_active)?;
    payload.set_item("amount_base", row.amount_base)?;
    payload.set_item("amount_minor", row.amount_minor)?;
    payload.set_item("subitems", subitems)?;
    Ok(payload.into_any().unbind())
}

fn distribution_monthly_to_dict(
    py: Python<'_>,
    row: ledgera_engine_storage::DistributionMonthlyPayload,
) -> PyResult<Py<PyAny>> {
    let items = row
        .items
        .into_iter()
        .map(|item| distribution_item_to_dict(py, item))
        .collect::<PyResult<Vec<_>>>()?;
    let payload = PyDict::new(py);
    payload.set_item("month", row.month)?;
    payload.set_item("net_income_base", row.net_income_base)?;
    payload.set_item("net_income_minor", row.net_income_minor)?;
    payload.set_item("is_negative", row.is_negative)?;
    payload.set_item("items", items)?;
    Ok(payload.into_any().unbind())
}

fn frozen_distribution_to_dict(
    py: Python<'_>,
    row: FrozenDistributionPayload,
) -> PyResult<Py<PyAny>> {
    let headings = PyDict::new(py);
    for (key, value) in row.headings_by_column {
        headings.set_item(key, value)?;
    }
    let values = PyDict::new(py);
    for (key, value) in row.values_by_column {
        values.set_item(key, value)?;
    }
    let payload = PyDict::new(py);
    payload.set_item("month", row.month)?;
    payload.set_item("column_order", row.column_order)?;
    payload.set_item("headings_by_column", headings)?;
    payload.set_item("values_by_column", values)?;
    payload.set_item("is_negative", row.is_negative)?;
    payload.set_item("auto_fixed", row.auto_fixed)?;
    Ok(payload.into_any().unbind())
}

fn item_tuple_to_payload(
    row: (i64, String, String, i64, f64, i64, bool),
) -> DistributionItemPayload {
    DistributionItemPayload {
        id: row.0,
        name: row.1,
        group_name: row.2,
        sort_order: row.3,
        pct: row.4,
        pct_minor: row.5,
        is_active: row.6,
        amount_base: 0.0,
        amount_minor: 0,
        subitems: Vec::new(),
    }
}

fn subitem_tuple_to_payload(
    row: (i64, i64, String, i64, f64, i64, bool),
) -> DistributionSubitemPayload {
    DistributionSubitemPayload {
        id: row.0,
        item_id: row.1,
        name: row.2,
        sort_order: row.3,
        pct: row.4,
        pct_minor: row.5,
        is_active: row.6,
        amount_base: 0.0,
        amount_minor: 0,
    }
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

fn monthly_summary_to_py(py: Python<'_>, rows: Vec<MonthlySummaryRow>) -> PyResult<Vec<Py<PyAny>>> {
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

#[pyfunction(signature = (db_path, today = None))]
fn audit_run(py: Python<'_>, db_path: &str, today: Option<&str>) -> PyResult<Vec<Py<PyAny>>> {
    let findings = if let Some(today) = today {
        storage_audit_run_for_date(db_path, today)
    } else {
        storage_audit_run(db_path)
    };
    findings
        .map_err(core_err)?
        .into_iter()
        .map(|row| audit_finding_to_dict(py, row))
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
    payload.set_item(
        "tag_coverage",
        tag_coverage_to_dict(py, snapshot.tag_coverage)?,
    )?;
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
fn metrics_refresh_snapshot_compact(
    db_path: &str,
    start_date: &str,
    end_date: &str,
    days: i64,
    category_limit: Option<i64>,
    tag_limit: Option<i64>,
) -> PyResult<CompactMetricsRefreshSnapshot> {
    let snapshot = storage_metrics_refresh_snapshot(
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

fn sync_config_from_dict(payload: &Bound<'_, PyDict>) -> PyResult<SyncConfig> {
    Ok(SyncConfig {
        db_path: dict_required(payload, "db_path")?,
        device_id: dict_required(payload, "device_id")?,
        device_name: dict_required(payload, "device_name")?,
        bind_host: dict_required(payload, "bind_host")?,
        bind_port: dict_required(payload, "bind_port")?,
        discovery_enabled: dict_required(payload, "discovery_enabled")?,
        discovery_port: dict_required(payload, "discovery_port")?,
        poll_interval_ms: dict_required(payload, "poll_interval_ms")?,
    })
}

fn sync_status_to_dict(py: Python<'_>, status: SyncStatus) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("enabled", status.enabled)?;
    payload.set_item("running", status.running)?;
    payload.set_item("bind_host", status.bind_host)?;
    payload.set_item("bind_port", status.bind_port)?;
    payload.set_item("device_id", status.device_id)?;
    payload.set_item("device_name", status.device_name)?;
    payload.set_item("last_error", status.last_error)?;
    Ok(payload.into_any().unbind())
}

fn sync_peer_to_dict(py: Python<'_>, peer: SyncPeer) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("host", peer.host)?;
    payload.set_item("port", peer.port)?;
    payload.set_item("device_id", peer.device_id)?;
    payload.set_item("device_name", peer.device_name)?;
    Ok(payload.into_any().unbind())
}

fn sync_result_to_dict(py: Python<'_>, result: SyncApplyResult) -> PyResult<Py<PyAny>> {
    let payload = PyDict::new(py);
    payload.set_item("inserted", result.inserted)?;
    payload.set_item("skipped", result.skipped)?;
    payload.set_item("errors", result.errors)?;
    Ok(payload.into_any().unbind())
}

#[pyfunction]
fn sync_start_daemon(py: Python<'_>, config: &Bound<'_, PyDict>) -> PyResult<Py<PyAny>> {
    engine_sync_start_daemon(sync_config_from_dict(config)?)
        .map_err(core_err)
        .and_then(|status| sync_status_to_dict(py, status))
}

#[pyfunction]
fn sync_stop_daemon(py: Python<'_>) -> PyResult<Py<PyAny>> {
    engine_sync_stop_daemon()
        .map_err(core_err)
        .and_then(|status| sync_status_to_dict(py, status))
}

#[pyfunction]
fn sync_status(py: Python<'_>) -> PyResult<Py<PyAny>> {
    sync_status_to_dict(py, engine_sync_status())
}

#[pyfunction]
#[pyo3(signature = (timeout_ms, discovery_port = 37639))]
fn sync_discover_peers(
    py: Python<'_>,
    timeout_ms: u64,
    discovery_port: u16,
) -> PyResult<Vec<Py<PyAny>>> {
    engine_sync_discover_peers(timeout_ms, discovery_port)
        .map_err(core_err)?
        .into_iter()
        .map(|peer| sync_peer_to_dict(py, peer))
        .collect()
}

#[pyfunction]
fn sync_push_once(
    py: Python<'_>,
    config: &Bound<'_, PyDict>,
    peer_host: &str,
    peer_port: u16,
) -> PyResult<Py<PyAny>> {
    engine_sync_push_once(sync_config_from_dict(config)?, peer_host, peer_port)
        .map_err(core_err)
        .and_then(|result| sync_result_to_dict(py, result))
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

#[pyfunction]
fn distribution_net_income_for_period(
    db_path: &str,
    start_date: &str,
    end_date: &str,
) -> PyResult<(f64, i64)> {
    storage_distribution_net_income_for_period(db_path, start_date, end_date).map_err(core_err)
}

#[pyfunction]
fn distribution_available_months(db_path: &str) -> PyResult<Vec<String>> {
    storage_distribution_available_months(db_path).map_err(core_err)
}

#[pyfunction]
fn distribution_history_months(
    db_path: &str,
    start_month: &str,
    end_month: &str,
) -> PyResult<Vec<String>> {
    storage_distribution_history_months(db_path, start_month, end_month).map_err(core_err)
}

#[pyfunction]
fn distribution_validate_structure(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_distribution_validate_structure(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| distribution_validation_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn distribution_monthly_payload(
    py: Python<'_>,
    db_path: &str,
    month: &str,
    start_date: &str,
    end_date: &str,
) -> PyResult<Py<PyAny>> {
    storage_distribution_monthly_payload(db_path, month, start_date, end_date)
        .map_err(core_err)
        .and_then(|row| distribution_monthly_to_dict(py, row))
}

#[pyfunction]
fn distribution_item_rows(
    py: Python<'_>,
    db_path: &str,
    active_only: bool,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_distribution_item_rows(db_path, active_only)
        .map_err(core_err)?
        .into_iter()
        .map(|row| distribution_item_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn distribution_subitem_rows(
    py: Python<'_>,
    db_path: &str,
    item_id: i64,
    active_only: bool,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_distribution_subitem_rows(db_path, item_id, active_only)
        .map_err(core_err)?
        .into_iter()
        .map(|row| distribution_subitem_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn distribution_create_item(
    py: Python<'_>,
    db_path: &str,
    name: &str,
    group_name: &str,
    sort_order: i64,
    pct: f64,
    pct_minor: i64,
) -> PyResult<Py<PyAny>> {
    storage_distribution_create_item(db_path, name, group_name, sort_order, pct, pct_minor)
        .map_err(core_err)
        .and_then(|row| distribution_item_to_dict(py, row))
}

#[pyfunction]
fn distribution_update_item_pct(
    py: Python<'_>,
    db_path: &str,
    item_id: i64,
    pct: f64,
    pct_minor: i64,
) -> PyResult<Py<PyAny>> {
    storage_distribution_update_item_pct(db_path, item_id, pct, pct_minor)
        .map_err(core_err)
        .and_then(|row| distribution_item_to_dict(py, row))
}

#[pyfunction]
fn distribution_update_item_name(
    py: Python<'_>,
    db_path: &str,
    item_id: i64,
    name: &str,
) -> PyResult<Py<PyAny>> {
    storage_distribution_update_item_name(db_path, item_id, name)
        .map_err(core_err)
        .and_then(|row| distribution_item_to_dict(py, row))
}

#[pyfunction]
fn distribution_update_item_order(db_path: &str, item_id: i64, sort_order: i64) -> PyResult<()> {
    storage_distribution_update_item_order(db_path, item_id, sort_order).map_err(core_err)
}

#[pyfunction]
fn distribution_delete_item(db_path: &str, item_id: i64) -> PyResult<()> {
    storage_distribution_delete_item(db_path, item_id).map_err(core_err)
}

#[pyfunction]
fn distribution_create_subitem(
    py: Python<'_>,
    db_path: &str,
    item_id: i64,
    name: &str,
    sort_order: i64,
    pct: f64,
    pct_minor: i64,
) -> PyResult<Py<PyAny>> {
    storage_distribution_create_subitem(db_path, item_id, name, sort_order, pct, pct_minor)
        .map_err(core_err)
        .and_then(|row| distribution_subitem_to_dict(py, row))
}

#[pyfunction]
fn distribution_update_subitem_pct(
    py: Python<'_>,
    db_path: &str,
    subitem_id: i64,
    pct: f64,
    pct_minor: i64,
) -> PyResult<Py<PyAny>> {
    storage_distribution_update_subitem_pct(db_path, subitem_id, pct, pct_minor)
        .map_err(core_err)
        .and_then(|row| distribution_subitem_to_dict(py, row))
}

#[pyfunction]
fn distribution_update_subitem_name(
    py: Python<'_>,
    db_path: &str,
    subitem_id: i64,
    name: &str,
) -> PyResult<Py<PyAny>> {
    storage_distribution_update_subitem_name(db_path, subitem_id, name)
        .map_err(core_err)
        .and_then(|row| distribution_subitem_to_dict(py, row))
}

#[pyfunction]
fn distribution_update_subitem_order(
    db_path: &str,
    subitem_id: i64,
    sort_order: i64,
) -> PyResult<()> {
    storage_distribution_update_subitem_order(db_path, subitem_id, sort_order).map_err(core_err)
}

#[pyfunction]
fn distribution_delete_subitem(db_path: &str, subitem_id: i64) -> PyResult<()> {
    storage_distribution_delete_subitem(db_path, subitem_id).map_err(core_err)
}

#[pyfunction]
fn distribution_replace_structure(
    db_path: &str,
    items: Vec<(i64, String, String, i64, f64, i64, bool)>,
    subitems: Vec<(i64, i64, String, i64, f64, i64, bool)>,
) -> PyResult<()> {
    let item_payloads: Vec<_> = items.into_iter().map(item_tuple_to_payload).collect();
    let subitem_payloads: Vec<_> = subitems.into_iter().map(subitem_tuple_to_payload).collect();
    storage_distribution_replace_structure(db_path, &item_payloads, &subitem_payloads)
        .map_err(core_err)
}

#[pyfunction]
fn distribution_is_month_fixed(db_path: &str, month: &str) -> PyResult<bool> {
    storage_distribution_is_month_fixed(db_path, month).map_err(core_err)
}

#[pyfunction]
fn distribution_is_month_auto_fixed(db_path: &str, month: &str) -> PyResult<bool> {
    storage_distribution_is_month_auto_fixed(db_path, month).map_err(core_err)
}

#[pyfunction]
fn distribution_write_frozen_row(
    db_path: &str,
    month: &str,
    column_order: Vec<String>,
    headings_by_column: Vec<(String, String)>,
    values_by_column: Vec<(String, String)>,
    is_negative: bool,
    auto_fixed: bool,
) -> PyResult<()> {
    let row = FrozenDistributionPayload {
        month: month.to_owned(),
        column_order,
        headings_by_column,
        values_by_column,
        is_negative,
        auto_fixed,
    };
    storage_distribution_write_frozen_row(db_path, &row).map_err(core_err)
}

#[pyfunction]
fn distribution_unfreeze_month(db_path: &str, month: &str) -> PyResult<()> {
    storage_distribution_unfreeze_month(db_path, month).map_err(core_err)
}

#[pyfunction]
fn distribution_frozen_rows(
    py: Python<'_>,
    db_path: &str,
    start_month: Option<&str>,
    end_month: Option<&str>,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_distribution_frozen_rows(db_path, start_month, end_month)
        .map_err(core_err)?
        .into_iter()
        .map(|row| frozen_distribution_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn distribution_replace_frozen_rows(
    db_path: &str,
    rows: Vec<FrozenDistributionRowPayload>,
) -> PyResult<()> {
    let payloads: Vec<_> = rows
        .into_iter()
        .map(|row| FrozenDistributionPayload {
            month: row.0,
            column_order: row.1,
            headings_by_column: row.2,
            values_by_column: row.3,
            is_negative: row.4,
            auto_fixed: row.5,
        })
        .collect();
    storage_distribution_replace_frozen_rows(db_path, &payloads).map_err(core_err)
}

#[pyfunction]
fn budget_rows(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_budget_rows(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| budget_to_dict(py, row))
        .collect()
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn budget_create(
    py: Python<'_>,
    db_path: &str,
    category: &str,
    scope_type: &str,
    scope_value: &str,
    start_date: &str,
    end_date: &str,
    limit_base: f64,
    limit_base_minor: i64,
    include_mandatory: bool,
) -> PyResult<Py<PyAny>> {
    storage_budget_create(
        db_path,
        BudgetCreatePayload {
            category,
            scope_type,
            scope_value,
            start_date,
            end_date,
            limit_base,
            limit_base_minor,
            include_mandatory,
        },
    )
    .map_err(core_err)
    .and_then(|row| budget_to_dict(py, row))
}

#[pyfunction]
fn budget_delete(db_path: &str, budget_id: i64) -> PyResult<()> {
    storage_budget_delete(db_path, budget_id).map_err(core_err)
}

#[pyfunction]
fn budget_update_limit(
    py: Python<'_>,
    db_path: &str,
    budget_id: i64,
    limit_base: f64,
    limit_base_minor: i64,
) -> PyResult<Py<PyAny>> {
    storage_budget_update_limit(db_path, budget_id, limit_base, limit_base_minor)
        .map_err(core_err)
        .and_then(|row| budget_to_dict(py, row))
}

#[pyfunction]
fn budget_replace_rows(db_path: &str, rows: Vec<BudgetRowPayload>) -> PyResult<()> {
    let payloads: Vec<_> = rows.into_iter().map(budget_tuple_to_payload).collect();
    storage_budget_replace_rows(db_path, &payloads).map_err(core_err)
}

#[pyfunction]
fn budget_spent_minor(
    db_path: &str,
    scope_type: &str,
    scope_value: &str,
    start_date: &str,
    end_date: &str,
    include_mandatory: bool,
) -> PyResult<i64> {
    storage_budget_spent_minor(
        db_path,
        scope_type,
        scope_value,
        start_date,
        end_date,
        include_mandatory,
    )
    .map_err(core_err)
}

#[pyfunction]
fn budget_batch_spent_minor(
    db_path: &str,
    budgets: Vec<(i64, String, String, String, String, bool)>,
) -> PyResult<Vec<(i64, i64)>> {
    storage_budget_batch_spent_minor(db_path, &budgets).map_err(core_err)
}

#[pyfunction]
fn budget_overlap_exists(
    db_path: &str,
    scope_type: &str,
    scope_value: &str,
    start_date: &str,
    end_date: &str,
    exclude_id: Option<i64>,
) -> PyResult<bool> {
    storage_budget_overlap_exists(
        db_path,
        scope_type,
        scope_value,
        start_date,
        end_date,
        exclude_id,
    )
    .map_err(core_err)
}

#[pyfunction]
fn debt_payment_total_minor(db_path: &str, debt_id: i64) -> PyResult<i64> {
    storage_debt_payment_total_minor(db_path, debt_id).map_err(core_err)
}

#[pyfunction]
fn debt_rows(py: Python<'_>, db_path: &str) -> PyResult<Vec<Py<PyAny>>> {
    storage_debt_rows(db_path)
        .map_err(core_err)?
        .into_iter()
        .map(|row| debt_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn debt_payment_rows(
    py: Python<'_>,
    db_path: &str,
    debt_id: Option<i64>,
) -> PyResult<Vec<Py<PyAny>>> {
    storage_debt_payment_rows(db_path, debt_id)
        .map_err(core_err)?
        .into_iter()
        .map(|row| debt_payment_to_dict(py, row))
        .collect()
}

#[pyfunction]
fn debt_create_obligation(
    py: Python<'_>,
    db_path: &str,
    debt_payload: &Bound<'_, PyDict>,
    open_record_payload: &Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    let debt = debt_from_dict(debt_payload)?;
    let record = debt_record_from_dict(open_record_payload)?;
    storage_debt_create_obligation(db_path, &debt, &record)
        .map_err(core_err)
        .and_then(|row| debt_to_dict(py, row))
}

#[pyfunction]
fn debt_delete(db_path: &str, debt_id: i64) -> PyResult<()> {
    storage_debt_delete(db_path, debt_id).map_err(core_err)
}

#[pyfunction]
fn debt_register_payment(
    py: Python<'_>,
    db_path: &str,
    debt_id: i64,
    payment_payload: &Bound<'_, PyDict>,
    payment_record_payload: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<PyAny>> {
    let payment = debt_payment_from_dict(payment_payload)?;
    let record = payment_record_payload
        .map(debt_record_from_dict)
        .transpose()?;
    storage_debt_register_payment(db_path, debt_id, &payment, record.as_ref())
        .map_err(core_err)
        .and_then(|row| debt_payment_to_dict(py, row))
}

#[pyfunction]
fn debt_delete_payment(
    py: Python<'_>,
    db_path: &str,
    payment_id: i64,
    delete_linked_record: bool,
) -> PyResult<Py<PyAny>> {
    storage_debt_delete_payment(db_path, payment_id, delete_linked_record)
        .map_err(core_err)
        .and_then(|row| debt_to_dict(py, row))
}

#[pyfunction]
fn debt_replace_rows(
    db_path: &str,
    debts: Vec<Bound<'_, PyDict>>,
    payments: Vec<Bound<'_, PyDict>>,
) -> PyResult<()> {
    let debt_payloads = debts
        .iter()
        .map(debt_from_dict)
        .collect::<PyResult<Vec<_>>>()?;
    let payment_payloads = payments
        .iter()
        .map(debt_payment_from_dict)
        .collect::<PyResult<Vec<_>>>()?;
    storage_debt_replace_rows(db_path, &debt_payloads, &payment_payloads).map_err(core_err)
}

#[pyfunction]
fn debt_recalculate_payload(py: Python<'_>, db_path: &str, debt_id: i64) -> PyResult<Py<PyAny>> {
    let row = storage_debt_recalculate_payload(db_path, debt_id).map_err(core_err)?;
    let payload = PyDict::new(py);
    payload.set_item("remaining_amount_minor", row.remaining_amount_minor)?;
    payload.set_item("status", row.status)?;
    payload.set_item("closed_at", row.closed_at)?;
    Ok(payload.into_any().unbind())
}

#[pyfunction]
fn debt_validate_payment_amount(
    remaining_amount_minor: i64,
    payment_amount_minor: i64,
) -> PyResult<i64> {
    storage_debt_validate_payment_amount(remaining_amount_minor, payment_amount_minor)
        .map_err(core_err)
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
    m.add_function(wrap_pyfunction!(audit_run, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_savings_rate, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_burn_rate, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_spending_by_category, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_income_by_category, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_spending_by_tag, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_tag_coverage, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_period_snapshot, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_period_snapshot_compact, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_refresh_snapshot_compact, m)?)?;
    m.add_function(wrap_pyfunction!(metrics_monthly_summary, m)?)?;
    m.add_function(wrap_pyfunction!(timeline_monthly_cashflow, m)?)?;
    m.add_function(wrap_pyfunction!(timeline_cumulative_income_expense, m)?)?;
    m.add_function(wrap_pyfunction!(timeline_net_worth_monthly_deltas, m)?)?;
    m.add_function(wrap_pyfunction!(currency_rate_for, m)?)?;
    m.add_function(wrap_pyfunction!(currency_default_rates_for_base, m)?)?;
    m.add_function(wrap_pyfunction!(currency_resolve_provider_order, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_net_income_for_period, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_available_months, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_history_months, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_validate_structure, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_monthly_payload, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_item_rows, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_subitem_rows, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_create_item, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_update_item_pct, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_update_item_name, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_update_item_order, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_delete_item, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_create_subitem, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_update_subitem_pct, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_update_subitem_name, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_update_subitem_order, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_delete_subitem, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_replace_structure, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_is_month_fixed, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_is_month_auto_fixed, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_write_frozen_row, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_unfreeze_month, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_frozen_rows, m)?)?;
    m.add_function(wrap_pyfunction!(distribution_replace_frozen_rows, m)?)?;
    m.add_function(wrap_pyfunction!(budget_rows, m)?)?;
    m.add_function(wrap_pyfunction!(budget_create, m)?)?;
    m.add_function(wrap_pyfunction!(budget_delete, m)?)?;
    m.add_function(wrap_pyfunction!(budget_update_limit, m)?)?;
    m.add_function(wrap_pyfunction!(budget_replace_rows, m)?)?;
    m.add_function(wrap_pyfunction!(budget_spent_minor, m)?)?;
    m.add_function(wrap_pyfunction!(budget_batch_spent_minor, m)?)?;
    m.add_function(wrap_pyfunction!(budget_overlap_exists, m)?)?;
    m.add_function(wrap_pyfunction!(debt_rows, m)?)?;
    m.add_function(wrap_pyfunction!(debt_payment_rows, m)?)?;
    m.add_function(wrap_pyfunction!(debt_create_obligation, m)?)?;
    m.add_function(wrap_pyfunction!(debt_delete, m)?)?;
    m.add_function(wrap_pyfunction!(debt_register_payment, m)?)?;
    m.add_function(wrap_pyfunction!(debt_delete_payment, m)?)?;
    m.add_function(wrap_pyfunction!(debt_replace_rows, m)?)?;
    m.add_function(wrap_pyfunction!(debt_payment_total_minor, m)?)?;
    m.add_function(wrap_pyfunction!(debt_recalculate_payload, m)?)?;
    m.add_function(wrap_pyfunction!(debt_validate_payment_amount, m)?)?;
    m.add_function(wrap_pyfunction!(storage_clear_read_cache, m)?)?;
    m.add_function(wrap_pyfunction!(sync_start_daemon, m)?)?;
    m.add_function(wrap_pyfunction!(sync_stop_daemon, m)?)?;
    m.add_function(wrap_pyfunction!(sync_status, m)?)?;
    m.add_function(wrap_pyfunction!(sync_discover_peers, m)?)?;
    m.add_function(wrap_pyfunction!(sync_push_once, m)?)?;
    Ok(())
}
