package app.ledgera.mandatory

import app.ledgera.bridge.MandatoryEngine
import app.ledgera.model.AddMandatoryToRecordsRequest
import app.ledgera.model.CreateMandatoryTemplateRequest
import app.ledgera.model.CurrencyRate
import app.ledgera.model.MandatoryAddToRecordsDraft
import app.ledgera.model.MandatoryAutoPayPopup
import app.ledgera.model.MandatoryImportResult
import app.ledgera.model.MandatoryTemplateDraft
import app.ledgera.model.MandatoryTemplateItem
import app.ledgera.model.UpdateMandatoryTemplateRequest
import app.ledgera.model.WalletOption
import app.ledgera.operations.ImportFileSnapshotProvider
import app.ledgera.validation.DateValidation
import app.ledgera.validation.currentLedgerDate
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class MandatoryUiState(
    val loading: Boolean = false,
    val templates: List<MandatoryTemplateItem> = emptyList(),
    val selectedTemplateId: Long? = null,
    val wallets: List<WalletOption> = emptyList(),
    val baseCurrency: String = "KZT",
    val currencyRates: List<CurrencyRate> = emptyList(),
    val categorySuggestions: List<String> = emptyList(),
    val editDraft: MandatoryTemplateDraft? = null,
    val addToRecordsDraft: MandatoryAddToRecordsDraft? = null,
    val deleteTemplateId: Long? = null,
    val confirmDeleteAll: Boolean = false,
    val importPreview: MandatoryImportResult? = null,
    val importPath: String? = null,
    val importFileSnapshot: String? = null,
    val inProgress: Boolean = false,
    val error: String? = null,
    val notice: String? = null,
    val autoPayPopup: MandatoryAutoPayPopup? = null,
)

class MandatoryViewModel(
    private val engine: MandatoryEngine,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
    private val importFileSnapshotProvider: ImportFileSnapshotProvider = NoMandatoryImportFileSnapshotProvider,
) {
    private val mutableState = MutableStateFlow(MandatoryUiState(loading = true))
    val state: StateFlow<MandatoryUiState> = mutableState.asStateFlow()

    fun refresh() {
        refresh(null)
    }

    private fun refresh(notice: String?) {
        val previous = mutableState.value
        mutableState.value = previous.copy(loading = true, error = null, notice = notice)
        launchSafely {
            runCatching {
                val baseCurrency = engine.baseCurrency()
                val wallets = engine.listWallets()
                val templates = engine.listMandatoryTemplates()
                val currencyRates = engine.currencyRates()
                val suggestions = engine.operationSuggestions()
                val selectedTemplateId = previous.selectedTemplateId?.takeIf { id ->
                    templates.any { it.id == id }
                } ?: templates.firstOrNull()?.id
                val latest = mutableState.value
                mutableState.value = MandatoryUiState(
                    loading = false,
                    templates = templates,
                    selectedTemplateId = selectedTemplateId,
                    wallets = wallets,
                    baseCurrency = baseCurrency,
                    currencyRates = currencyRates,
                    categorySuggestions = (suggestions.expenseCategories + templates.map { it.category })
                        .map(String::trim)
                        .filter(String::isNotEmpty)
                        .distinct()
                        .sorted(),
                    editDraft = previous.editDraft,
                    addToRecordsDraft = previous.addToRecordsDraft,
                    deleteTemplateId = previous.deleteTemplateId?.takeIf { id ->
                        templates.any { it.id == id }
                    },
                    confirmDeleteAll = previous.confirmDeleteAll,
                    importPreview = previous.importPreview,
                    importPath = previous.importPath,
                    importFileSnapshot = previous.importFileSnapshot,
                    inProgress = latest.inProgress,
                    notice = notice,
                    autoPayPopup = latest.autoPayPopup,
                )
            }.onFailure { error ->
                val latest = mutableState.value
                mutableState.value = latest.copy(
                    loading = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun selectTemplate(templateId: Long) {
        val template = mutableState.value.templates.firstOrNull { it.id == templateId }
        if (template == null) {
            mutableState.value = mutableState.value.copy(error = "Mandatory template not found", notice = null)
            return
        }
        mutableState.value = mutableState.value.copy(
            selectedTemplateId = templateId,
            editDraft = template.toDraft(),
            error = null,
            notice = null,
        )
    }

    fun openCreateDialog() {
        val state = mutableState.value
        mutableState.value = state.copy(
            editDraft = MandatoryTemplateDraft(
                walletId = state.wallets.firstOrNull()?.id ?: 0,
                currency = state.baseCurrency,
                rateAtOperation = "1",
                category = "Mandatory",
                period = "monthly",
            ),
            error = null,
            notice = null,
        )
    }

    fun closeEditDialog() {
        mutableState.value = mutableState.value.copy(editDraft = null, inProgress = false, error = null)
    }

    fun updateDraft(draft: MandatoryTemplateDraft) {
        val current = mutableState.value
        mutableState.value = current.copy(
            editDraft = recalculateDraft(draft, current.baseCurrency, current.currencyRates),
            error = null,
            notice = null,
        )
    }

    fun saveTemplate() {
        val state = mutableState.value
        val draft = state.editDraft ?: return
        val validationError = if (draft.id == null) {
            MandatoryValidation.validateCreateDraft(draft, state.baseCurrency)
        } else {
            MandatoryValidation.validateUpdateDraft(draft)
        }
        if (validationError != null) {
            mutableState.value = state.copy(error = validationError, notice = null)
            return
        }
        mutableState.value = state.copy(inProgress = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val saved = if (draft.id == null) {
                    engine.createMandatoryTemplate(
                        CreateMandatoryTemplateRequest(
                            walletId = draft.walletId,
                            amountOriginal = draft.amountOriginal.trim(),
                            currency = draft.currency.trim().uppercase(),
                            rateAtOperation = draft.rateAtOperation.trim().ifBlank { "1" },
                            amountBase = draft.amountBase.trim(),
                            category = draft.category.trim(),
                            description = draft.description.trim(),
                            period = draft.period.trim().lowercase(),
                            date = draft.date.toStorageDate(),
                        )
                    )
                } else {
                    engine.updateMandatoryTemplate(
                        draft.id,
                        UpdateMandatoryTemplateRequest(
                            walletId = draft.walletId,
                            amountBase = draft.amountBase.trim(),
                            period = draft.period.trim().lowercase(),
                            date = draft.date.toStorageDate(),
                        )
                    )
                }
                mutableState.value = mutableState.value.copy(
                    selectedTemplateId = saved.id,
                    editDraft = null,
                    inProgress = false,
                )
                refresh(
                    if (draft.id == null) {
                        "Mandatory template created (id=${saved.id})"
                    } else {
                        "Mandatory template updated (id=${saved.id})"
                    }
                )
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    inProgress = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun openAddToRecordsDialog() {
        val state = mutableState.value
        val templateId = state.selectedTemplateId
        if (templateId == null) {
            mutableState.value = state.copy(error = "Select a mandatory template first", notice = null)
            return
        }
        mutableState.value = state.copy(
            addToRecordsDraft = MandatoryAddToRecordsDraft(
                templateId = templateId,
                walletId = state.wallets.firstOrNull()?.id ?: 0,
                date = todayDisplayText(),
            ),
            error = null,
            notice = null,
        )
    }

    fun closeAddToRecordsDialog() {
        mutableState.value = mutableState.value.copy(addToRecordsDraft = null, inProgress = false, error = null)
    }

    fun updateAddToRecordsDraft(draft: MandatoryAddToRecordsDraft) {
        mutableState.value = mutableState.value.copy(addToRecordsDraft = draft, error = null, notice = null)
    }

    fun addToRecords() {
        val state = mutableState.value
        val draft = state.addToRecordsDraft ?: return
        MandatoryValidation.validateAddToRecordsDraft(draft)?.let { validationError ->
            mutableState.value = state.copy(error = validationError, notice = null)
            return
        }
        mutableState.value = state.copy(inProgress = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val record = engine.addMandatoryToRecords(
                    AddMandatoryToRecordsRequest(
                        templateId = draft.templateId,
                        date = draft.date.toStorageDate(),
                        walletId = draft.walletId,
                    )
                )
                mutableState.value = mutableState.value.copy(
                    addToRecordsDraft = null,
                    inProgress = false,
                    selectedTemplateId = draft.templateId,
                )
                refresh("Mandatory record added (id=${record.id})")
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    inProgress = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun applyAutoPayments() {
        applyAutoPayments(showWhenEmpty = true)
    }

    fun applyAutoPaymentsOnStartup() {
        applyAutoPayments(showWhenEmpty = false)
    }

    private fun applyAutoPayments(showWhenEmpty: Boolean) {
        val state = mutableState.value
        val today = todayStorageText()
        mutableState.value = state.copy(
            inProgress = true,
            editDraft = null,
            addToRecordsDraft = null,
            deleteTemplateId = null,
            confirmDeleteAll = false,
            importPreview = null,
            importPath = null,
            importFileSnapshot = null,
            error = null,
            notice = null,
        )
        launchSafely {
            runCatching {
                val result = engine.applyMandatoryAutoPayments(today)
                val popup = if (result.createdRecords.isNotEmpty() || showWhenEmpty) {
                    autoPayPopup(result.createdRecords.size)
                } else {
                    null
                }
                mutableState.value = mutableState.value.copy(
                    inProgress = false,
                    autoPayPopup = popup,
                )
                refresh(notice = null)
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    inProgress = false,
                    error = null,
                    autoPayPopup = MandatoryAutoPayPopup(
                        title = "Auto-pay failed",
                        message = error.message ?: error::class.simpleName ?: "Unknown error",
                    ),
                    notice = null,
                )
            }
        }
    }

    fun requestDeleteSelectedTemplate() {
        val state = mutableState.value
        val templateId = state.selectedTemplateId
        if (templateId == null) {
            mutableState.value = state.copy(error = "Select a mandatory template first", notice = null)
            return
        }
        mutableState.value = state.copy(deleteTemplateId = templateId, error = null, notice = null)
    }

    fun closeDeleteTemplateDialog() {
        mutableState.value = mutableState.value.copy(deleteTemplateId = null, inProgress = false, error = null)
    }

    fun deleteSelectedTemplate() {
        val state = mutableState.value
        val templateId = state.deleteTemplateId ?: return
        mutableState.value = state.copy(inProgress = true, error = null, notice = null)
        launchSafely {
            runCatching {
                engine.deleteMandatoryTemplate(templateId)
                mutableState.value = mutableState.value.copy(
                    deleteTemplateId = null,
                    selectedTemplateId = null,
                    inProgress = false,
                )
                refresh("Mandatory template deleted (id=$templateId)")
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    inProgress = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun requestDeleteAllTemplates() {
        mutableState.value = mutableState.value.copy(confirmDeleteAll = true, error = null, notice = null)
    }

    fun closeDeleteAllDialog() {
        mutableState.value = mutableState.value.copy(confirmDeleteAll = false, inProgress = false, error = null)
    }

    fun deleteAllTemplates() {
        val state = mutableState.value
        mutableState.value = state.copy(inProgress = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val deleted = engine.deleteAllMandatoryTemplates()
                mutableState.value = mutableState.value.copy(
                    confirmDeleteAll = false,
                    selectedTemplateId = null,
                    inProgress = false,
                )
                refresh("All mandatory templates deleted ($deleted)")
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    inProgress = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun previewImportMandatory(path: String?) {
        val normalizedPath = path?.trim().orEmpty()
        if (normalizedPath.isEmpty()) {
            return
        }
        val format = mandatoryFileFormat(normalizedPath)
        if (format == null) {
            mutableState.value = mutableState.value.copy(
                error = "Unsupported mandatory file format. Use .csv or .xlsx",
                notice = null,
            )
            return
        }
        mutableState.value = mutableState.value.copy(
            loading = true,
            error = null,
            notice = null,
            importPreview = null,
            importPath = normalizedPath,
            importFileSnapshot = importFileSnapshotProvider.snapshot(normalizedPath),
        )
        launchSafely {
            runCatching {
                val result = when (format) {
                    MandatoryFileFormat.Csv -> engine.previewImportMandatoryCsv(normalizedPath)
                    MandatoryFileFormat.Xlsx -> engine.previewImportMandatoryXlsx(normalizedPath)
                }
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    importPreview = result,
                    importPath = normalizedPath,
                    importFileSnapshot = importFileSnapshotProvider.snapshot(normalizedPath),
                    error = null,
                    notice = null,
                )
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    importPreview = null,
                    importPath = null,
                    importFileSnapshot = null,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun cancelImportPreview() {
        mutableState.value = mutableState.value.copy(
            importPreview = null,
            importPath = null,
            importFileSnapshot = null,
            error = null,
        )
    }

    fun confirmImportMandatory() {
        val state = mutableState.value
        val path = state.importPath
        if (path.isNullOrBlank()) {
            mutableState.value = state.copy(error = "Import file is required", notice = null)
            return
        }
        if (state.importPreview?.blockingErrors == true) {
            mutableState.value = state.copy(
                loading = false,
                error = "Import preview has blocking errors. Fix the file and run preview again.",
                notice = null,
            )
            return
        }
        val expectedSnapshot = state.importFileSnapshot
        val currentSnapshot = importFileSnapshotProvider.snapshot(path)
        if (expectedSnapshot != null && currentSnapshot != expectedSnapshot) {
            mutableState.value = state.copy(
                loading = false,
                error = "Import file changed after preview. Run preview again.",
                notice = null,
            )
            return
        }
        val format = mandatoryFileFormat(path)
        if (format == null) {
            mutableState.value = state.copy(
                error = "Unsupported mandatory file format. Use .csv or .xlsx",
                notice = null,
            )
            return
        }
        mutableState.value = state.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val result = when (format) {
                    MandatoryFileFormat.Csv -> engine.importMandatoryCsv(path)
                    MandatoryFileFormat.Xlsx -> engine.importMandatoryXlsx(path)
                }
                mutableState.value = mutableState.value.copy(
                    selectedTemplateId = null,
                    importPreview = null,
                    importPath = null,
                    importFileSnapshot = null,
                )
                refresh("Mandatory templates imported: ${result.imported}")
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun exportMandatory(path: String?) {
        val normalizedPath = path?.trim().orEmpty()
        if (normalizedPath.isEmpty()) {
            return
        }
        val format = mandatoryFileFormat(normalizedPath)
        if (format == null) {
            mutableState.value = mutableState.value.copy(
                error = "Unsupported mandatory file format. Use .csv or .xlsx",
                notice = null,
            )
            return
        }
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val result = when (format) {
                    MandatoryFileFormat.Csv -> engine.exportMandatoryCsv(normalizedPath)
                    MandatoryFileFormat.Xlsx -> engine.exportMandatoryXlsx(normalizedPath)
                }
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    error = null,
                    notice = "Mandatory templates exported: ${result.exportedRows}",
                )
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun clearNotice() {
        mutableState.value = mutableState.value.copy(notice = null)
    }

    fun clearFeedback() {
        mutableState.value = mutableState.value.copy(error = null, notice = null)
    }

    fun closeAutoPayPopup() {
        mutableState.value = mutableState.value.copy(autoPayPopup = null)
    }

    private fun autoPayPopup(createdCount: Int): MandatoryAutoPayPopup =
        MandatoryAutoPayPopup(
            title = "Auto-pay applied",
            message = if (createdCount == 1) {
                "Created 1 mandatory operation record."
            } else {
                "Created $createdCount mandatory operation records."
            },
        )

    private fun launchSafely(block: suspend () -> Unit) {
        scope.launch { block() }
    }

    private fun MandatoryTemplateItem.toDraft(): MandatoryTemplateDraft =
        MandatoryTemplateDraft(
            id = id,
            walletId = walletId,
            amountOriginal = amountOriginal,
            currency = currency,
            rateAtOperation = rateAtOperation,
            amountBase = amountBase,
            category = category,
            description = description,
            period = period,
            date = date.toDisplayDate(),
        )

    private fun recalculateDraft(
        draft: MandatoryTemplateDraft,
        baseCurrency: String,
        rates: List<CurrencyRate>,
    ): MandatoryTemplateDraft {
        if (draft.id != null) return draft
        val amount = draft.amountOriginal.trim().toDoubleOrNull()
        if (amount == null || amount <= 0.0) {
            return draft.copy(amountBase = "", rateAtOperation = "")
        }
        val currency = draft.currency.trim().uppercase()
        val effectiveDate = draft.date.toStorageDate().ifBlank { todayStorageText() }
        val rate = if (currency == baseCurrency.uppercase()) {
            1.0
        } else {
            rates.asSequence()
                .filter { it.baseCurrency.equals(baseCurrency, ignoreCase = true) }
                .filter { it.currency.equals(currency, ignoreCase = true) }
                .filter { it.effectiveDate <= effectiveDate }
                .maxWithOrNull(compareBy<CurrencyRate> { it.effectiveDate }.thenBy { it.id })
                ?.rate
                ?.toDoubleOrNull()
        }
        if (rate == null || rate <= 0.0) {
            return draft.copy(amountBase = "", rateAtOperation = "")
        }
        return draft.copy(
            amountBase = "%.2f".format(amount * rate),
            rateAtOperation = "%.10f".format(rate),
        )
    }

    private fun todayDisplayText(): String =
        currentLedgerDate().let { "%02d.%02d.%04d".format(it.day, it.month, it.year) }

    private fun todayStorageText(): String =
        currentLedgerDate().let { "%04d-%02d-%02d".format(it.year, it.month, it.day) }

    private fun String.toStorageDate(): String =
        DateValidation.formatGuiDateToYmd(this) ?: trim()

    private fun String.toDisplayDate(): String =
        DateValidation.formatYmdToDmy(this).ifBlank { trim() }
}

private enum class MandatoryFileFormat {
    Csv,
    Xlsx,
}

private fun mandatoryFileFormat(path: String): MandatoryFileFormat? =
    when (path.substringAfterLast('.', missingDelimiterValue = "").lowercase()) {
        "csv" -> MandatoryFileFormat.Csv
        "xlsx" -> MandatoryFileFormat.Xlsx
        else -> null
    }

private object NoMandatoryImportFileSnapshotProvider : ImportFileSnapshotProvider {
    override fun snapshot(path: String): String? = null
}
