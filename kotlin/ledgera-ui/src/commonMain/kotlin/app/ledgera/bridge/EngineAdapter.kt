package app.ledgera.bridge

import app.ledgera.model.CreateOperationRequest
import app.ledgera.model.CreateDebtRequest
import app.ledgera.model.CreateBudgetRequest
import app.ledgera.model.BudgetItem
import app.ledgera.model.BudgetResultItem
import app.ledgera.model.CreateTransferRequest
import app.ledgera.model.CreateTransferResult
import app.ledgera.model.CreateWalletRequest
import app.ledgera.model.FullBackupResult
import app.ledgera.model.AuditFinding
import app.ledgera.model.AddMandatoryToRecordsRequest
import app.ledgera.model.DebtItem
import app.ledgera.model.DebtPaymentItem
import app.ledgera.model.EngineStatus
import app.ledgera.model.CreateMandatoryTemplateRequest
import app.ledgera.model.OperationFilter
import app.ledgera.model.OperationDeleteResult
import app.ledgera.model.OperationExportResult
import app.ledgera.model.OperationImportResult
import app.ledgera.model.OperationRecord
import app.ledgera.model.OperationSuggestions
import app.ledgera.model.TagColor
import app.ledgera.model.MandatoryAutoPayResult
import app.ledgera.model.MandatoryExportResult
import app.ledgera.model.MandatoryImportResult
import app.ledgera.model.MandatoryTemplateItem
import app.ledgera.model.RegisterDebtPaymentRequest
import app.ledgera.model.ReportFilters
import app.ledgera.model.ReportResult
import app.ledgera.model.ReportExportResult
import app.ledgera.model.TransferDetails
import app.ledgera.model.UpdateMandatoryTemplateRequest
import app.ledgera.model.UpdateOperationRequest
import app.ledgera.model.UpdateTransferRequest
import app.ledgera.model.UpdateTransferResult
import app.ledgera.model.WalletOption
import app.ledgera.model.WalletDeleteResult
import app.ledgera.model.WalletSettingsItem

interface RuntimeEngine {
    suspend fun status(): EngineStatus
}

interface ReportsEngine {
    suspend fun generateReport(filters: ReportFilters): ReportResult = error("Reports generation is unavailable")
    suspend fun reportWallets(): List<WalletOption> = emptyList()
    suspend fun reportCategories(): List<String> = emptyList()
    suspend fun reportTags(): List<String> = emptyList()
    suspend fun exportReportCsv(filters: ReportFilters, path: String): ReportExportResult = error("Reports export is unavailable")
    suspend fun exportReportXlsx(filters: ReportFilters, path: String): ReportExportResult = error("Reports export is unavailable")
    suspend fun exportReportPdf(filters: ReportFilters, path: String): ReportExportResult = error("Reports export is unavailable")
}

interface OperationsEngine {
    suspend fun baseCurrency(): String
    suspend fun listRecords(filter: OperationFilter): List<OperationRecord>
    suspend fun getRecord(recordId: Long): OperationRecord?
    suspend fun createRecord(request: CreateOperationRequest): OperationRecord
    suspend fun createRecordWithTagColors(request: CreateOperationRequest): OperationRecord
    suspend fun updateRecord(recordId: Long, request: UpdateOperationRequest): OperationRecord
    suspend fun updateRecordWithTagColors(recordId: Long, request: UpdateOperationRequest): OperationRecord
    suspend fun deleteRecord(recordId: Long): Boolean
    suspend fun createTransfer(request: CreateTransferRequest): CreateTransferResult
    suspend fun getTransfer(transferId: Long): TransferDetails?
    suspend fun updateTransfer(transferId: Long, request: UpdateTransferRequest): UpdateTransferResult
    suspend fun deleteTransfer(transferId: Long): Boolean
    suspend fun deleteAllOperations(): OperationDeleteResult
    suspend fun deleteOperationsSelection(recordIds: List<Long>, transferIds: List<Long>): OperationDeleteResult
    suspend fun previewImportRecordsCsv(path: String): OperationImportResult
    suspend fun importRecordsCsv(path: String): OperationImportResult
    suspend fun exportRecordsCsv(path: String): OperationExportResult
    suspend fun previewImportRecordsXlsx(path: String): OperationImportResult
    suspend fun importRecordsXlsx(path: String): OperationImportResult
    suspend fun exportRecordsXlsx(path: String): OperationExportResult
    suspend fun listTags(): List<String>
    suspend fun listCategories(recordType: String): List<String>
    suspend fun listRecordDescriptions(recordType: String? = null): List<String>
    suspend fun operationSuggestions(): OperationSuggestions
    suspend fun listTagColors(): List<TagColor>
    suspend fun tagColorPalette(): List<String>
    suspend fun listWallets(): List<WalletOption>
    suspend fun walletBalances(): List<WalletOption>
}

interface SettingsEngine {
    suspend fun baseCurrency(): String
    suspend fun listWalletsForSettings(): List<WalletSettingsItem>
    suspend fun createWallet(request: CreateWalletRequest): WalletSettingsItem
    suspend fun deleteWallet(walletId: Long): WalletDeleteResult
    suspend fun runAudit(): List<AuditFinding>
    suspend fun previewFullBackup(path: String): FullBackupResult = error("Full backup preview is unavailable")
    suspend fun importFullBackup(path: String): FullBackupResult = error("Full backup restore is unavailable")
    suspend fun exportFullBackup(path: String): FullBackupResult = error("Full backup export is unavailable")
}

interface BudgetEngine {
    suspend fun budgetScopeSuggestions(scopeType: String): List<String> = emptyList()
    suspend fun listBudgets(): List<BudgetItem>
    suspend fun listBudgetResults(today: String? = null): List<BudgetResultItem>
    suspend fun createBudget(request: CreateBudgetRequest): BudgetItem
    suspend fun updateBudgetLimit(budgetId: Long, limitBase: String): BudgetItem
    suspend fun deleteBudget(budgetId: Long): Boolean
}

interface DebtsEngine {
    suspend fun baseCurrency(): String
    suspend fun listWallets(): List<WalletOption>
    suspend fun listDebts(): List<DebtItem>
    suspend fun listDebtPayments(debtId: Long): List<DebtPaymentItem>
    suspend fun createDebt(request: CreateDebtRequest): DebtItem
    suspend fun registerDebtPayment(request: RegisterDebtPaymentRequest): DebtPaymentItem
    suspend fun registerDebtWriteOff(request: RegisterDebtPaymentRequest): DebtPaymentItem
    suspend fun closeDebt(request: RegisterDebtPaymentRequest): DebtItem
    suspend fun deleteDebt(debtId: Long): Boolean
    suspend fun deleteDebtPayment(paymentId: Long, deleteLinkedRecord: Boolean): DebtItem
}

interface MandatoryEngine {
    suspend fun baseCurrency(): String
    suspend fun listWallets(): List<WalletOption>
    suspend fun listMandatoryTemplates(): List<MandatoryTemplateItem>
    suspend fun getMandatoryTemplate(templateId: Long): MandatoryTemplateItem?
    suspend fun createMandatoryTemplate(request: CreateMandatoryTemplateRequest): MandatoryTemplateItem
    suspend fun updateMandatoryTemplate(templateId: Long, request: UpdateMandatoryTemplateRequest): MandatoryTemplateItem
    suspend fun deleteMandatoryTemplate(templateId: Long): Boolean
    suspend fun deleteAllMandatoryTemplates(): Long
    suspend fun addMandatoryToRecords(request: AddMandatoryToRecordsRequest): OperationRecord
    suspend fun applyMandatoryAutoPayments(today: String): MandatoryAutoPayResult
    suspend fun previewImportMandatoryCsv(path: String): MandatoryImportResult
    suspend fun importMandatoryCsv(path: String): MandatoryImportResult
    suspend fun exportMandatoryCsv(path: String): MandatoryExportResult
    suspend fun previewImportMandatoryXlsx(path: String): MandatoryImportResult
    suspend fun importMandatoryXlsx(path: String): MandatoryImportResult
    suspend fun exportMandatoryXlsx(path: String): MandatoryExportResult
}

interface EngineAdapter : RuntimeEngine, ReportsEngine, OperationsEngine, SettingsEngine, DebtsEngine, MandatoryEngine, BudgetEngine
