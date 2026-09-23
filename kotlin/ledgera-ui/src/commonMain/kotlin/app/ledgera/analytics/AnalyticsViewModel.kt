package app.ledgera.analytics

import app.ledgera.bridge.AnalyticsEngine
import app.ledgera.model.AnalyticsFilters
import app.ledgera.model.AnalyticsSnapshot
import app.ledgera.validation.DateValidation
import app.ledgera.validation.currentLedgerDate
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AnalyticsUiState(
    val periodStart: String = DateValidation.formatDmy(currentLedgerDate().copy(month = 1, day = 1)),
    val periodEnd: String = DateValidation.formatDmy(currentLedgerDate()),
    val category: String = "",
    val tag: String = "",
    val tagMode: String = "or",
    val totalsMode: String = "fixed",
    val groupByCategory: Boolean = false,
    val categories: List<String> = emptyList(),
    val tags: List<String> = emptyList(),
    val breakdownMode: String = "category",
    val piePeriod: String = "all_time",
    val dailyMonth: String = DateValidation.formatYmd(currentLedgerDate()).take(7),
    val monthlyYear: String = DateValidation.formatYmd(currentLedgerDate()).take(4),
    val infographicMonths: List<String> = emptyList(),
    val infographicYears: List<String> = emptyList(),
    val snapshot: AnalyticsSnapshot? = null,
    val loading: Boolean = false,
    val error: String? = null,
)

private data class AnalyticsRefreshPayload(
    val snapshot: AnalyticsSnapshot,
    val categories: List<String>,
    val tags: List<String>,
    val months: List<String>,
    val years: List<String>,
)

class AnalyticsViewModel(
    private val engine: AnalyticsEngine,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
) {
    private val mutableState = MutableStateFlow(AnalyticsUiState())
    private var refreshJob: Job? = null
    private var refreshGeneration = 0L
    val state: StateFlow<AnalyticsUiState> = mutableState.asStateFlow()

    init { generate() }

    fun updatePeriodStart(value: String) = mutableState.update { it.copy(periodStart = value, error = null) }
    fun updatePeriodEnd(value: String) = mutableState.update { it.copy(periodEnd = value, error = null) }
    fun updateCategory(value: String) = mutableState.update { it.copy(category = value, error = null) }
    fun updateTag(value: String) = mutableState.update { it.copy(tag = value, error = null) }
    fun updateTagMode(value: String) = mutableState.update { it.copy(tagMode = value, error = null) }
    fun updateTotalsMode(value: String) = mutableState.update { it.copy(totalsMode = value, error = null) }
    fun updateGrouping(value: Boolean) = mutableState.update { it.copy(groupByCategory = value, error = null) }
    fun updateBreakdownMode(value: String) = mutableState.update { it.copy(breakdownMode = value, error = null) }
    fun updatePiePeriod(value: String) = mutableState.update { it.copy(piePeriod = value, error = null) }
    fun updateDailyMonth(value: String) = mutableState.update { it.copy(dailyMonth = value, error = null) }
    fun updateMonthlyYear(value: String) = mutableState.update { it.copy(monthlyYear = value, error = null) }

    fun generate() {
        refreshJob?.cancel()
        val generation = ++refreshGeneration
        val current = mutableState.value
        val start = DateValidation.formatGuiDateToYmd(current.periodStart)
        val end = DateValidation.formatGuiDateToYmd(current.periodEnd)
        if (start == null || end == null) {
            mutableState.value = current.copy(error = "Period dates must use DD.MM.YYYY")
            return
        }
        if (DateValidation.parseYmd(start)!! > DateValidation.parseYmd(end)!!) {
            mutableState.value = current.copy(error = "Start date must not be after end date")
            return
        }
        mutableState.value = current.copy(loading = true, error = null)
        refreshJob = scope.launch {
            runCatching {
                val filters = AnalyticsFilters(
                    periodStart = start,
                    periodEnd = end,
                    category = current.category,
                    tag = current.tag,
                    tagMode = current.tagMode,
                    totalsMode = current.totalsMode,
                    groupByCategory = current.groupByCategory,
                    breakdownMode = current.breakdownMode,
                    piePeriod = current.piePeriod,
                    dailyMonth = current.dailyMonth,
                    monthlyYear = current.monthlyYear,
                )
                val snapshot = engine.generateAnalyticsSnapshot(filters)
                AnalyticsRefreshPayload(
                    snapshot,
                    snapshot.suggestedCategories,
                    snapshot.suggestedTags,
                    snapshot.infographicMonths,
                    snapshot.infographicYears,
                )
            }.onSuccess { payload ->
                if (generation == refreshGeneration) {
                    mutableState.value = mutableState.value.copy(
                        loading = false,
                        snapshot = payload.snapshot,
                        categories = payload.categories,
                        tags = payload.tags,
                        infographicMonths = payload.months,
                        infographicYears = payload.years,
                        error = null,
                    )
                }
            }.onFailure { error ->
                if (generation == refreshGeneration && error !is CancellationException) {
                    mutableState.value = mutableState.value.copy(
                        loading = false,
                        error = error.message ?: "Failed to generate Analytics",
                    )
                }
            }
        }
    }
}
