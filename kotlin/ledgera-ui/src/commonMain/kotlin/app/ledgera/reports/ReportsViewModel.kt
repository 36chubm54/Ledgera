package app.ledgera.reports

import app.ledgera.bridge.ReportsEngine
import app.ledgera.model.ReportFilters
import app.ledgera.model.ReportResult
import app.ledgera.model.WalletOption
import app.ledgera.validation.DateValidation
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ReportsUiState(
    val loading: Boolean = false,
    val wallets: List<WalletOption> = emptyList(),
    val categories: List<String> = emptyList(),
    val tags: List<String> = emptyList(),
    val periodStart: String = "",
    val periodEnd: String = "",
    val walletId: Long? = null,
    val category: String = "",
    val tag: String = "",
    val tagMode: String = "or",
    val totalsMode: String = "fixed",
    val groupByCategory: Boolean = false,
    val result: ReportResult? = null,
    val periodStartError: String? = null,
    val periodEndError: String? = null,
    val error: String? = null,
    val notice: String? = null,
)

class ReportsViewModel(
    private val engine: ReportsEngine,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
) {
    private val mutableState = MutableStateFlow(ReportsUiState(loading = true))
    val state: StateFlow<ReportsUiState> = mutableState.asStateFlow()

    init { refreshLookups() }

    fun clearFeedback() { mutableState.value = mutableState.value.copy(error = null, notice = null) }
    fun updatePeriodStart(value: String) { mutableState.value = mutableState.value.copy(periodStart = value, periodStartError = null, periodEndError = null, error = null) }
    fun updatePeriodEnd(value: String) { mutableState.value = mutableState.value.copy(periodEnd = value, periodEndError = null, error = null) }
    fun updateWallet(value: Long?) { mutableState.value = mutableState.value.copy(walletId = value) }
    fun updateCategory(value: String) { mutableState.value = mutableState.value.copy(category = value) }
    fun updateTag(value: String) { mutableState.value = mutableState.value.copy(tag = value) }
    fun updateTagMode(value: String) { mutableState.value = mutableState.value.copy(tagMode = value) }
    fun updateTotalsMode(value: String) { mutableState.value = mutableState.value.copy(totalsMode = value) }
    fun updateGrouping(value: Boolean) { mutableState.value = mutableState.value.copy(groupByCategory = value) }

    fun refreshLookups() {
        scope.launch {
            runCatching {
                engine.reportWallets()
            }.onSuccess { wallets ->
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    wallets = wallets,
                    categories = runCatching { engine.reportCategories() }.getOrDefault(emptyList()),
                    tags = runCatching { engine.reportTags() }.getOrDefault(emptyList()),
                )
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(loading = false, error = error.message ?: "Failed to load Reports")
            }
        }
    }

    fun generate() {
        val current = mutableState.value
        val start = current.periodStart.trim()
        val end = current.periodEnd.trim()
        val startYmd = if (start.isBlank()) null else DateValidation.parseDmyStrict(start)?.let(DateValidation::formatYmd)
        val endYmd = if (end.isBlank()) null else DateValidation.parseDmyStrict(end)?.let(DateValidation::formatYmd)
        if (start.isNotBlank() && startYmd == null) return setPeriodError(start = "Start date must use DD.MM.YYYY")
        if (end.isNotBlank() && endYmd == null) return setPeriodError(end = "End date must use DD.MM.YYYY")
        if (startYmd == null && endYmd != null) return setPeriodError(start = "Start date is required when an end date is set")
        mutableState.value = current.copy(loading = true, periodStartError = null, periodEndError = null, error = null, notice = null)
        scope.launch {
            runCatching {
                engine.generateReport(ReportFilters(current.walletId, startYmd, endYmd, current.category, current.tag, current.tagMode, current.totalsMode, current.groupByCategory))
            }.onSuccess { result ->
                mutableState.value = mutableState.value.copy(loading = false, result = result, error = null, notice = "Report generated")
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(loading = false, error = error.message ?: "Failed to generate report", notice = null)
            }
        }
    }

    fun export(format: String, fileActions: ReportsFileActions) {
        val current = mutableState.value
        if (current.result == null) return fail("Generate a report before exporting")
        val path = fileActions.saveReportPath(format) ?: return
        mutableState.value = current.copy(loading = true, error = null, notice = null)
        scope.launch {
            runCatching {
                val filters = current.result.filters
                when (format.lowercase()) {
                    "csv" -> engine.exportReportCsv(filters, path)
                    "xlsx" -> engine.exportReportXlsx(filters, path)
                    "pdf" -> engine.exportReportPdf(filters, path)
                    else -> error("Unsupported report format")
                }
            }.onSuccess { result ->
                mutableState.value = mutableState.value.copy(loading = false, notice = "Report exported: ${result.exportedRows}", error = null)
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(loading = false, error = error.message ?: "Failed to export report", notice = null)
            }
        }
    }

    private fun setPeriodError(start: String? = null, end: String? = null) {
        mutableState.value = mutableState.value.copy(loading = false, periodStartError = start, periodEndError = end, error = null, notice = null)
    }

    private fun fail(message: String) { mutableState.value = mutableState.value.copy(loading = false, error = message, notice = null) }
}
