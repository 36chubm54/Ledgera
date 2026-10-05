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

data class CurrencyTransferRequest(
    val fromWalletId: Long,
    val toWalletId: Long,
    val date: String,
    val sourceAmount: String,
    val sourceCurrency: String,
    val targetAmount: String,
    val targetCurrency: String,
    val conversionRate: String,
    val description: String,
    val commissionAmount: String = "",
    val commissionCurrency: String = "",
)

data class CurrencyTransferResult(
    val id: Long,
    val fromWalletId: Long,
    val toWalletId: Long,
    val date: String,
    val sourceAmount: String,
    val sourceCurrency: String,
    val targetAmount: String,
    val targetCurrency: String,
    val conversionRate: String,
    val description: String,
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

data class CurrencyRate(
    val id: Long,
    val baseCurrency: String,
    val currency: String,
    val rate: String,
    val effectiveDate: String,
    val source: String,
    val createdAt: String,
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

data class FullBackupResult(
    val path: String,
    val importedRows: Long,
    val budgetRows: Long,
    val distributionRows: Long = 0,
    val assetRows: Long = 0,
    val assetSnapshotRows: Long = 0,
    val goalRows: Long = 0,
    val currencyRateRows: Long = 0,
    val checksum: String,
)

data class DistributionSubitem(
    val id: Long,
    val itemId: Long,
    val name: String,
    val sortOrder: Long,
    val pct: Double,
    val pctMinor: Long,
    val isActive: Boolean,
    val amountBase: String,
    val amountMinor: Long,
)

data class DistributionItem(
    val id: Long,
    val name: String,
    val groupName: String,
    val sortOrder: Long,
    val pct: Double,
    val pctMinor: Long,
    val isActive: Boolean,
    val amountBase: String,
    val amountMinor: Long,
    val subitems: List<DistributionSubitem>,
)

data class DistributionMonthlyResult(
    val month: String,
    val netIncomeBase: String,
    val netIncomeMinor: Long,
    val isNegative: Boolean,
    val items: List<DistributionItem>,
)

data class DistributionColumn(val key: String, val label: String, val value: String)

data class DistributionFrozenRow(
    val month: String,
    val columns: List<DistributionColumn>,
    val isNegative: Boolean,
    val autoFixed: Boolean,
)

data class DistributionValidationError(val level: String, val message: String)

data class CreateDistributionItemRequest(
    val name: String,
    val groupName: String = "",
    val sortOrder: Long = 0,
    val pct: Double,
)

data class CreateDistributionSubitemRequest(
    val itemId: Long,
    val name: String,
    val sortOrder: Long = 0,
    val pct: Double,
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

data class CreateBudgetRequest(
    val category: String,
    val scopeType: String,
    val scopeValue: String,
    val startDate: String,
    val endDate: String,
    val limitBase: String,
    val includeMandatory: Boolean,
)

data class BudgetItem(
    val id: Long,
    val category: String,
    val scopeType: String,
    val scopeValue: String,
    val startDate: String,
    val endDate: String,
    val limitBase: String,
    val limitBaseMinor: Long,
    val includeMandatory: Boolean,
)

data class BudgetResultItem(
    val budget: BudgetItem,
    val spentBase: String,
    val spentMinor: Long,
    val remainingBase: String,
    val usagePct: Double,
    val timePct: Double,
    val status: String,
    val paceStatus: String,
    val forecastRemainingBase: String?,
    val forecastDeltaBase: String?,
    val forecastDaysLeft: Long?,
    val forecastStatusKey: String?,
    val forecastStatusParams: String?,
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

data class AnalyticsFilters(
    val periodStart: String,
    val periodEnd: String,
    val walletId: Long? = null,
    val category: String = "",
    val tag: String = "",
    val tagMode: String = "or",
    val totalsMode: String = "fixed",
    val groupByCategory: Boolean = false,
    val breakdownMode: String = "category",
    val piePeriod: String = "all_time",
    val dailyMonth: String = "",
    val monthlyYear: String = "",
)

data class AnalyticsSummary(
    val netWorthBase: Double,
    val savingsRate: Double,
    val burnRate: Double,
    val averageMonthlyIncome: Double,
    val averageMonthlyExpenses: Double,
    val yearIncome: Double,
    val yearExpense: Double,
)

data class AnalyticsCapitalPoint(val month: String, val balanceBase: Double)

data class AnalyticsBreakdownRow(
    val label: String,
    val amountBase: Double,
    val recordCount: Long,
    val color: String,
    val isOther: Boolean,
    val details: List<AnalyticsBreakdownDetail> = emptyList(),
)

data class AnalyticsBreakdownDetail(
    val label: String,
    val amountBase: Double,
    val recordCount: Long,
)

data class AnalyticsMonthlyRow(
    val month: String,
    val incomeBase: Double,
    val expensesBase: Double,
    val cashflowBase: Double,
    val savingsRate: Double,
)

data class AnalyticsDailyRow(
    val day: String,
    val incomeBase: Double,
    val expensesBase: Double,
)

data class AnalyticsSnapshot(
    val summary: AnalyticsSummary,
    val capital: List<AnalyticsCapitalPoint>,
    val categories: List<AnalyticsBreakdownRow>,
    val groupedCategories: List<AnalyticsBreakdownRow> = emptyList(),
    val tags: List<AnalyticsBreakdownRow>,
    val infographicCategories: List<AnalyticsBreakdownRow> = emptyList(),
    val monthly: List<AnalyticsMonthlyRow>,
    val daily: List<AnalyticsDailyRow>,
    val infographicMonthly: List<AnalyticsMonthlyRow>,
    val infographicDaily: List<AnalyticsDailyRow> = emptyList(),
    val suggestedCategories: List<String> = emptyList(),
    val suggestedTags: List<String> = emptyList(),
    val infographicMonths: List<String> = emptyList(),
    val infographicYears: List<String> = emptyList(),
)

data class DashboardAsset(
    val id: Long,
    val name: String,
    val category: String,
    val currency: String,
    val isActive: Boolean,
    val createdAt: String,
    val description: String,
    val currentValue: String,
    val currentValueMinor: Long,
    val currentSnapshotDate: String?,
)

data class DashboardAssetSnapshotUpdate(val assetId: Long, val value: String, val note: String)

data class DashboardAssetBreakdown(val label: String, val amountBase: String, val assetCount: Long, val color: String)
data class DashboardCapitalPoint(val month: String, val balanceBase: String)
data class DashboardGoal(
    val id: Long,
    val title: String,
    val targetAmount: String,
    val targetAmountMinor: Long,
    val currency: String,
    val targetDate: String?,
    val isCompleted: Boolean,
    val createdAt: String,
    val description: String,
    val currentAmount: String,
    val currentAmountMinor: Long,
)
data class DashboardSnapshot(
    val baseCurrency: String,
    val netWorth: String,
    val totalAssets: String,
    val activeAssetCount: Long,
    val totalAssetCount: Long,
    val completedGoalCount: Long,
    val totalGoalCount: Long,
    val capital: List<DashboardCapitalPoint>,
    val assetBreakdown: List<DashboardAssetBreakdown>,
    val assets: List<DashboardAsset>,
    val goals: List<DashboardGoal>,
)
