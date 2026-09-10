use ledgera_engine_storage::{
    AuditFindingRow, BudgetCreatePayload, BudgetPayload, BudgetResultPayload, DebtCreatePayload,
    DebtPayload, DebtPaymentPayload, DebtPaymentRequestPayload, MandatoryAddToRecordsPayload,
    MandatoryAutoPayResult, MandatoryExpenseRow, MandatoryExportResult, MandatoryImportResult,
    MandatoryTemplateCreatePayload, MandatoryTemplateUpdatePayload, OperationDeleteResult,
    OperationExportResult, OperationImportResult, RecordFilterPayload, RecordRow,
    ReportCategoryRow, ReportDebtRow, ReportExportResult, ReportFilters, ReportMonthlyRow,
    ReportOperationRow, ReportResult, ReportTagRow, StandaloneRecordCreatePayload,
    StandaloneRecordUpdatePayload, TagColorAssignment as StorageTagColorAssignment,
    TransferCreatePayload, TransferRow, TransferUpdatePayload, WalletBalanceRow,
    WalletCreatePayload, WalletRow, audit_run_for_date, base_currency_code, budget_create,
    budget_delete, budget_results, budget_rows, budget_update_limit,
    create_standalone_record_with_tag_colors, create_transfer, create_wallet, current_local_date,
    debt_close_validated, debt_create, debt_delete, debt_delete_payment, debt_payment_rows,
    debt_register_payment_validated, debt_register_write_off_validated, debt_rows,
    delete_all_operations, delete_operations_selection, delete_standalone_record, delete_transfer,
    delete_wallet, distinct_record_categories, distinct_record_descriptions, export_mandatory_csv,
    export_mandatory_xlsx, export_records_csv, export_records_xlsx, filtered_record_list_rows,
    import_mandatory_csv, import_mandatory_xlsx, import_records_csv, import_records_xlsx,
    mandatory_add_to_records, mandatory_apply_auto_payments, mandatory_expense_row,
    mandatory_expense_rows, mandatory_template_create, mandatory_template_delete,
    mandatory_template_delete_all, mandatory_template_update, normalize_tag_colors,
    operation_suggestions, preview_import_mandatory_csv, preview_import_mandatory_xlsx,
    preview_import_records_csv, preview_import_records_xlsx, report_export_csv, report_export_pdf,
    report_export_xlsx, report_generate, standalone_record_get_row, tag_color_palette,
    tag_color_rows, tag_names, transfer_get_row, update_standalone_record_with_tag_colors,
    update_transfer, wallet_balance_row, wallet_balance_rows, wallet_list_rows,
};
use std::fmt;
use std::path::Path;

uniffi::include_scaffolding!("ledgera_engine");

#[derive(Debug, Clone, Default, PartialEq)]
pub struct RecordFilterDto {
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub wallet_id: Option<i64>,
    pub record_type: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CreateRecordRequest {
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
pub struct UpdateRecordRequest {
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

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TagColorAssignment {
    pub name: String,
    pub color: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TagColorDto {
    pub name: String,
    pub color: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CreateTransferRequest {
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
pub struct CreateTransferResult {
    pub transfer_id: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct UpdateTransferRequest {
    pub from_wallet_id: i64,
    pub to_wallet_id: i64,
    pub date: String,
    pub amount: String,
    pub currency: String,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct UpdateTransferResult {
    pub transfer_id: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CreateWalletRequest {
    pub name: String,
    pub currency: String,
    pub initial_balance: String,
    pub allow_negative: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CreateDebtRequest {
    pub kind: String,
    pub contact_name: String,
    pub wallet_id: i64,
    pub amount: String,
    pub currency: String,
    pub created_at: String,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RegisterDebtPaymentRequest {
    pub debt_id: i64,
    pub wallet_id: Option<i64>,
    pub amount: String,
    pub payment_date: String,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CreateMandatoryTemplateRequest {
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
pub struct UpdateMandatoryTemplateRequest {
    pub wallet_id: i64,
    pub amount_base: String,
    pub period: String,
    pub date: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct AddMandatoryToRecordsRequest {
    pub template_id: i64,
    pub date: String,
    pub wallet_id: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CreateBudgetRequest {
    pub category: String,
    pub scope_type: String,
    pub scope_value: String,
    pub start_date: String,
    pub end_date: String,
    pub limit_base: String,
    pub include_mandatory: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BudgetDto {
    pub id: i64,
    pub category: String,
    pub scope_type: String,
    pub scope_value: String,
    pub start_date: String,
    pub end_date: String,
    pub limit_base: String,
    pub limit_base_minor: i64,
    pub include_mandatory: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BudgetResultDto {
    pub budget: BudgetDto,
    pub spent_base: String,
    pub spent_minor: i64,
    pub remaining_base: String,
    pub usage_pct: f64,
    pub time_pct: f64,
    pub status: String,
    pub pace_status: String,
    pub forecast_remaining_base: Option<String>,
    pub forecast_delta_base: Option<String>,
    pub forecast_days_left: Option<i64>,
    pub forecast_status_key: Option<String>,
    pub forecast_status_params: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletDeleteResultDto {
    pub wallet_id: i64,
    pub action: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct OperationDeleteResultDto {
    pub deleted_records: i64,
    pub deleted_transfers: i64,
    pub deleted_debt_linked_records: i64,
    pub skipped_records: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct OperationImportResultDto {
    pub imported: i64,
    pub skipped: i64,
    pub errors: Vec<String>,
    pub dry_run: bool,
    pub blocking_errors: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct OperationExportResultDto {
    pub exported_rows: i64,
    pub path: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct OperationSuggestionsDto {
    pub tags: Vec<String>,
    pub income_categories: Vec<String>,
    pub expense_categories: Vec<String>,
    pub descriptions: Vec<String>,
    pub income_descriptions: Vec<String>,
    pub expense_descriptions: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MandatoryImportResultDto {
    pub imported: i64,
    pub skipped: i64,
    pub errors: Vec<String>,
    pub dry_run: bool,
    pub blocking_errors: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MandatoryExportResultDto {
    pub exported_rows: i64,
    pub path: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct AuditFindingDto {
    pub check: String,
    pub severity: String,
    pub message: String,
    pub entity: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RecordDto {
    pub id: i64,
    pub record_type: String,
    pub date: String,
    pub wallet_id: i64,
    pub transfer_id: Option<i64>,
    pub related_debt_id: Option<i64>,
    pub amount_original: String,
    pub currency: String,
    pub rate_at_operation: String,
    pub amount_base: String,
    pub category: String,
    pub description: String,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletDto {
    pub id: i64,
    pub name: String,
    pub currency: String,
    pub initial_balance: String,
    pub system: bool,
    pub allow_negative: bool,
    pub is_active: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WalletBalanceDto {
    pub wallet_id: i64,
    pub name: String,
    pub currency: String,
    pub balance: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TransferDto {
    pub id: i64,
    pub from_wallet_id: i64,
    pub to_wallet_id: i64,
    pub date: String,
    pub amount_original: String,
    pub currency: String,
    pub rate_at_operation: String,
    pub amount_base: String,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DebtDto {
    pub id: i64,
    pub contact_name: String,
    pub kind: String,
    pub total_amount: String,
    pub remaining_amount: String,
    pub currency: String,
    pub interest_rate: String,
    pub status: String,
    pub created_at: String,
    pub closed_at: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DebtPaymentDto {
    pub id: i64,
    pub debt_id: i64,
    pub record_id: Option<i64>,
    pub operation_type: String,
    pub principal_paid: String,
    pub is_write_off: bool,
    pub payment_date: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MandatoryTemplateDto {
    pub id: i64,
    pub wallet_id: i64,
    pub amount_original: String,
    pub currency: String,
    pub rate_at_operation: String,
    pub amount_base: String,
    pub category: String,
    pub description: String,
    pub period: String,
    pub date: String,
    pub auto_pay: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MandatoryAutoPayResultDto {
    pub created_records: Vec<RecordDto>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EngineStatusDto {
    pub ok: bool,
    pub db_path: String,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportFiltersDto {
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
pub struct ReportSummaryDto {
    pub net_worth_fixed: f64,
    pub net_worth_current: f64,
    pub initial_balance: f64,
    pub records_total_fixed: f64,
    pub records_total_current: f64,
    pub final_balance_fixed: f64,
    pub final_balance_current: f64,
    pub fx_difference: f64,
    pub records_count: i64,
    pub balance_label: String,
    pub active_tag: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportOperationRowDto {
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
pub struct ReportMonthlyRowDto {
    pub month: String,
    pub income: f64,
    pub expenses: f64,
    pub income_current: f64,
    pub expenses_current: f64,
}
#[derive(Debug, Clone, PartialEq)]
pub struct ReportCategoryRowDto {
    pub category: String,
    pub operations_count: i64,
    pub total_base: f64,
    pub total_current: f64,
}
#[derive(Debug, Clone, PartialEq)]
pub struct ReportTagRowDto {
    pub tag: String,
    pub operations_count: i64,
    pub total_base: f64,
    pub total_current: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportDebtRowDto {
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
pub struct ReportResultDto {
    pub title: String,
    pub base_currency: String,
    pub display_currency: String,
    pub filters: ReportFiltersDto,
    pub summary: ReportSummaryDto,
    pub operations: Vec<ReportOperationRowDto>,
    pub monthly: Vec<ReportMonthlyRowDto>,
    pub categories: Vec<ReportCategoryRowDto>,
    pub tags: Vec<ReportTagRowDto>,
    pub debts: Vec<ReportDebtRowDto>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReportExportResultDto {
    pub exported_rows: i64,
    pub path: String,
}

#[derive(Debug)]
pub enum LedgeraEngineError {
    Validation { message: String },
    Storage { message: String },
}

impl fmt::Display for LedgeraEngineError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Validation { message } | Self::Storage { message } => {
                formatter.write_str(message)
            }
        }
    }
}

impl std::error::Error for LedgeraEngineError {}

pub struct LedgeraEngine {
    db_path: String,
}

impl LedgeraEngine {
    pub fn new(db_path: String) -> Self {
        Self { db_path }
    }

    pub fn engine_status(&self) -> EngineStatusDto {
        let ok = Path::new(&self.db_path).exists();
        EngineStatusDto {
            ok,
            db_path: self.db_path.clone(),
            message: if ok {
                "ready".to_owned()
            } else {
                "database file does not exist".to_owned()
            },
        }
    }

    pub fn generate_report(
        &self,
        filters: ReportFiltersDto,
    ) -> Result<ReportResultDto, LedgeraEngineError> {
        report_generate(
            &self.db_path,
            &ReportFilters {
                wallet_id: filters.wallet_id,
                period_start: filters.period_start,
                period_end: filters.period_end,
                category: filters.category,
                tag: filters.tag,
                tag_mode: filters.tag_mode,
                totals_mode: filters.totals_mode,
                group_by_category: filters.group_by_category,
            },
        )
        .map(report_to_dto)
        .map_err(storage_error)
    }

    pub fn export_report_csv(
        &self,
        filters: ReportFiltersDto,
        path: String,
    ) -> Result<ReportExportResultDto, LedgeraEngineError> {
        report_export_csv(&self.db_path, &report_filters_from_dto(filters), &path)
            .map(report_export_to_dto)
            .map_err(storage_error)
    }

    pub fn export_report_xlsx(
        &self,
        filters: ReportFiltersDto,
        path: String,
    ) -> Result<ReportExportResultDto, LedgeraEngineError> {
        report_export_xlsx(&self.db_path, &report_filters_from_dto(filters), &path)
            .map(report_export_to_dto)
            .map_err(storage_error)
    }

    pub fn export_report_pdf(
        &self,
        filters: ReportFiltersDto,
        path: String,
    ) -> Result<ReportExportResultDto, LedgeraEngineError> {
        report_export_pdf(&self.db_path, &report_filters_from_dto(filters), &path)
            .map(report_export_to_dto)
            .map_err(storage_error)
    }

    pub fn base_currency(&self) -> Result<String, LedgeraEngineError> {
        base_currency_code(&self.db_path).map_err(storage_error)
    }

    pub fn list_records(
        &self,
        filter: RecordFilterDto,
    ) -> Result<Vec<RecordDto>, LedgeraEngineError> {
        let payload = RecordFilterPayload {
            start_date: filter.start_date,
            end_date: filter.end_date,
            wallet_id: filter.wallet_id,
            record_type: filter.record_type,
        };
        filtered_record_list_rows(&self.db_path, &payload)
            .map(|rows| rows.into_iter().map(record_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn get_record(&self, record_id: i64) -> Result<Option<RecordDto>, LedgeraEngineError> {
        standalone_record_get_row(&self.db_path, record_id)
            .map(|row| row.map(record_to_dto))
            .map_err(storage_error)
    }

    pub fn create_record(
        &self,
        request: CreateRecordRequest,
    ) -> Result<RecordDto, LedgeraEngineError> {
        self.create_record_with_tag_colors(request, Vec::new())
    }

    pub fn create_record_with_tag_colors(
        &self,
        request: CreateRecordRequest,
        tag_colors: Vec<TagColorAssignment>,
    ) -> Result<RecordDto, LedgeraEngineError> {
        validate_create_request(&request)?;
        let payload = StandaloneRecordCreatePayload {
            record_type: request.record_type,
            date: request.date,
            wallet_id: request.wallet_id,
            amount_original: request.amount_original,
            currency: request.currency,
            rate_at_operation: request.rate_at_operation,
            amount_base: request.amount_base,
            category: request.category,
            description: request.description,
            tags: request.tags,
        };
        let assignments = tag_colors
            .into_iter()
            .map(|assignment| StorageTagColorAssignment {
                name: assignment.name,
                color: assignment.color,
            })
            .collect::<Vec<_>>();
        create_standalone_record_with_tag_colors(&self.db_path, &payload, &assignments)
            .map(record_to_dto)
            .map_err(storage_error)
    }

    pub fn update_record(
        &self,
        record_id: i64,
        request: UpdateRecordRequest,
    ) -> Result<RecordDto, LedgeraEngineError> {
        self.update_record_with_tag_colors(record_id, request, Vec::new())
    }

    pub fn update_record_with_tag_colors(
        &self,
        record_id: i64,
        request: UpdateRecordRequest,
        tag_colors: Vec<TagColorAssignment>,
    ) -> Result<RecordDto, LedgeraEngineError> {
        validate_update_request(&request)?;
        let payload = StandaloneRecordUpdatePayload {
            record_type: request.record_type,
            date: request.date,
            wallet_id: request.wallet_id,
            amount_original: request.amount_original,
            currency: request.currency,
            rate_at_operation: request.rate_at_operation,
            amount_base: request.amount_base,
            category: request.category,
            description: request.description,
            tags: request.tags,
        };
        let assignments = tag_colors
            .into_iter()
            .map(|assignment| StorageTagColorAssignment {
                name: assignment.name,
                color: assignment.color,
            })
            .collect::<Vec<_>>();
        update_standalone_record_with_tag_colors(&self.db_path, record_id, &payload, &assignments)
            .map(record_to_dto)
            .map_err(storage_error)
    }

    pub fn delete_record(&self, record_id: i64) -> Result<bool, LedgeraEngineError> {
        delete_standalone_record(&self.db_path, record_id).map_err(storage_error)
    }

    pub fn create_transfer(
        &self,
        request: CreateTransferRequest,
    ) -> Result<CreateTransferResult, LedgeraEngineError> {
        let payload = TransferCreatePayload {
            from_wallet_id: request.from_wallet_id,
            to_wallet_id: request.to_wallet_id,
            date: request.date,
            amount: request.amount,
            currency: request.currency,
            description: request.description,
            commission_amount: request.commission_amount,
            commission_currency: request.commission_currency,
        };
        create_transfer(&self.db_path, &payload)
            .map(|row| CreateTransferResult {
                transfer_id: row.id,
            })
            .map_err(storage_error)
    }

    pub fn get_transfer(
        &self,
        transfer_id: i64,
    ) -> Result<Option<TransferDto>, LedgeraEngineError> {
        transfer_get_row(&self.db_path, transfer_id)
            .map(|row| row.map(transfer_to_dto))
            .map_err(storage_error)
    }

    pub fn update_transfer(
        &self,
        transfer_id: i64,
        request: UpdateTransferRequest,
    ) -> Result<UpdateTransferResult, LedgeraEngineError> {
        let payload = TransferUpdatePayload {
            from_wallet_id: request.from_wallet_id,
            to_wallet_id: request.to_wallet_id,
            date: request.date,
            amount: request.amount,
            currency: request.currency,
            description: request.description,
        };
        update_transfer(&self.db_path, transfer_id, &payload)
            .map(|row| UpdateTransferResult {
                transfer_id: row.id,
            })
            .map_err(storage_error)
    }

    pub fn delete_transfer(&self, transfer_id: i64) -> Result<bool, LedgeraEngineError> {
        delete_transfer(&self.db_path, transfer_id).map_err(storage_error)
    }

    pub fn delete_all_operations(&self) -> Result<OperationDeleteResultDto, LedgeraEngineError> {
        delete_all_operations(&self.db_path)
            .map(operation_delete_to_dto)
            .map_err(storage_error)
    }

    pub fn delete_operations_selection(
        &self,
        record_ids: Vec<i64>,
        transfer_ids: Vec<i64>,
    ) -> Result<OperationDeleteResultDto, LedgeraEngineError> {
        delete_operations_selection(&self.db_path, &record_ids, &transfer_ids)
            .map(operation_delete_to_dto)
            .map_err(storage_error)
    }

    pub fn preview_import_records_csv(
        &self,
        path: String,
    ) -> Result<OperationImportResultDto, LedgeraEngineError> {
        preview_import_records_csv(&self.db_path, &path)
            .map(operation_import_to_dto)
            .map_err(storage_error)
    }

    pub fn import_records_csv(
        &self,
        path: String,
    ) -> Result<OperationImportResultDto, LedgeraEngineError> {
        import_records_csv(&self.db_path, &path)
            .map(operation_import_to_dto)
            .map_err(storage_error)
    }

    pub fn export_records_csv(
        &self,
        path: String,
    ) -> Result<OperationExportResultDto, LedgeraEngineError> {
        export_records_csv(&self.db_path, &path)
            .map(operation_export_to_dto)
            .map_err(storage_error)
    }

    pub fn preview_import_records_xlsx(
        &self,
        path: String,
    ) -> Result<OperationImportResultDto, LedgeraEngineError> {
        preview_import_records_xlsx(&self.db_path, &path)
            .map(operation_import_to_dto)
            .map_err(storage_error)
    }

    pub fn import_records_xlsx(
        &self,
        path: String,
    ) -> Result<OperationImportResultDto, LedgeraEngineError> {
        import_records_xlsx(&self.db_path, &path)
            .map(operation_import_to_dto)
            .map_err(storage_error)
    }

    pub fn export_records_xlsx(
        &self,
        path: String,
    ) -> Result<OperationExportResultDto, LedgeraEngineError> {
        export_records_xlsx(&self.db_path, &path)
            .map(operation_export_to_dto)
            .map_err(storage_error)
    }

    pub fn list_tags(&self) -> Result<Vec<String>, LedgeraEngineError> {
        tag_names(&self.db_path).map_err(storage_error)
    }

    pub fn list_categories(&self, record_type: String) -> Result<Vec<String>, LedgeraEngineError> {
        distinct_record_categories(&self.db_path, &record_type).map_err(storage_error)
    }

    pub fn list_record_descriptions(
        &self,
        record_type: Option<String>,
    ) -> Result<Vec<String>, LedgeraEngineError> {
        distinct_record_descriptions(&self.db_path, record_type.as_deref()).map_err(storage_error)
    }

    pub fn operation_suggestions(&self) -> Result<OperationSuggestionsDto, LedgeraEngineError> {
        operation_suggestions(&self.db_path)
            .map(|suggestions| OperationSuggestionsDto {
                tags: suggestions.tags,
                income_categories: suggestions.income_categories,
                expense_categories: suggestions.expense_categories,
                descriptions: suggestions.descriptions,
                income_descriptions: suggestions.income_descriptions,
                expense_descriptions: suggestions.expense_descriptions,
            })
            .map_err(storage_error)
    }

    pub fn list_tag_colors(&self) -> Result<Vec<TagColorDto>, LedgeraEngineError> {
        tag_color_rows(&self.db_path)
            .map(|rows| {
                rows.into_iter()
                    .map(|row| TagColorDto {
                        name: row.name,
                        color: row.color,
                    })
                    .collect()
            })
            .map_err(storage_error)
    }

    pub fn tag_color_palette(&self) -> Vec<String> {
        tag_color_palette()
    }

    pub fn normalize_tag_colors(&self) -> Result<(), LedgeraEngineError> {
        normalize_tag_colors(&self.db_path).map_err(storage_error)
    }

    pub fn list_wallets(&self) -> Result<Vec<WalletDto>, LedgeraEngineError> {
        wallet_list_rows(&self.db_path)
            .map(|rows| rows.into_iter().map(wallet_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn create_wallet(
        &self,
        request: CreateWalletRequest,
    ) -> Result<WalletDto, LedgeraEngineError> {
        let payload = WalletCreatePayload {
            name: request.name,
            currency: request.currency,
            initial_balance: request.initial_balance,
            allow_negative: request.allow_negative,
        };
        create_wallet(&self.db_path, &payload)
            .map(wallet_to_dto)
            .map_err(storage_error)
    }

    pub fn delete_wallet(
        &self,
        wallet_id: i64,
    ) -> Result<WalletDeleteResultDto, LedgeraEngineError> {
        delete_wallet(&self.db_path, wallet_id)
            .map(|result| WalletDeleteResultDto {
                wallet_id: result.wallet_id,
                action: result.action,
            })
            .map_err(storage_error)
    }

    pub fn list_budgets(&self) -> Result<Vec<BudgetDto>, LedgeraEngineError> {
        budget_rows(&self.db_path)
            .map(|rows| rows.into_iter().map(budget_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn list_budget_results(
        &self,
        today: Option<String>,
    ) -> Result<Vec<BudgetResultDto>, LedgeraEngineError> {
        budget_results(&self.db_path, today.as_deref())
            .map(|rows| rows.into_iter().map(budget_result_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn create_budget(
        &self,
        request: CreateBudgetRequest,
    ) -> Result<BudgetDto, LedgeraEngineError> {
        let limit_value = request
            .limit_base
            .parse::<f64>()
            .map_err(|error| validation_error(&error.to_string()))?;
        let limit_base_minor = (limit_value * 100.0).round() as i64;
        budget_create(
            &self.db_path,
            BudgetCreatePayload {
                category: &request.category,
                scope_type: &request.scope_type,
                scope_value: &request.scope_value,
                start_date: &request.start_date,
                end_date: &request.end_date,
                limit_base: limit_value,
                limit_base_minor,
                include_mandatory: request.include_mandatory,
            },
        )
        .map(budget_to_dto)
        .map_err(storage_error)
    }

    pub fn update_budget_limit(
        &self,
        budget_id: i64,
        limit_base: String,
    ) -> Result<BudgetDto, LedgeraEngineError> {
        let limit_value = limit_base
            .parse::<f64>()
            .map_err(|error| validation_error(&error.to_string()))?;
        let limit_base_minor = (limit_value * 100.0).round() as i64;
        budget_update_limit(&self.db_path, budget_id, limit_value, limit_base_minor)
            .map(budget_to_dto)
            .map_err(storage_error)
    }

    pub fn delete_budget(&self, budget_id: i64) -> Result<bool, LedgeraEngineError> {
        budget_delete(&self.db_path, budget_id)
            .map(|_| true)
            .map_err(storage_error)
    }

    pub fn list_debts(&self) -> Result<Vec<DebtDto>, LedgeraEngineError> {
        debt_rows(&self.db_path)
            .map(|rows| rows.into_iter().map(debt_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn list_debt_payments(
        &self,
        debt_id: i64,
    ) -> Result<Vec<DebtPaymentDto>, LedgeraEngineError> {
        debt_payment_rows(&self.db_path, Some(debt_id))
            .map(|rows| rows.into_iter().map(debt_payment_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn create_debt(&self, request: CreateDebtRequest) -> Result<DebtDto, LedgeraEngineError> {
        let payload = DebtCreatePayload {
            kind: request.kind,
            contact_name: request.contact_name,
            wallet_id: request.wallet_id,
            amount: request.amount,
            currency: request.currency,
            created_at: request.created_at,
            description: request.description,
        };
        debt_create(&self.db_path, &payload)
            .map(debt_to_dto)
            .map_err(storage_error)
    }

    pub fn register_debt_payment(
        &self,
        request: RegisterDebtPaymentRequest,
    ) -> Result<DebtPaymentDto, LedgeraEngineError> {
        debt_register_payment_validated(&self.db_path, &debt_payment_request_payload(request))
            .map(debt_payment_to_dto)
            .map_err(storage_error)
    }

    pub fn register_debt_write_off(
        &self,
        request: RegisterDebtPaymentRequest,
    ) -> Result<DebtPaymentDto, LedgeraEngineError> {
        debt_register_write_off_validated(&self.db_path, &debt_payment_request_payload(request))
            .map(debt_payment_to_dto)
            .map_err(storage_error)
    }

    pub fn close_debt(
        &self,
        request: RegisterDebtPaymentRequest,
    ) -> Result<DebtDto, LedgeraEngineError> {
        debt_close_validated(&self.db_path, &debt_payment_request_payload(request))
            .map(debt_to_dto)
            .map_err(storage_error)
    }

    pub fn delete_debt(&self, debt_id: i64) -> Result<bool, LedgeraEngineError> {
        debt_delete(&self.db_path, debt_id)
            .map(|_| true)
            .map_err(storage_error)
    }

    pub fn delete_debt_payment(
        &self,
        payment_id: i64,
        delete_linked_record: bool,
    ) -> Result<DebtDto, LedgeraEngineError> {
        debt_delete_payment(&self.db_path, payment_id, delete_linked_record)
            .map(debt_to_dto)
            .map_err(storage_error)
    }

    pub fn list_mandatory_templates(
        &self,
    ) -> Result<Vec<MandatoryTemplateDto>, LedgeraEngineError> {
        mandatory_expense_rows(&self.db_path)
            .map(|rows| rows.into_iter().map(mandatory_template_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn get_mandatory_template(
        &self,
        template_id: i64,
    ) -> Result<Option<MandatoryTemplateDto>, LedgeraEngineError> {
        mandatory_expense_row(&self.db_path, template_id)
            .map(|row| row.map(mandatory_template_to_dto))
            .map_err(storage_error)
    }

    pub fn create_mandatory_template(
        &self,
        request: CreateMandatoryTemplateRequest,
    ) -> Result<MandatoryTemplateDto, LedgeraEngineError> {
        let payload = MandatoryTemplateCreatePayload {
            wallet_id: request.wallet_id,
            amount_original: request.amount_original,
            currency: request.currency,
            rate_at_operation: request.rate_at_operation,
            amount_base: request.amount_base,
            category: request.category,
            description: request.description,
            period: request.period,
            date: request.date,
        };
        mandatory_template_create(&self.db_path, &payload)
            .map(mandatory_template_to_dto)
            .map_err(storage_error)
    }

    pub fn update_mandatory_template(
        &self,
        template_id: i64,
        request: UpdateMandatoryTemplateRequest,
    ) -> Result<MandatoryTemplateDto, LedgeraEngineError> {
        let payload = MandatoryTemplateUpdatePayload {
            wallet_id: request.wallet_id,
            amount_base: request.amount_base,
            period: request.period,
            date: request.date,
        };
        mandatory_template_update(&self.db_path, template_id, &payload)
            .map(mandatory_template_to_dto)
            .map_err(storage_error)
    }

    pub fn delete_mandatory_template(&self, template_id: i64) -> Result<bool, LedgeraEngineError> {
        mandatory_template_delete(&self.db_path, template_id).map_err(storage_error)
    }

    pub fn delete_all_mandatory_templates(&self) -> Result<i64, LedgeraEngineError> {
        mandatory_template_delete_all(&self.db_path).map_err(storage_error)
    }

    pub fn add_mandatory_to_records(
        &self,
        request: AddMandatoryToRecordsRequest,
    ) -> Result<RecordDto, LedgeraEngineError> {
        let payload = MandatoryAddToRecordsPayload {
            template_id: request.template_id,
            date: request.date,
            wallet_id: request.wallet_id,
        };
        mandatory_add_to_records(&self.db_path, &payload)
            .map(record_to_dto)
            .map_err(storage_error)
    }

    pub fn apply_mandatory_auto_payments(
        &self,
        today: String,
    ) -> Result<MandatoryAutoPayResultDto, LedgeraEngineError> {
        mandatory_apply_auto_payments(&self.db_path, &today)
            .map(mandatory_auto_pay_to_dto)
            .map_err(storage_error)
    }

    pub fn preview_import_mandatory_csv(
        &self,
        path: String,
    ) -> Result<MandatoryImportResultDto, LedgeraEngineError> {
        preview_import_mandatory_csv(&self.db_path, &path)
            .map(mandatory_import_to_dto)
            .map_err(storage_error)
    }

    pub fn import_mandatory_csv(
        &self,
        path: String,
    ) -> Result<MandatoryImportResultDto, LedgeraEngineError> {
        import_mandatory_csv(&self.db_path, &path)
            .map(mandatory_import_to_dto)
            .map_err(storage_error)
    }

    pub fn export_mandatory_csv(
        &self,
        path: String,
    ) -> Result<MandatoryExportResultDto, LedgeraEngineError> {
        export_mandatory_csv(&self.db_path, &path)
            .map(mandatory_export_to_dto)
            .map_err(storage_error)
    }

    pub fn preview_import_mandatory_xlsx(
        &self,
        path: String,
    ) -> Result<MandatoryImportResultDto, LedgeraEngineError> {
        preview_import_mandatory_xlsx(&self.db_path, &path)
            .map(mandatory_import_to_dto)
            .map_err(storage_error)
    }

    pub fn import_mandatory_xlsx(
        &self,
        path: String,
    ) -> Result<MandatoryImportResultDto, LedgeraEngineError> {
        import_mandatory_xlsx(&self.db_path, &path)
            .map(mandatory_import_to_dto)
            .map_err(storage_error)
    }

    pub fn export_mandatory_xlsx(
        &self,
        path: String,
    ) -> Result<MandatoryExportResultDto, LedgeraEngineError> {
        export_mandatory_xlsx(&self.db_path, &path)
            .map(mandatory_export_to_dto)
            .map_err(storage_error)
    }

    pub fn audit_run(&self) -> Result<Vec<AuditFindingDto>, LedgeraEngineError> {
        audit_run_for_date(&self.db_path, &current_local_date_text())
            .map(|findings| findings.into_iter().map(audit_finding_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn wallet_balances(&self) -> Result<Vec<WalletBalanceDto>, LedgeraEngineError> {
        wallet_balance_rows(&self.db_path, None)
            .map(|rows| rows.into_iter().map(wallet_balance_to_dto).collect())
            .map_err(storage_error)
    }

    pub fn wallet_balance(
        &self,
        wallet_id: i64,
    ) -> Result<Option<WalletBalanceDto>, LedgeraEngineError> {
        wallet_balance_row(&self.db_path, wallet_id)
            .map(|row| row.map(wallet_balance_to_dto))
            .map_err(storage_error)
    }
}

fn validate_create_request(request: &CreateRecordRequest) -> Result<(), LedgeraEngineError> {
    let record_type = request.record_type.trim().to_lowercase();
    if record_type != "income" && record_type != "expense" {
        return Err(validation_error(
            "Only income and expense records are supported in alpha.4 Operations",
        ));
    }
    if request.date.trim().is_empty() {
        return Err(validation_error("Record date is required"));
    }
    validate_ymd_date(request.date.trim())?;
    if request.wallet_id <= 0 {
        return Err(validation_error("wallet_id must be positive"));
    }
    validate_currency_code(&request.currency)?;
    if request.category.trim().is_empty() {
        return Err(validation_error("Category is required"));
    }
    Ok(())
}

fn validate_update_request(request: &UpdateRecordRequest) -> Result<(), LedgeraEngineError> {
    let record_type = request.record_type.trim().to_lowercase();
    if record_type != "income" && record_type != "expense" {
        return Err(validation_error(
            "Only income and expense records are supported in beta.1 Operations",
        ));
    }
    if request.date.trim().is_empty() {
        return Err(validation_error("Record date is required"));
    }
    validate_ymd_date(request.date.trim())?;
    if request.wallet_id <= 0 {
        return Err(validation_error("wallet_id must be positive"));
    }
    validate_currency_code(&request.currency)?;
    if request.category.trim().is_empty() {
        return Err(validation_error("Category is required"));
    }
    Ok(())
}

fn validate_ymd_date(value: &str) -> Result<(), LedgeraEngineError> {
    let bytes = value.as_bytes();
    if bytes.len() != 10 || bytes[4] != b'-' || bytes[7] != b'-' {
        return Err(validation_error("Date must use YYYY-MM-DD format"));
    }
    let year = parse_date_part(value, 0, 4, "year")?;
    let month = parse_date_part(value, 5, 7, "month")?;
    let day = parse_date_part(value, 8, 10, "day")?;
    if !(1..=12).contains(&month) {
        return Err(validation_error("Date month must be between 01 and 12"));
    }
    let max_day = days_in_month(year, month);
    if day < 1 || day > max_day {
        return Err(validation_error(&format!(
            "Date day must be between 01 and {max_day:02}"
        )));
    }
    if (year, month, day) > current_local_date() {
        return Err(validation_error("Date cannot be in the future"));
    }
    Ok(())
}

fn parse_date_part(
    value: &str,
    start: usize,
    end: usize,
    name: &str,
) -> Result<i32, LedgeraEngineError> {
    let part = &value[start..end];
    if !part.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(validation_error(&format!(
            "Date {name} must contain digits only"
        )));
    }
    part.parse::<i32>()
        .map_err(|_| validation_error(&format!("Date {name} is invalid")))
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

fn is_leap_year(year: i32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn validate_currency_code(value: &str) -> Result<(), LedgeraEngineError> {
    let currency = value.trim();
    if currency.len() != 3 || !currency.bytes().all(|byte| byte.is_ascii_alphabetic()) {
        return Err(validation_error("Currency code must contain 3 letters"));
    }
    if !is_supported_currency(currency) {
        return Err(validation_error("Unsupported currency"));
    }
    Ok(())
}

fn report_to_dto(result: ReportResult) -> ReportResultDto {
    ReportResultDto {
        title: result.title,
        base_currency: result.base_currency,
        display_currency: result.display_currency,
        filters: ReportFiltersDto {
            wallet_id: result.filters.wallet_id,
            period_start: result.filters.period_start.clone(),
            period_end: result.filters.period_end.clone(),
            category: result.filters.category.clone(),
            tag: result.filters.tag.clone(),
            tag_mode: result.filters.tag_mode.clone(),
            totals_mode: result.filters.totals_mode.clone(),
            group_by_category: result.filters.group_by_category,
        },
        summary: ReportSummaryDto {
            net_worth_fixed: result.summary.net_worth_fixed,
            net_worth_current: result.summary.net_worth_current,
            initial_balance: result.summary.initial_balance,
            records_total_fixed: result.summary.records_total_fixed,
            records_total_current: result.summary.records_total_current,
            final_balance_fixed: result.summary.final_balance_fixed,
            final_balance_current: result.summary.final_balance_current,
            fx_difference: result.summary.fx_difference,
            records_count: result.summary.records_count,
            balance_label: result.summary.balance_label,
            active_tag: result.summary.active_tag,
        },
        operations: result
            .operations
            .into_iter()
            .map(report_operation_to_dto)
            .collect(),
        monthly: result
            .monthly
            .into_iter()
            .map(report_monthly_to_dto)
            .collect(),
        categories: result
            .categories
            .into_iter()
            .map(report_category_to_dto)
            .collect(),
        tags: result.tags.into_iter().map(report_tag_to_dto).collect(),
        debts: result.debts.into_iter().map(report_debt_to_dto).collect(),
    }
}

fn report_filters_from_dto(filters: ReportFiltersDto) -> ReportFilters {
    ReportFilters {
        wallet_id: filters.wallet_id,
        period_start: filters.period_start,
        period_end: filters.period_end,
        category: filters.category,
        tag: filters.tag,
        tag_mode: filters.tag_mode,
        totals_mode: filters.totals_mode,
        group_by_category: filters.group_by_category,
    }
}

fn report_export_to_dto(result: ReportExportResult) -> ReportExportResultDto {
    ReportExportResultDto {
        exported_rows: result.exported_rows,
        path: result.path,
    }
}

fn report_operation_to_dto(row: ReportOperationRow) -> ReportOperationRowDto {
    ReportOperationRowDto {
        date: row.date,
        type_label: row.type_label,
        kind: row.kind,
        category: row.category,
        tags_text: row.tags_text,
        amount_base: row.amount_base,
        amount_current: row.amount_current,
        description: row.description,
    }
}

fn report_monthly_to_dto(row: ReportMonthlyRow) -> ReportMonthlyRowDto {
    ReportMonthlyRowDto {
        month: row.month,
        income: row.income,
        expenses: row.expenses,
        income_current: row.income_current,
        expenses_current: row.expenses_current,
    }
}

fn report_category_to_dto(row: ReportCategoryRow) -> ReportCategoryRowDto {
    ReportCategoryRowDto {
        category: row.category,
        operations_count: row.operations_count,
        total_base: row.total_base,
        total_current: row.total_current,
    }
}

fn report_tag_to_dto(row: ReportTagRow) -> ReportTagRowDto {
    ReportTagRowDto {
        tag: row.tag,
        operations_count: row.operations_count,
        total_base: row.total_base,
        total_current: row.total_current,
    }
}

fn report_debt_to_dto(row: ReportDebtRow) -> ReportDebtRowDto {
    ReportDebtRowDto {
        contact_name: row.contact_name,
        kind: row.kind,
        status: row.status,
        created_at: row.created_at,
        closed_at: row.closed_at,
        currency: row.currency,
        total_amount: row.total_amount,
        remaining_amount: row.remaining_amount,
        settled_amount: row.settled_amount,
        progress_percent: row.progress_percent,
    }
}

fn is_supported_currency(value: &str) -> bool {
    matches!(
        value.to_ascii_uppercase().as_str(),
        "KZT" | "USD" | "EUR" | "RUB"
    )
}

fn record_to_dto(row: RecordRow) -> RecordDto {
    RecordDto {
        id: row.id,
        record_type: row.record_type,
        date: row.date,
        wallet_id: row.wallet_id,
        transfer_id: row.transfer_id,
        related_debt_id: row.related_debt_id,
        amount_original: format_money(row.amount_original),
        currency: row.currency,
        rate_at_operation: format_rate(row.rate_at_operation),
        amount_base: format_money(row.amount_base),
        category: row.category,
        description: row.description,
        tags: row.tags,
    }
}

fn wallet_to_dto(row: WalletRow) -> WalletDto {
    WalletDto {
        id: row.id,
        name: row.name,
        currency: row.currency,
        initial_balance: format_money(row.initial_balance),
        system: row.system,
        allow_negative: row.allow_negative,
        is_active: row.is_active,
    }
}

fn wallet_balance_to_dto(row: WalletBalanceRow) -> WalletBalanceDto {
    WalletBalanceDto {
        wallet_id: row.0,
        name: row.1,
        currency: row.2,
        balance: format_money(row.3 + row.4),
    }
}

fn operation_delete_to_dto(result: OperationDeleteResult) -> OperationDeleteResultDto {
    OperationDeleteResultDto {
        deleted_records: result.deleted_records,
        deleted_transfers: result.deleted_transfers,
        deleted_debt_linked_records: result.deleted_debt_linked_records,
        skipped_records: result.skipped_records,
    }
}

fn operation_import_to_dto(result: OperationImportResult) -> OperationImportResultDto {
    OperationImportResultDto {
        imported: result.imported,
        skipped: result.skipped,
        errors: result.errors,
        dry_run: result.dry_run,
        blocking_errors: result.blocking_errors,
    }
}

fn operation_export_to_dto(result: OperationExportResult) -> OperationExportResultDto {
    OperationExportResultDto {
        exported_rows: result.exported_rows,
        path: result.path,
    }
}

fn mandatory_import_to_dto(result: MandatoryImportResult) -> MandatoryImportResultDto {
    MandatoryImportResultDto {
        imported: result.imported,
        skipped: result.skipped,
        errors: result.errors,
        dry_run: result.dry_run,
        blocking_errors: result.blocking_errors,
    }
}

fn mandatory_export_to_dto(result: MandatoryExportResult) -> MandatoryExportResultDto {
    MandatoryExportResultDto {
        exported_rows: result.exported_rows,
        path: result.path,
    }
}

fn audit_finding_to_dto(row: AuditFindingRow) -> AuditFindingDto {
    AuditFindingDto {
        check: row.check,
        severity: row.severity,
        message: row.message,
        entity: row.detail,
    }
}

fn mandatory_template_to_dto(row: MandatoryExpenseRow) -> MandatoryTemplateDto {
    MandatoryTemplateDto {
        id: row.id,
        wallet_id: row.wallet_id,
        amount_original: format_money(row.amount_original),
        currency: row.currency,
        rate_at_operation: format_rate(row.rate_at_operation),
        amount_base: format_money(row.amount_base),
        category: row.category,
        description: row.description,
        period: row.period,
        date: row.date,
        auto_pay: row.auto_pay,
    }
}

fn mandatory_auto_pay_to_dto(result: MandatoryAutoPayResult) -> MandatoryAutoPayResultDto {
    MandatoryAutoPayResultDto {
        created_records: result
            .created_records
            .into_iter()
            .map(record_to_dto)
            .collect(),
    }
}

fn transfer_to_dto(row: TransferRow) -> TransferDto {
    TransferDto {
        id: row.id,
        from_wallet_id: row.from_wallet_id,
        to_wallet_id: row.to_wallet_id,
        date: row.date,
        amount_original: format_money(row.amount_original),
        currency: row.currency,
        rate_at_operation: format_rate(row.rate_at_operation),
        amount_base: format_money(row.amount_base),
        description: row.description,
    }
}

fn budget_to_dto(row: BudgetPayload) -> BudgetDto {
    BudgetDto {
        id: row.id,
        category: row.category,
        scope_type: row.scope_type,
        scope_value: row.scope_value,
        start_date: row.start_date,
        end_date: row.end_date,
        limit_base: format_money(row.limit_base),
        limit_base_minor: row.limit_base_minor,
        include_mandatory: row.include_mandatory,
    }
}

fn budget_result_to_dto(row: BudgetResultPayload) -> BudgetResultDto {
    BudgetResultDto {
        budget: budget_to_dto(row.budget),
        spent_base: format_money(row.spent_base),
        spent_minor: row.spent_minor,
        remaining_base: format_money(row.remaining_base),
        usage_pct: row.usage_pct,
        time_pct: row.time_pct,
        status: row.status,
        pace_status: row.pace_status,
        forecast_remaining_base: row.forecast_remaining_base.map(format_money),
        forecast_delta_base: row.forecast_delta_base.map(format_money),
        forecast_days_left: row.forecast_days_left,
        forecast_status_key: row.forecast_status_key,
        forecast_status_params: row.forecast_status_params,
    }
}

fn debt_to_dto(row: DebtPayload) -> DebtDto {
    DebtDto {
        id: row.id,
        contact_name: row.contact_name,
        kind: row.kind,
        total_amount: format_money_minor(row.total_amount_minor),
        remaining_amount: format_money_minor(row.remaining_amount_minor),
        currency: row.currency,
        interest_rate: format_rate(row.interest_rate),
        status: row.status,
        created_at: row.created_at,
        closed_at: row.closed_at,
    }
}

fn debt_payment_to_dto(row: DebtPaymentPayload) -> DebtPaymentDto {
    DebtPaymentDto {
        id: row.id,
        debt_id: row.debt_id,
        record_id: row.record_id,
        operation_type: row.operation_type,
        principal_paid: format_money_minor(row.principal_paid_minor),
        is_write_off: row.is_write_off,
        payment_date: row.payment_date,
    }
}

fn debt_payment_request_payload(request: RegisterDebtPaymentRequest) -> DebtPaymentRequestPayload {
    DebtPaymentRequestPayload {
        debt_id: request.debt_id,
        wallet_id: request.wallet_id,
        amount: request.amount,
        payment_date: request.payment_date,
        description: request.description,
    }
}

fn format_money(value: f64) -> String {
    format!("{value:.2}")
}

fn format_money_minor(value: i64) -> String {
    let sign = if value < 0 { "-" } else { "" };
    let abs = value.abs();
    format!("{sign}{}.{:02}", abs / 100, abs % 100)
}

fn format_rate(value: f64) -> String {
    format!("{value:.6}")
}

fn current_local_date_text() -> String {
    let (year, month, day) = current_local_date();
    format!("{year:04}-{month:02}-{day:02}")
}

fn storage_error(message: String) -> LedgeraEngineError {
    LedgeraEngineError::Storage { message }
}

fn validation_error(message: &str) -> LedgeraEngineError {
    LedgeraEngineError::Validation {
        message: message.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusqlite::Connection;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn fixture_db() -> String {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("ledgera_kotlin_ffi_{unique}.db"));
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
            CREATE TABLE records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                date TEXT NOT NULL,
                wallet_id INTEGER NOT NULL,
                transfer_id INTEGER,
                related_debt_id INTEGER DEFAULT NULL,
                amount_original REAL NOT NULL,
                amount_original_minor INTEGER DEFAULT NULL,
                currency TEXT NOT NULL,
                rate_at_operation REAL NOT NULL,
                rate_at_operation_text TEXT DEFAULT NULL,
                amount_base REAL NOT NULL,
                amount_base_minor INTEGER DEFAULT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                period TEXT,
                FOREIGN KEY(wallet_id) REFERENCES wallets(id)
            );
            CREATE TABLE transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            CREATE TABLE tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '',
                usage_count INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE record_tags (
                record_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY(record_id, tag_id)
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
            CREATE TABLE budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                limit_base REAL NOT NULL,
                limit_base_minor INTEGER NOT NULL,
                include_mandatory INTEGER NOT NULL DEFAULT 0,
                scope_type TEXT NOT NULL DEFAULT 'category',
                scope_value TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO wallets (id, name, currency, initial_balance, initial_balance_minor, is_active)
            VALUES (1, 'Main', 'KZT', 100.0, 10000, 1);
            INSERT INTO wallets (id, name, currency, initial_balance, initial_balance_minor, is_active)
            VALUES (2, 'Savings', 'KZT', 0.0, 0, 1);
            ",
        )
        .unwrap();
        path.to_string_lossy().to_string()
    }

    fn audit_fixture_db() -> String {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("ledgera_kotlin_ffi_audit_{unique}.db"));
        let conn = Connection::open(&path).unwrap();
        conn.execute_batch(
            "
            CREATE TABLE wallets (id INTEGER PRIMARY KEY, system INTEGER NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE transfers (
                id INTEGER PRIMARY KEY, from_wallet_id INTEGER, to_wallet_id INTEGER, date TEXT,
                amount_original REAL, currency TEXT, rate_at_operation REAL, amount_base REAL
            );
            CREATE TABLE records (
                id INTEGER PRIMARY KEY, type TEXT, date TEXT, wallet_id INTEGER, transfer_id INTEGER,
                related_debt_id INTEGER, amount_original REAL, currency TEXT,
                rate_at_operation REAL, amount_base REAL, category TEXT
            );
            CREATE TABLE mandatory_expenses (
                id INTEGER PRIMARY KEY, amount_original REAL, amount_base REAL, date TEXT, auto_pay INTEGER
            );
            CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT, usage_count INTEGER);
            CREATE TABLE record_tags (record_id INTEGER, tag_id INTEGER);
            CREATE TABLE debts (
                id INTEGER PRIMARY KEY, total_amount_minor INTEGER, remaining_amount_minor INTEGER, status TEXT
            );
            CREATE TABLE debt_payments (
                id INTEGER PRIMARY KEY, debt_id INTEGER, record_id INTEGER, operation_type TEXT,
                principal_paid_minor INTEGER, is_write_off INTEGER
            );
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY, name TEXT, category TEXT, currency TEXT, is_active INTEGER, created_at TEXT
            );
            CREATE TABLE asset_snapshots (
                id INTEGER PRIMARY KEY, asset_id INTEGER, snapshot_date TEXT, value_minor INTEGER, currency TEXT
            );
            CREATE TABLE goals (
                id INTEGER PRIMARY KEY, title TEXT, target_amount_minor INTEGER, currency TEXT,
                target_date TEXT, is_completed INTEGER, created_at TEXT
            );
            INSERT INTO wallets (id, system) VALUES (1, 1), (2, 0);
            INSERT INTO transfers VALUES (1, 1, 2, '2026-03-04', 100.0, 'KZT', 1.0, 100.0);
            INSERT INTO records VALUES
                (1, 'income', '2026-03-02', 1, NULL, NULL, 200.0, 'KZT', 1.0, 200.0, 'Salary'),
                (2, 'expense', '2026-03-03', 1, NULL, NULL, 50.0, 'KZT', 1.0, 50.0, 'Food'),
                (3, 'expense', '2026-03-04', 1, 1, NULL, 100.0, 'KZT', 1.0, 100.0, 'Transfer'),
                (4, 'income', '2026-03-04', 2, 1, NULL, 100.0, 'KZT', 1.0, 100.0, 'Transfer');
            INSERT INTO mandatory_expenses VALUES (1, 75.0, 75.0, NULL, 0);
            INSERT INTO assets VALUES (1, 'Broker', 'bank', 'KZT', 1, '2026-03-01');
            INSERT INTO asset_snapshots VALUES (1, 1, '2026-03-05', 150000, 'KZT');
            INSERT INTO goals VALUES (1, 'Emergency Fund', 500000, 'KZT', '2026-12-31', 0, '2026-03-02');
            ",
        )
        .unwrap();
        path.to_string_lossy().to_string()
    }

    #[test]
    fn engine_audit_run_returns_ok_findings_for_clean_fixture() {
        let db_path = audit_fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let findings = engine.audit_run().unwrap();

        assert_eq!(findings.len(), 15);
        assert!(findings.iter().all(|finding| finding.severity == "ok"));
        assert!(findings.iter().any(|finding| {
            finding.check == "transfer_pair_integrity"
                && finding.message == "All transfer pairs valid."
        }));
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_audit_run_maps_error_finding_fields() {
        let db_path = audit_fixture_db();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "INSERT INTO records VALUES (5, 'income', '2999-01-01', 1, NULL, NULL, 1.0, 'KZT', 1.0, 1.0, 'Future')",
            [],
        )
        .unwrap();
        let engine = LedgeraEngine::new(db_path.clone());

        let findings = engine.audit_run().unwrap();

        assert!(findings.iter().any(|finding| {
            finding.check == "date_validity"
                && finding.severity == "error"
                && finding.message == "Record id=5 has invalid date."
                && finding.entity == "2999-01-01: Date cannot be in the future"
        }));
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn current_local_date_text_uses_storage_local_date() {
        let (year, month, day) = current_local_date();

        assert_eq!(
            current_local_date_text(),
            format!("{year:04}-{month:02}-{day:02}")
        );
    }

    #[test]
    fn engine_creates_and_lists_standalone_record() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        assert_eq!(engine.wallet_balances().unwrap()[0].balance, "100.00");

        let created = engine
            .create_record(CreateRecordRequest {
                record_type: "income".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10.005".to_owned(),
                currency: "kzt".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10.005".to_owned(),
                category: "Salary".to_owned(),
                description: "Alpha".to_owned(),
                tags: vec!["Work".to_owned(), "123".to_owned()],
            })
            .unwrap();
        assert_eq!(created.amount_base, "10.01");
        assert_eq!(created.tags, vec!["work"]);

        let rows = engine
            .list_records(RecordFilterDto {
                start_date: None,
                end_date: None,
                wallet_id: Some(1),
                record_type: Some("income".to_owned()),
            })
            .unwrap();
        assert_eq!(rows, vec![created]);
        assert_eq!(engine.wallet_balance(1).unwrap().unwrap().balance, "110.01");
        assert!(engine.wallet_balance(3).unwrap().is_none());
        assert!(engine.wallet_balance(99).unwrap().is_none());
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_manages_budget_results() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let created = engine
            .create_budget(CreateBudgetRequest {
                category: " Food ".to_owned(),
                scope_type: "CATEGORY".to_owned(),
                scope_value: " Food ".to_owned(),
                start_date: "2026-01-01".to_owned(),
                end_date: "2026-01-31".to_owned(),
                limit_base: "50".to_owned(),
                include_mandatory: false,
            })
            .unwrap();
        assert_eq!(created.scope_type, "category");
        assert_eq!(created.scope_value, "Food");

        engine
            .create_record(CreateRecordRequest {
                record_type: "expense".to_owned(),
                date: "2026-01-02".to_owned(),
                wallet_id: 1,
                amount_original: "20".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "20".to_owned(),
                category: "Food".to_owned(),
                description: "Lunch".to_owned(),
                tags: Vec::new(),
            })
            .unwrap();
        let results = engine
            .list_budget_results(Some("2026-01-05".to_owned()))
            .unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].spent_base, "20.00");
        assert_eq!(results[0].status, "active");
        assert_eq!(results[0].pace_status, "overpace");

        let updated = engine
            .update_budget_limit(created.id, "100".to_owned())
            .unwrap();
        assert_eq!(updated.limit_base, "100.00");
        assert!(engine.delete_budget(created.id).unwrap());
        assert!(engine.list_budgets().unwrap().is_empty());
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_updates_and_deletes_standalone_record() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let created = engine
            .create_record(CreateRecordRequest {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "25".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "25".to_owned(),
                category: "Food".to_owned(),
                description: "Lunch".to_owned(),
                tags: vec!["food".to_owned()],
            })
            .unwrap();

        let updated = engine
            .update_record(
                created.id,
                UpdateRecordRequest {
                    record_type: "income".to_owned(),
                    date: "2026-01-02".to_owned(),
                    wallet_id: 1,
                    amount_original: "30.125".to_owned(),
                    currency: "kzt".to_owned(),
                    rate_at_operation: "1".to_owned(),
                    amount_base: "30.125".to_owned(),
                    category: "Bonus".to_owned(),
                    description: "Updated".to_owned(),
                    tags: vec!["Work".to_owned(), "food".to_owned()],
                },
            )
            .unwrap();
        assert_eq!(updated.amount_base, "30.13");
        assert_eq!(updated.category, "Bonus");
        assert_eq!(updated.tags, vec!["food", "work"]);
        assert_eq!(engine.get_record(created.id).unwrap(), Some(updated));
        assert_eq!(engine.list_tags().unwrap(), vec!["food", "work"]);
        assert_eq!(
            engine.list_categories("income".to_owned()).unwrap(),
            vec!["Bonus"]
        );
        assert_eq!(
            engine.list_record_descriptions(None).unwrap(),
            vec!["Updated"]
        );
        assert_eq!(
            engine
                .list_record_descriptions(Some("income".to_owned()))
                .unwrap(),
            vec!["Updated"]
        );
        assert!(
            engine
                .list_record_descriptions(Some("transfer".to_owned()))
                .is_err()
        );
        let suggestions = engine.operation_suggestions().unwrap();
        assert_eq!(suggestions.tags, vec!["food", "work"]);
        assert_eq!(suggestions.income_categories, vec!["Bonus"]);
        assert_eq!(suggestions.descriptions, vec!["Updated"]);
        assert_eq!(suggestions.income_descriptions, vec!["Updated"]);
        assert!(suggestions.expense_categories.is_empty());
        assert!(suggestions.expense_descriptions.is_empty());

        assert!(engine.delete_record(created.id).unwrap());
        assert_eq!(engine.get_record(created.id).unwrap(), None);
        assert!(
            engine
                .list_records(RecordFilterDto::default())
                .unwrap()
                .is_empty()
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_maps_tag_palette_and_assignments() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let created = engine
            .create_record_with_tag_colors(
                CreateRecordRequest {
                    record_type: "expense".to_owned(),
                    date: "2026-01-01".to_owned(),
                    wallet_id: 1,
                    amount_original: "10".to_owned(),
                    currency: "KZT".to_owned(),
                    rate_at_operation: "1".to_owned(),
                    amount_base: "10".to_owned(),
                    category: "Food".to_owned(),
                    description: "Colored".to_owned(),
                    tags: vec!["colored".to_owned()],
                },
                vec![TagColorAssignment {
                    name: "colored".to_owned(),
                    color: "#ea3b5a".to_owned(),
                }],
            )
            .unwrap();
        assert_eq!(created.tags, vec!["colored"]);
        assert_eq!(engine.tag_color_palette().len(), 32);
        assert_eq!(
            engine
                .list_tag_colors()
                .unwrap()
                .into_iter()
                .find(|tag| tag.name == "colored")
                .unwrap()
                .color,
            "#ea3b5a"
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_rejects_invalid_record_dates() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let create_error = engine
            .create_record(CreateRecordRequest {
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
            })
            .unwrap_err();
        assert!(
            create_error
                .to_string()
                .contains("Date month must be between 01 and 12")
        );

        let created = engine
            .create_record(CreateRecordRequest {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            })
            .unwrap();
        let update_error = engine
            .update_record(
                created.id,
                UpdateRecordRequest {
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
        assert!(
            update_error
                .to_string()
                .contains("Date day must be between 01 and 28")
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_rejects_future_record_dates() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let create_error = engine
            .create_record(CreateRecordRequest {
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
            })
            .unwrap_err();
        assert!(
            create_error
                .to_string()
                .contains("Date cannot be in the future")
        );

        let created = engine
            .create_record(CreateRecordRequest {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            })
            .unwrap();
        let update_error = engine
            .update_record(
                created.id,
                UpdateRecordRequest {
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
        assert!(
            update_error
                .to_string()
                .contains("Date cannot be in the future")
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_rejects_invalid_currency_codes() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let create_error = engine
            .create_record(CreateRecordRequest {
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
            })
            .unwrap_err();
        assert!(
            create_error
                .to_string()
                .contains("Currency code must contain 3 letters")
        );

        let created = engine
            .create_record(CreateRecordRequest {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            })
            .unwrap();
        let update_error = engine
            .update_record(
                created.id,
                UpdateRecordRequest {
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
        assert!(
            update_error
                .to_string()
                .contains("Currency code must contain 3 letters")
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_creates_base_currency_transfer() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let result = engine
            .create_transfer(CreateTransferRequest {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-01-01".to_owned(),
                amount: "20".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            })
            .unwrap();

        assert_eq!(result.transfer_id, 1);
        assert_eq!(engine.wallet_balance(1).unwrap().unwrap().balance, "80.00");
        let records = engine.list_records(RecordFilterDto::default()).unwrap();
        assert_eq!(records.len(), 2);
        assert!(records.iter().any(|record| {
            record.record_type == "expense" && record.transfer_id == Some(result.transfer_id)
        }));
        assert!(records.iter().any(|record| {
            record.record_type == "income" && record.transfer_id == Some(result.transfer_id)
        }));
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_gets_and_updates_transfer() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let result = engine
            .create_transfer(CreateTransferRequest {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-01-01".to_owned(),
                amount: "20".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            })
            .unwrap();

        let transfer = engine.get_transfer(result.transfer_id).unwrap().unwrap();
        assert_eq!(transfer.from_wallet_id, 1);
        assert_eq!(transfer.to_wallet_id, 2);
        assert_eq!(transfer.amount_original, "20.00");

        let updated = engine
            .update_transfer(
                result.transfer_id,
                UpdateTransferRequest {
                    from_wallet_id: 1,
                    to_wallet_id: 2,
                    date: "2026-01-02".to_owned(),
                    amount: "5.25".to_owned(),
                    currency: "KZT".to_owned(),
                    description: "Return".to_owned(),
                },
            )
            .unwrap();
        assert_eq!(updated.transfer_id, result.transfer_id);

        let transfer = engine.get_transfer(result.transfer_id).unwrap().unwrap();
        assert_eq!(transfer.from_wallet_id, 1);
        assert_eq!(transfer.to_wallet_id, 2);
        assert_eq!(transfer.amount_original, "5.25");
        assert_eq!(transfer.description, "Return");
        let records = engine.list_records(RecordFilterDto::default()).unwrap();
        assert!(records.iter().any(|record| {
            record.record_type == "expense"
                && record.transfer_id == Some(result.transfer_id)
                && record.wallet_id == 1
        }));
        assert!(records.iter().any(|record| {
            record.record_type == "income"
                && record.transfer_id == Some(result.transfer_id)
                && record.wallet_id == 2
        }));

        let error = engine
            .update_transfer(
                result.transfer_id,
                UpdateTransferRequest {
                    from_wallet_id: 1,
                    to_wallet_id: 1,
                    date: "2026-01-02".to_owned(),
                    amount: "5.25".to_owned(),
                    currency: "KZT".to_owned(),
                    description: "Invalid".to_owned(),
                },
            )
            .unwrap_err();
        assert!(error.to_string().contains("must be different"));
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_deletes_transfer() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let result = engine
            .create_transfer(CreateTransferRequest {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-01-01".to_owned(),
                amount: "20".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            })
            .unwrap();

        assert!(engine.delete_transfer(result.transfer_id).unwrap());
        assert!(engine.get_transfer(result.transfer_id).unwrap().is_none());
        assert!(
            engine
                .list_records(RecordFilterDto::default())
                .unwrap()
                .iter()
                .all(|record| record.transfer_id != Some(result.transfer_id))
        );

        let error = engine.delete_transfer(result.transfer_id).unwrap_err();
        assert!(error.to_string().contains("Transfer not found"));
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_bulk_deletes_operations() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let record = engine
            .create_record(CreateRecordRequest {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "Lunch".to_owned(),
                tags: vec!["food".to_owned()],
            })
            .unwrap();
        let transfer = engine
            .create_transfer(CreateTransferRequest {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-01-02".to_owned(),
                amount: "20".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            })
            .unwrap();

        let selected = engine
            .delete_operations_selection(vec![record.id], vec![transfer.transfer_id])
            .unwrap();

        assert_eq!(
            selected,
            OperationDeleteResultDto {
                deleted_records: 1,
                deleted_transfers: 1,
                deleted_debt_linked_records: 0,
                skipped_records: 0,
            }
        );
        assert!(
            engine
                .list_records(RecordFilterDto::default())
                .unwrap()
                .is_empty()
        );

        engine
            .create_record(CreateRecordRequest {
                record_type: "income".to_owned(),
                date: "2026-01-03".to_owned(),
                wallet_id: 1,
                amount_original: "5".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "5".to_owned(),
                category: "Bonus".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            })
            .unwrap();
        let all = engine.delete_all_operations().unwrap();
        assert_eq!(
            all,
            OperationDeleteResultDto {
                deleted_records: 1,
                deleted_transfers: 0,
                deleted_debt_linked_records: 0,
                skipped_records: 0,
            }
        );
        assert!(
            engine
                .list_records(RecordFilterDto::default())
                .unwrap()
                .is_empty()
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_imports_and_exports_operations_csv() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let import_path = std::env::temp_dir().join(format!(
            "ledgera_kotlin_ffi_import_{}.csv",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let export_path = std::env::temp_dir().join(format!(
            "ledgera_kotlin_ffi_export_{}.csv",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::write(
            &import_path,
            "date,type,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,tags,period,transfer_id,from_wallet_id,to_wallet_id\n\
             2026-01-01,income,1,Salary,10.00,KZT,1,10.00,Pay,work,,,,,\n\
             2026-01-02,transfer,,Transfer,5.00,KZT,1,5.00,Move,,,1,1,2\n",
        )
        .unwrap();

        let preview = engine
            .preview_import_records_csv(import_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(preview.imported, 2);
        assert!(preview.dry_run);

        let imported = engine
            .import_records_csv(import_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(imported.imported, 2);
        assert!(!imported.dry_run);

        let exported = engine
            .export_records_csv(export_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(exported.exported_rows, 2);
        let csv = fs::read_to_string(&export_path).unwrap();
        assert!(csv.contains(",transfer,"));
        assert!(csv.contains("Salary"));

        fs::remove_file(import_path).ok();
        fs::remove_file(export_path).ok();
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_imports_and_exports_operations_xlsx() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let import_path = std::env::temp_dir().join(format!(
            "ledgera_kotlin_ffi_import_{}.xlsx",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let export_path = std::env::temp_dir().join(format!(
            "ledgera_kotlin_ffi_export_{}.xlsx",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        engine
            .create_record(CreateRecordRequest {
                record_type: "income".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10.00".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10.00".to_owned(),
                category: "Salary".to_owned(),
                description: "Pay".to_owned(),
                tags: vec!["work".to_owned()],
            })
            .unwrap();
        engine
            .create_transfer(CreateTransferRequest {
                from_wallet_id: 1,
                to_wallet_id: 2,
                date: "2026-01-02".to_owned(),
                amount: "5.00".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            })
            .unwrap();
        export_records_xlsx(&db_path, import_path.to_str().unwrap()).unwrap();

        let preview = engine
            .preview_import_records_xlsx(import_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(preview.imported, 2);
        assert!(preview.dry_run);

        let imported = engine
            .import_records_xlsx(import_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(imported.imported, 2);
        assert!(!imported.dry_run);

        let exported = engine
            .export_records_xlsx(export_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(exported.exported_rows, 2);
        assert!(export_path.exists());

        fs::remove_file(import_path).ok();
        fs::remove_file(export_path).ok();
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_creates_wallet() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let wallet = engine
            .create_wallet(CreateWalletRequest {
                name: "Emergency".to_owned(),
                currency: "kzt".to_owned(),
                initial_balance: "12.345".to_owned(),
                allow_negative: true,
            })
            .unwrap();

        assert_eq!(wallet.id, 3);
        assert_eq!(wallet.name, "Emergency");
        assert_eq!(wallet.currency, "KZT");
        assert_eq!(wallet.initial_balance, "12.35");
        assert!(!wallet.system);
        assert!(wallet.allow_negative);
        assert!(wallet.is_active);
        assert_eq!(engine.list_wallets().unwrap().len(), 3);
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_creates_and_lists_debts() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let debt = engine
            .create_debt(CreateDebtRequest {
                kind: "debt".to_owned(),
                contact_name: "Alice".to_owned(),
                wallet_id: 1,
                amount: "25.50".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            })
            .expect("create debt");
        assert_eq!(debt.id, 1);
        assert_eq!(debt.contact_name, "Alice");
        assert_eq!(debt.kind, "debt");
        assert_eq!(debt.total_amount, "25.50");
        assert_eq!(debt.remaining_amount, "25.50");
        assert_eq!(debt.status, "open");

        let debts = engine.list_debts().expect("list debts");
        assert_eq!(debts, vec![debt.clone()]);
        let records = engine.list_records(RecordFilterDto::default()).unwrap();
        let linked_record = records
            .iter()
            .find(|record| record.related_debt_id == Some(debt.id))
            .expect("debt-linked record is visible to Operations");
        assert_eq!(linked_record.record_type, "income");
        assert_eq!(linked_record.category, "Debt");
        let linked_record_id = linked_record.id;
        let conn = Connection::open(&db_path).expect("open");
        let linked_type: String = conn
            .query_row(
                "SELECT type FROM records WHERE related_debt_id = ?1",
                [debt.id],
                |row| row.get(0),
            )
            .expect("linked debt record");
        assert_eq!(linked_type, "income");
        drop(conn);

        assert!(
            engine
                .delete_record(linked_record_id)
                .expect("delete debt-linked record")
        );
        assert!(engine.get_record(linked_record_id).unwrap().is_none());
        assert!(
            engine
                .list_debt_payments(debt.id)
                .expect("list debt payments")
                .is_empty()
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_creates_loan_and_rejects_invalid_debt_requests() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let loan = engine
            .create_debt(CreateDebtRequest {
                kind: "loan".to_owned(),
                contact_name: "Bob".to_owned(),
                wallet_id: 1,
                amount: "10.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "Loan to Bob".to_owned(),
            })
            .expect("create loan");
        assert_eq!(loan.kind, "loan");
        let conn = Connection::open(&db_path).expect("open");
        let linked_type: String = conn
            .query_row(
                "SELECT type FROM records WHERE related_debt_id = ?1",
                [loan.id],
                |row| row.get(0),
            )
            .expect("linked loan record");
        assert_eq!(linked_type, "expense");
        drop(conn);

        let error = engine
            .create_debt(CreateDebtRequest {
                kind: "loan".to_owned(),
                contact_name: "Too much".to_owned(),
                wallet_id: 1,
                amount: "999.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            })
            .expect_err("insufficient funds");
        assert!(error.to_string().contains("Insufficient funds"));

        let error = engine
            .create_debt(CreateDebtRequest {
                kind: "debt".to_owned(),
                contact_name: "USD".to_owned(),
                wallet_id: 1,
                amount: "1.00".to_owned(),
                currency: "USD".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            })
            .expect_err("non-base currency");
        assert!(error.to_string().contains("base-currency"));
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_registers_debt_actions() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let debt = engine
            .create_debt(CreateDebtRequest {
                kind: "debt".to_owned(),
                contact_name: "Alice".to_owned(),
                wallet_id: 1,
                amount: "50.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            })
            .expect("create debt");

        let payment = engine
            .register_debt_payment(RegisterDebtPaymentRequest {
                debt_id: debt.id,
                wallet_id: Some(1),
                amount: "20.00".to_owned(),
                payment_date: "2026-03-05".to_owned(),
                description: "cash".to_owned(),
            })
            .expect("payment");
        assert_eq!(payment.debt_id, debt.id);
        assert_eq!(payment.operation_type, "debt_repay");
        assert_eq!(payment.principal_paid, "20.00");
        assert!(payment.record_id.is_some());
        assert!(
            engine
                .register_debt_payment(RegisterDebtPaymentRequest {
                    debt_id: debt.id,
                    wallet_id: Some(1),
                    amount: "40.00".to_owned(),
                    payment_date: "2026-03-06".to_owned(),
                    description: "too much".to_owned(),
                })
                .expect_err("overpayment")
                .to_string()
                .contains("exceeds")
        );

        let write_off = engine
            .register_debt_write_off(RegisterDebtPaymentRequest {
                debt_id: debt.id,
                wallet_id: None,
                amount: "30.00".to_owned(),
                payment_date: "2026-03-06".to_owned(),
                description: "".to_owned(),
            })
            .expect("write off");
        assert_eq!(write_off.operation_type, "debt_forgive");
        assert!(write_off.is_write_off);
        assert!(write_off.record_id.is_none());
        let updated = engine.list_debts().expect("debts").remove(0);
        assert_eq!(updated.status, "closed");
        assert_eq!(updated.closed_at.as_deref(), Some("2026-03-06"));

        let loan = engine
            .create_debt(CreateDebtRequest {
                kind: "loan".to_owned(),
                contact_name: "Bob".to_owned(),
                wallet_id: 1,
                amount: "10.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            })
            .expect("create loan");
        let closed_loan = engine
            .close_debt(RegisterDebtPaymentRequest {
                debt_id: loan.id,
                wallet_id: Some(1),
                amount: "0.01".to_owned(),
                payment_date: "2026-03-07".to_owned(),
                description: "close".to_owned(),
            })
            .expect("close loan");
        assert_eq!(closed_loan.status, "closed");
        assert_eq!(
            engine
                .list_debt_payments(loan.id)
                .expect("loan history")
                .first()
                .expect("loan payment")
                .operation_type,
            "loan_collect"
        );

        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_deletes_debt_and_debt_payments() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let debt = engine
            .create_debt(CreateDebtRequest {
                kind: "debt".to_owned(),
                contact_name: "Alice".to_owned(),
                wallet_id: 1,
                amount: "50.00".to_owned(),
                currency: "KZT".to_owned(),
                created_at: "2026-03-01".to_owned(),
                description: "".to_owned(),
            })
            .expect("create debt");
        let payment = engine
            .register_debt_payment(RegisterDebtPaymentRequest {
                debt_id: debt.id,
                wallet_id: Some(1),
                amount: "20.00".to_owned(),
                payment_date: "2026-03-05".to_owned(),
                description: "cash".to_owned(),
            })
            .expect("payment");
        let record_id = payment.record_id.expect("linked payment record");

        let reopened = engine
            .delete_debt_payment(payment.id, true)
            .expect("delete payment");
        assert_eq!(reopened.id, debt.id);
        assert_eq!(reopened.status, "open");
        assert_eq!(reopened.remaining_amount, "50.00");
        let conn = Connection::open(&db_path).expect("open");
        let linked_record_count: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM records WHERE id = ?",
                [record_id],
                |row| row.get(0),
            )
            .expect("record count");
        assert_eq!(linked_record_count, 0);
        drop(conn);

        assert!(engine.delete_debt(debt.id).expect("delete debt"));
        assert!(engine.list_debts().expect("debts").is_empty());
        let conn = Connection::open(&db_path).expect("open");
        let preserved_records: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM records WHERE related_debt_id IS NULL",
                [],
                |row| row.get(0),
            )
            .expect("preserved records");
        assert!(preserved_records > 0);
        let missing = engine
            .delete_debt(999)
            .expect_err("missing debt should fail");
        assert!(missing.to_string().contains("Debt not found: 999"));

        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_lists_debt_payment_history() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let conn = Connection::open(&db_path).expect("open");
        conn.execute(
            "INSERT INTO debts (
                id, contact_name, kind, total_amount_minor, remaining_amount_minor,
                currency, interest_rate, status, created_at, closed_at
             ) VALUES (1, 'Alice', 'debt', 5000, 3000, 'KZT', 0, 'open', '2026-03-01', NULL)",
            [],
        )
        .expect("debt");
        conn.execute(
            "INSERT INTO debt_payments (
                id, debt_id, record_id, operation_type, principal_paid_minor, is_write_off, payment_date
             ) VALUES (1, 1, NULL, 'debt_repay', 2000, 0, '2026-03-05')",
            [],
        )
        .expect("payment");
        drop(conn);

        let payments = engine.list_debt_payments(1).expect("payments");
        assert_eq!(payments.len(), 1);
        assert_eq!(payments[0].debt_id, 1);
        assert_eq!(payments[0].principal_paid, "20.00");
        assert_eq!(payments[0].operation_type, "debt_repay");
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_manages_mandatory_templates_and_records() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let created = engine
            .create_mandatory_template(CreateMandatoryTemplateRequest {
                wallet_id: 1,
                amount_original: "25.25".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "25.25".to_owned(),
                category: "Rent".to_owned(),
                description: "Monthly rent".to_owned(),
                period: "monthly".to_owned(),
                date: "2026-02-01".to_owned(),
            })
            .unwrap();
        assert_eq!(created.id, 1);
        assert!(created.auto_pay);
        assert_eq!(engine.list_mandatory_templates().unwrap().len(), 1);

        let updated = engine
            .update_mandatory_template(
                created.id,
                UpdateMandatoryTemplateRequest {
                    wallet_id: 1,
                    amount_base: "20".to_owned(),
                    period: "weekly".to_owned(),
                    date: "".to_owned(),
                },
            )
            .unwrap();
        assert_eq!(updated.wallet_id, 1);
        assert_eq!(updated.period, "weekly");
        assert!(!updated.auto_pay);

        let record = engine
            .add_mandatory_to_records(AddMandatoryToRecordsRequest {
                template_id: updated.id,
                date: "2026-02-03".to_owned(),
                wallet_id: 1,
            })
            .unwrap();
        assert_eq!(record.record_type, "mandatory_expense");
        assert_eq!(record.category, "Rent");

        assert!(engine.delete_mandatory_template(updated.id).unwrap());
        assert!(engine.list_mandatory_templates().unwrap().is_empty());
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_imports_and_exports_mandatory_templates() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let import_path = std::env::temp_dir().join(format!("ledgera_mandatory_{unique}.csv"));
        let export_path = std::env::temp_dir().join(format!("ledgera_mandatory_{unique}.xlsx"));
        fs::write(
            &import_path,
            "type,date,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,period\n\
mandatory_expense,2026-03-01,1,Rent,100,KZT,1,100,Rent,monthly\n\
mandatory_expense,,2,Phone,25,KZT,1,25,Mobile,weekly\n",
        )
        .unwrap();

        let preview = engine
            .preview_import_mandatory_csv(import_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(preview.imported, 2);
        assert!(preview.dry_run);
        assert!(preview.errors.is_empty());

        let imported = engine
            .import_mandatory_csv(import_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(imported.imported, 2);
        assert_eq!(engine.list_mandatory_templates().unwrap().len(), 2);

        let export = engine
            .export_mandatory_xlsx(export_path.to_string_lossy().to_string())
            .unwrap();
        assert_eq!(export.exported_rows, 2);
        assert_eq!(export.path, export_path.to_string_lossy());

        fs::write(
            &import_path,
            "type,date,wallet_id,category,amount_original,currency,rate_at_operation,amount_base,description,period\n\
expense,,1,Wrong,10,KZT,1,10,Wrong,monthly\n",
        )
        .unwrap();
        let invalid_preview = engine
            .preview_import_mandatory_csv(import_path.to_string_lossy().to_string())
            .unwrap();
        assert!(invalid_preview.blocking_errors);
        assert!(
            engine
                .import_mandatory_csv(import_path.to_string_lossy().to_string())
                .unwrap_err()
                .to_string()
                .contains("Mandatory import contains validation errors")
        );

        fs::remove_file(import_path).ok();
        fs::remove_file(export_path).ok();
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_applies_mandatory_auto_payments() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        engine
            .create_mandatory_template(CreateMandatoryTemplateRequest {
                wallet_id: 1,
                amount_original: "5".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "5".to_owned(),
                category: "Daily".to_owned(),
                description: "Coffee".to_owned(),
                period: "daily".to_owned(),
                date: "2026-02-01".to_owned(),
            })
            .unwrap();

        let result = engine
            .apply_mandatory_auto_payments("2026-02-05".to_owned())
            .unwrap();
        assert_eq!(result.created_records.len(), 1);
        assert_eq!(result.created_records[0].date, "2026-02-05");
        assert_eq!(result.created_records[0].record_type, "mandatory_expense");

        let duplicate = engine
            .apply_mandatory_auto_payments("2026-02-05".to_owned())
            .unwrap();
        assert!(duplicate.created_records.is_empty());
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_rejects_duplicate_wallet_names() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        engine
            .create_wallet(CreateWalletRequest {
                name: "Emergency".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            })
            .unwrap();
        let error = engine
            .create_wallet(CreateWalletRequest {
                name: " emergency ".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            })
            .unwrap_err();

        assert!(matches!(error, LedgeraEngineError::Storage { .. }));
        assert!(
            error
                .to_string()
                .contains("Wallet name already exists: emergency")
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_marks_first_created_wallet_as_system() {
        let db_path = fixture_db();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute("DELETE FROM wallets", []).unwrap();
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'wallets'", [])
            .unwrap();
        drop(conn);
        let engine = LedgeraEngine::new(db_path.clone());

        let first = engine
            .create_wallet(CreateWalletRequest {
                name: "Main".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            })
            .unwrap();
        let second = engine
            .create_wallet(CreateWalletRequest {
                name: "Savings".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            })
            .unwrap();

        assert_eq!(first.id, 1);
        assert!(first.system);
        assert_eq!(second.id, 2);
        assert!(!second.system);
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_deletes_wallet_with_hard_and_soft_actions() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        let empty_wallet = engine
            .create_wallet(CreateWalletRequest {
                name: "Empty".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            })
            .unwrap();
        let result = engine.delete_wallet(empty_wallet.id).unwrap();
        assert_eq!(result.wallet_id, empty_wallet.id);
        assert_eq!(result.action, "hard_deleted");
        assert!(
            engine
                .list_wallets()
                .unwrap()
                .iter()
                .all(|wallet| wallet.id != empty_wallet.id)
        );
        let replacement = engine
            .create_wallet(CreateWalletRequest {
                name: "Replacement".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            })
            .unwrap();
        assert_eq!(replacement.id, empty_wallet.id);
        assert!(engine.delete_wallet(replacement.id).is_ok());

        let archived_wallet = engine
            .create_wallet(CreateWalletRequest {
                name: "Archive".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            })
            .unwrap();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "INSERT INTO records (type, date, wallet_id, amount_original, amount_original_minor, currency, rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor, category, description)
             VALUES ('income', '2026-01-01', ?1, 1.0, 100, 'KZT', 1.0, '1.000000', 1.0, 100, 'Test', 'In')",
            [archived_wallet.id],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (type, date, wallet_id, amount_original, amount_original_minor, currency, rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor, category, description)
             VALUES ('expense', '2026-01-01', ?1, 1.0, 100, 'KZT', 1.0, '1.000000', 1.0, 100, 'Test', 'Out')",
            [archived_wallet.id],
        )
        .unwrap();
        drop(conn);

        let result = engine.delete_wallet(archived_wallet.id).unwrap();
        assert_eq!(result.action, "soft_deleted");
        assert!(
            !engine
                .list_wallets()
                .unwrap()
                .into_iter()
                .find(|wallet| wallet.id == archived_wallet.id)
                .unwrap()
                .is_active
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_surfaces_wallet_storage_errors() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let error = engine
            .create_wallet(CreateWalletRequest {
                name: " ".to_owned(),
                currency: "KZT".to_owned(),
                initial_balance: "0".to_owned(),
                allow_negative: false,
            })
            .unwrap_err();

        assert!(error.to_string().contains("Wallet name is required"));
        let conn = Connection::open(&db_path).unwrap();
        conn.execute("UPDATE wallets SET system = 1 WHERE id = 1", [])
            .unwrap();
        drop(conn);
        let error = engine.delete_wallet(1).unwrap_err();
        assert!(
            error
                .to_string()
                .contains("System wallet cannot be deleted")
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_surfaces_transfer_storage_errors() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let error = engine
            .create_transfer(CreateTransferRequest {
                from_wallet_id: 1,
                to_wallet_id: 1,
                date: "2026-01-01".to_owned(),
                amount: "20".to_owned(),
                currency: "KZT".to_owned(),
                description: "Move".to_owned(),
                commission_amount: "0".to_owned(),
                commission_currency: "KZT".to_owned(),
            })
            .unwrap_err();

        assert!(error.to_string().contains("must be different"));
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_rejects_unsupported_currency_codes() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());

        let create_error = engine
            .create_record(CreateRecordRequest {
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
            })
            .unwrap_err();
        assert!(create_error.to_string().contains("Unsupported currency"));

        let created = engine
            .create_record(CreateRecordRequest {
                record_type: "expense".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Food".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            })
            .unwrap();
        let update_error = engine
            .update_record(
                created.id,
                UpdateRecordRequest {
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
        assert!(update_error.to_string().contains("Unsupported currency"));
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_rejects_non_base_currency_records() {
        let db_path = fixture_db();
        let engine = LedgeraEngine::new(db_path.clone());
        assert_eq!(engine.base_currency().unwrap(), "KZT");

        let create_error = engine
            .create_record(CreateRecordRequest {
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
            })
            .unwrap_err();
        assert!(
            create_error
                .to_string()
                .contains("base-currency records only (KZT)")
        );

        let created = engine
            .create_record(CreateRecordRequest {
                record_type: "income".to_owned(),
                date: "2026-01-01".to_owned(),
                wallet_id: 1,
                amount_original: "10".to_owned(),
                currency: "KZT".to_owned(),
                rate_at_operation: "1".to_owned(),
                amount_base: "10".to_owned(),
                category: "Salary".to_owned(),
                description: "".to_owned(),
                tags: vec![],
            })
            .unwrap();
        let update_error = engine
            .update_record(
                created.id,
                UpdateRecordRequest {
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
        assert!(
            update_error
                .to_string()
                .contains("base-currency records only (KZT)")
        );
        fs::remove_file(db_path).ok();
    }

    #[test]
    fn engine_rejects_linked_record_update_and_delete() {
        let db_path = fixture_db();
        let conn = Connection::open(&db_path).unwrap();
        conn.execute(
            "INSERT INTO transfers (
                id, from_wallet_id, to_wallet_id, date, amount_original, amount_original_minor,
                currency, rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor, description
             ) VALUES (1, 1, 1, '2026-01-01', 10.0, 1000, 'KZT', 1.0, '1.000000', 10.0, 1000, '')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO records (
                id, type, date, wallet_id, transfer_id, amount_original, amount_original_minor,
                currency, rate_at_operation, rate_at_operation_text, amount_base, amount_base_minor,
                category, description
             ) VALUES (1, 'expense', '2026-01-01', 1, 1, 10.0, 1000, 'KZT', 1.0, '1.000000', 10.0, 1000, 'Transfer', '')",
            [],
        )
        .unwrap();
        let engine = LedgeraEngine::new(db_path.clone());
        let request = UpdateRecordRequest {
            record_type: "expense".to_owned(),
            date: "2026-01-01".to_owned(),
            wallet_id: 1,
            amount_original: "10".to_owned(),
            currency: "KZT".to_owned(),
            rate_at_operation: "1".to_owned(),
            amount_base: "10".to_owned(),
            category: "Transfer".to_owned(),
            description: "".to_owned(),
            tags: vec![],
        };

        assert!(engine.update_record(1, request).is_err());
        assert!(engine.delete_record(1).is_err());
        assert!(engine.get_record(1).is_err());
        fs::remove_file(db_path).ok();
    }
}
