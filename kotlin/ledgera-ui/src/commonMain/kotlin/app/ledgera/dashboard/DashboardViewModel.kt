package app.ledgera.dashboard

import app.ledgera.bridge.DashboardEngine
import app.ledgera.model.DashboardAsset
import app.ledgera.model.DashboardSnapshot
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

data class DashboardUiState(
    val snapshot: DashboardSnapshot? = null,
    val selectedAssetId: Long? = null,
    val selectedCategory: String? = null,
    val selectedGoalId: Long? = null,
    val loading: Boolean = false,
    val error: String? = null,
    val notice: String? = null,
)

data class DashboardSnapshotUpdate(
    val assetId: Long,
    val value: String,
    val note: String,
)

class DashboardViewModel(
    private val engine: DashboardEngine,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
) {
    private val mutableState = MutableStateFlow(DashboardUiState(loading = true))
    private var refreshJob: Job? = null
    private var generation = 0L
    val state: StateFlow<DashboardUiState> = mutableState.asStateFlow()

    init { refresh() }

    fun refresh() {
        refreshJob?.cancel()
        val requestGeneration = ++generation
        mutableState.update { it.copy(loading = true, error = null, notice = null) }
        refreshJob = scope.launch {
            runCatching { engine.dashboardSnapshot() }
                .onSuccess { snapshot ->
                    if (requestGeneration == generation) mutableState.update { current ->
                        current.copy(
                            snapshot = snapshot,
                            selectedAssetId = current.selectedAssetId?.takeIf { id -> snapshot.assets.any { it.id == id } },
                            selectedGoalId = current.selectedGoalId?.takeIf { id -> snapshot.goals.any { it.id == id } },
                            loading = false,
                            error = null,
                        )
                    }
                }
                .onFailure { error ->
                    if (requestGeneration == generation && error !is CancellationException) mutableState.update { it.copy(loading = false, error = error.message ?: "Dashboard loading failed") }
                }
        }
    }

    fun selectAsset(asset: DashboardAsset) = mutableState.update { it.copy(selectedAssetId = asset.id) }
    fun selectCategory(category: String?) = mutableState.update { it.copy(selectedCategory = category, selectedAssetId = null) }
    fun selectGoal(goalId: Long) = mutableState.update { it.copy(selectedGoalId = goalId) }

    fun createAsset(name: String, category: String, currency: String, value: String, date: String, description: String) = mutate {
        engine.createDashboardAsset(name, category, currency, value, date, description)
    }
    fun updateAsset(assetId: Long, name: String, category: String, currency: String, value: String, snapshotDate: String, description: String) = mutate {
        engine.updateDashboardAsset(assetId, name, category, currency, value, snapshotDate, description)
    }
    fun addAssetSnapshot(assetId: Long, value: String, date: String, note: String) = mutate {
        engine.addDashboardAssetSnapshot(assetId, value, date, note)
    }
    fun saveAssetSnapshots(updates: List<DashboardSnapshotUpdate>, date: String) = mutate {
        updates.filter { it.value.isNotBlank() }.forEach { update ->
            engine.addDashboardAssetSnapshot(update.assetId, update.value, date, update.note)
        }
    }
    fun setAssetActive(assetId: Long, active: Boolean) = mutate { engine.setDashboardAssetActive(assetId, active) }
    fun createGoal(title: String, target: String, currency: String, date: String?, description: String) = mutate {
        engine.createDashboardGoal(title, target, currency, date, description)
    }
    fun setGoalCompleted(goalId: Long, completed: Boolean) = mutate { engine.setDashboardGoalCompleted(goalId, completed) }
    fun deleteGoal(goalId: Long) = mutate { engine.deleteDashboardGoal(goalId) }

    private fun mutate(action: suspend () -> Any) {
        scope.launch {
            runCatching { action() }
                .onSuccess { mutableState.update { it.copy(notice = "Dashboard updated") }; refresh() }
                .onFailure { error -> mutableState.update { it.copy(error = error.message ?: "Dashboard update failed") } }
        }
    }
}
