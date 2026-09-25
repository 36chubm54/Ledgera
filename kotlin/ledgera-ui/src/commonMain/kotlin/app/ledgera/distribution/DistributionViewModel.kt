package app.ledgera.distribution

import app.ledgera.bridge.DistributionEngine
import app.ledgera.model.CreateDistributionItemRequest
import app.ledgera.model.CreateDistributionSubitemRequest
import app.ledgera.model.DistributionFrozenRow
import app.ledgera.model.DistributionItem
import app.ledgera.model.DistributionMonthlyResult
import app.ledgera.model.DistributionValidationError
import app.ledgera.validation.currentLedgerDate
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class DistributionUiState(
    val startMonth: String = "${currentLedgerDate().year}-01",
    val endMonth: String = "${currentLedgerDate().year}-${currentLedgerDate().month.toString().padStart(2, '0')}",
    val items: List<DistributionItem> = emptyList(),
    val history: List<DistributionMonthlyResult> = emptyList(),
    val frozenRows: List<DistributionFrozenRow> = emptyList(),
    val expandedIds: Set<String> = emptySet(),
    val collapsedGroups: Set<String> = emptySet(),
    val selectedItemId: Long? = null,
    val selectedSubitemId: Long? = null,
    val selectedMonth: String? = null,
    val validation: List<DistributionValidationError> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
    val notice: String? = null,
)

class DistributionViewModel(
    private val engine: DistributionEngine,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
) {
    private val mutableState = MutableStateFlow(DistributionUiState(loading = true))
    private var refreshJob: Job? = null
    private var generation = 0L
    val state: StateFlow<DistributionUiState> = mutableState.asStateFlow()

    init { refresh() }

    fun updateStartMonth(value: String) = mutableState.update { it.copy(startMonth = value, error = null) }
    fun updateEndMonth(value: String) = mutableState.update { it.copy(endMonth = value, error = null) }
    fun selectMonth(month: String) = mutableState.update { it.copy(selectedMonth = month) }
    fun selectItem(itemId: Long) = mutableState.update { it.copy(selectedItemId = itemId, selectedSubitemId = null) }
    fun selectSubitem(itemId: Long, subitemId: Long) = mutableState.update { it.copy(selectedItemId = itemId, selectedSubitemId = subitemId) }
    fun toggleExpanded(id: String) = mutableState.update {
        it.copy(
            expandedIds = if (id in it.expandedIds) it.expandedIds - id else it.expandedIds + id,
        )
    }
    fun toggleGroup(group: String) = mutableState.update {
        it.copy(collapsedGroups = if (group in it.collapsedGroups) it.collapsedGroups - group else it.collapsedGroups + group)
    }

    fun refresh() {
        refreshJob?.cancel()
        val requestGeneration = ++generation
        val current = mutableState.value
        if (!validMonth(current.startMonth) || !validMonth(current.endMonth) || current.startMonth > current.endMonth) {
            mutableState.value = current.copy(error = "Period must use YYYY-MM and start must not be after end", loading = false)
            return
        }
        mutableState.value = current.copy(loading = true, error = null, notice = null)
        refreshJob = scope.launch {
            runCatching {
                RefreshPayload(
                    engine.distributionItems(true),
                    engine.distributionHistory(current.startMonth, current.endMonth),
                    engine.frozenDistributionRows(current.startMonth, current.endMonth),
                    engine.validateDistribution(),
                )
            }.onSuccess { payload ->
                if (requestGeneration == generation) mutableState.value = mutableState.value.copy(
                    items = payload.items,
                    history = payload.history,
                    frozenRows = payload.frozenRows,
                    validation = payload.validation,
                    loading = false,
                    error = null,
                    selectedMonth = mutableState.value.selectedMonth?.takeIf { month ->
                        payload.history.any { it.month == month } || payload.frozenRows.any { it.month == month }
                    },
                )
            }.onFailure { error ->
                if (requestGeneration == generation && error !is CancellationException) {
                    mutableState.value = mutableState.value.copy(loading = false, error = error.message ?: "Failed to load Distribution")
                }
            }
        }
    }

    fun addItem(name: String, group: String, pct: Double) = mutate {
        engine.createDistributionItem(CreateDistributionItemRequest(name.trim(), group.trim(), pct = pct))
    }
    fun addSubitem(itemId: Long, name: String, pct: Double) = mutate {
        engine.createDistributionSubitem(CreateDistributionSubitemRequest(itemId, name.trim(), pct = pct))
    }
    fun updateItemPct(id: Long, pct: Double) = mutate { engine.updateDistributionItemPct(id, pct) }
    fun updateSubitemPct(id: Long, pct: Double) = mutate { engine.updateDistributionSubitemPct(id, pct) }
    fun updateItem(id: Long, name: String, pct: Double) = mutate { engine.updateDistributionItem(id, name.trim(), pct) }
    fun updateSubitem(id: Long, name: String, pct: Double) = mutate { engine.updateDistributionSubitem(id, name.trim(), pct) }
    fun renameItem(id: Long, name: String) = mutate { engine.renameDistributionItem(id, name.trim()) }
    fun renameSubitem(id: Long, name: String) = mutate { engine.renameDistributionSubitem(id, name.trim()) }
    fun deleteItem(id: Long) = mutate { engine.deleteDistributionItem(id) }
    fun deleteSubitem(id: Long) = mutate { engine.deleteDistributionSubitem(id) }

    fun toggleFixed(month: String) {
        scope.launch {
            runCatching {
                if (engine.isDistributionMonthFixed(month)) {
                    if (engine.isDistributionMonthAutoFixed(month)) error("Month $month is auto-fixed and cannot be unfixed")
                    engine.unfreezeDistributionMonth(month)
                } else engine.freezeDistributionMonth(month)
            }.onSuccess { mutableState.update { it.copy(notice = "Distribution row updated") }; refresh() }
                .onFailure { error -> mutableState.update { it.copy(error = error.message ?: "Failed to update row") } }
        }
    }

    private fun mutate(action: suspend () -> Any) {
        scope.launch {
            runCatching { action() }
                .onSuccess { mutableState.update { it.copy(notice = "Distribution updated") }; refresh() }
                .onFailure { error -> mutableState.update { it.copy(error = error.message ?: "Distribution update failed") } }
        }
    }

    private data class RefreshPayload(
        val items: List<DistributionItem>,
        val history: List<DistributionMonthlyResult>,
        val frozenRows: List<DistributionFrozenRow>,
        val validation: List<DistributionValidationError>,
    )

    private fun validMonth(value: String): Boolean = value.matches(Regex("\\d{4}-(0[1-9]|1[0-2])"))
}
