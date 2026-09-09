package app.ledgera.model

data class OperationRecord(
    val id: Long,
    val type: String,
    val date: String,
    val walletId: Long,
    val transferId: Long? = null,
    val relatedDebtId: Long? = null,
    val amountOriginal: String,
    val currency: String,
    val rateAtOperation: String,
    val amountBase: String,
    val category: String,
    val description: String,
    val tags: List<String>,
)

data class OperationDraft(
    val id: Long? = null,
    val type: String = "expense",
    val date: String = "",
    val walletId: Long = 0,
    val amountOriginal: String = "",
    val currency: String = "KZT",
    val rateAtOperation: String = "1",
    val amountBase: String = "",
    val category: String = "",
    val description: String = "",
    val tagsText: String = "",
    val tagColors: Map<String, String> = emptyMap(),
)

data class OperationFilter(
    val startDate: String? = null,
    val endDate: String? = null,
    val walletId: Long? = null,
    val recordType: String? = null,
)

data class CreateOperationRequest(
    val type: String,
    val date: String,
    val walletId: Long,
    val amountOriginal: String,
    val currency: String,
    val rateAtOperation: String,
    val amountBase: String,
    val category: String,
    val description: String,
    val tags: List<String> = emptyList(),
    val tagColors: Map<String, String> = emptyMap(),
)

data class UpdateOperationRequest(
    val type: String,
    val date: String,
    val walletId: Long,
    val transferId: Long? = null,
    val relatedDebtId: Long? = null,
    val amountOriginal: String,
    val currency: String,
    val rateAtOperation: String,
    val amountBase: String,
    val category: String,
    val description: String,
    val tags: List<String> = emptyList(),
    val tagColors: Map<String, String> = emptyMap(),
)

data class CreateTransferRequest(
    val fromWalletId: Long,
    val toWalletId: Long,
    val date: String,
    val amount: String,
    val currency: String,
    val description: String,
    val commissionAmount: String = "0",
    val commissionCurrency: String = "",
)

data class CreateTransferResult(
    val transferId: Long,
)

data class TransferDetails(
    val id: Long,
    val fromWalletId: Long,
    val toWalletId: Long,
    val date: String,
    val amountOriginal: String,
    val currency: String,
    val rateAtOperation: String,
    val amountBase: String,
    val description: String,
)

data class TransferDraft(
    val id: Long,
    val fromWalletId: Long = 0,
    val toWalletId: Long = 0,
    val date: String = "",
    val amount: String = "",
    val currency: String = "KZT",
    val description: String = "",
)

data class UpdateTransferRequest(
    val fromWalletId: Long,
    val toWalletId: Long,
    val date: String,
    val amount: String,
    val currency: String,
    val description: String,
)

data class UpdateTransferResult(
    val transferId: Long,
)

data class OperationDeleteResult(
    val deletedRecords: Long,
    val deletedTransfers: Long,
    val deletedDebtLinkedRecords: Long,
    val skippedRecords: Long,
)

data class OperationImportResult(
    val imported: Long,
    val skipped: Long,
    val errors: List<String>,
    val dryRun: Boolean,
    val blockingErrors: Boolean = false,
)

data class OperationExportResult(
    val exportedRows: Long,
    val path: String,
)

data class OperationSuggestions(
    val tags: List<String> = emptyList(),
    val incomeCategories: List<String> = emptyList(),
    val expenseCategories: List<String> = emptyList(),
    val descriptions: List<String> = emptyList(),
    val incomeDescriptions: List<String> = emptyList(),
    val expenseDescriptions: List<String> = emptyList(),
)

data class TagColor(
    val name: String,
    val color: String,
)

data class MandatoryImportResult(
    val imported: Long,
    val skipped: Long,
    val errors: List<String>,
    val dryRun: Boolean,
    val blockingErrors: Boolean = false,
)

data class MandatoryExportResult(
    val exportedRows: Long,
    val path: String,
)

data class WalletOption(
    val id: Long,
    val name: String,
    val currency: String,
    val balance: String = "0.00",
)

data class WalletSettingsItem(
    val id: Long,
    val name: String,
    val currency: String,
    val initialBalance: String,
    val balance: String,
    val system: Boolean,
    val allowNegative: Boolean,
    val active: Boolean,
)

data class CreateWalletRequest(
    val name: String,
    val currency: String,
    val initialBalance: String,
    val allowNegative: Boolean,
)

data class WalletDeleteResult(
    val walletId: Long,
    val action: String,
)

data class DebtItem(
    val id: Long,
    val contactName: String,
    val kind: String,
    val totalAmount: String,
    val remainingAmount: String,
    val currency: String,
    val interestRate: String,
    val status: String,
    val createdAt: String,
    val closedAt: String? = null,
)

data class DebtPaymentItem(
    val id: Long,
    val debtId: Long,
    val recordId: Long? = null,
    val operationType: String,
    val principalPaid: String,
    val isWriteOff: Boolean,
    val paymentDate: String,
)

data class DebtDraft(
    val kind: String = "debt",
    val contactName: String = "",
    val walletId: Long = 0,
    val amount: String = "",
    val currency: String = "KZT",
    val createdAt: String = "",
    val description: String = "",
)

data class DebtActionDraft(
    val action: String = "payment",
    val debtId: Long = 0,
    val walletId: Long = 0,
    val amount: String = "",
    val paymentDate: String = "",
    val description: String = "",
)

data class CreateDebtRequest(
    val kind: String,
    val contactName: String,
    val walletId: Long,
    val amount: String,
    val currency: String,
    val createdAt: String,
    val description: String,
)

data class RegisterDebtPaymentRequest(
    val debtId: Long,
    val walletId: Long?,
    val amount: String,
    val paymentDate: String,
    val description: String,
)

data class MandatoryTemplateItem(
    val id: Long,
    val walletId: Long,
    val amountOriginal: String,
    val currency: String,
    val rateAtOperation: String,
    val amountBase: String,
    val category: String,
    val description: String,
    val period: String,
    val date: String,
    val autoPay: Boolean,
)

data class MandatoryTemplateDraft(
    val id: Long? = null,
    val walletId: Long = 0,
    val amountOriginal: String = "",
    val currency: String = "KZT",
    val rateAtOperation: String = "1",
    val amountBase: String = "",
    val category: String = "Mandatory",
    val description: String = "",
    val period: String = "monthly",
    val date: String = "",
)

data class MandatoryAddToRecordsDraft(
    val templateId: Long = 0,
    val walletId: Long = 0,
    val date: String = "",
)

data class CreateMandatoryTemplateRequest(
    val walletId: Long,
    val amountOriginal: String,
    val currency: String,
    val rateAtOperation: String,
    val amountBase: String,
    val category: String,
    val description: String,
    val period: String,
    val date: String,
)

data class UpdateMandatoryTemplateRequest(
    val walletId: Long,
    val amountBase: String,
    val period: String,
    val date: String,
)

data class AddMandatoryToRecordsRequest(
    val templateId: Long,
    val date: String,
    val walletId: Long,
)

data class MandatoryAutoPayResult(
    val createdRecords: List<OperationRecord>,
)

data class MandatoryAutoPayPopup(
    val title: String,
    val message: String,
)

data class AuditFinding(
    val check: String,
    val severity: String,
    val message: String,
    val entity: String,
)

data class AuditSummary(
    val errors: Int,
    val warnings: Int,
    val ok: Int,
    val total: Int,
)

data class EngineStatus(
    val ok: Boolean,
    val dbPath: String,
    val message: String,
)

data class ReportFilters(
    val walletId: Long? = null,
    val periodStart: String? = null,
    val periodEnd: String? = null,
    val category: String = "",
    val tag: String = "",
    val tagMode: String = "or",
    val totalsMode: String = "fixed",
    val groupByCategory: Boolean = false,
)

data class ReportSummary(
    val netWorthFixed: Double,
    val netWorthCurrent: Double,
    val initialBalance: Double,
    val recordsTotalFixed: Double,
    val recordsTotalCurrent: Double,
    val finalBalanceFixed: Double,
    val finalBalanceCurrent: Double,
    val fxDifference: Double,
    val recordsCount: Long,
    val balanceLabel: String,
    val activeTag: String,
)

data class ReportOperationRow(
    val date: String,
    val typeLabel: String,
    val kind: String,
    val category: String,
    val tagsText: String,
    val amountBase: Double,
    val amountCurrent: Double,
    val description: String,
)

data class ReportMonthlyRow(val month: String, val income: Double, val expenses: Double, val incomeCurrent: Double, val expensesCurrent: Double)
data class ReportCategoryRow(val category: String, val operationsCount: Long, val totalBase: Double, val totalCurrent: Double)
data class ReportTagRow(val tag: String, val operationsCount: Long, val totalBase: Double, val totalCurrent: Double)
data class ReportDebtRow(
    val contactName: String,
    val kind: String,
    val status: String,
    val createdAt: String,
    val closedAt: String?,
    val currency: String,
    val totalAmount: Double,
    val remainingAmount: Double,
    val settledAmount: Double,
    val progressPercent: Double,
)

data class ReportResult(
    val title: String,
    val baseCurrency: String,
    val displayCurrency: String,
    val filters: ReportFilters,
    val summary: ReportSummary,
    val operations: List<ReportOperationRow>,
    val monthly: List<ReportMonthlyRow>,
    val categories: List<ReportCategoryRow>,
    val tags: List<ReportTagRow>,
    val debts: List<ReportDebtRow>,
)

data class ReportExportResult(val exportedRows: Long, val path: String)
