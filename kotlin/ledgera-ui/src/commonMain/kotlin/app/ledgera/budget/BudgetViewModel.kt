package app.ledgera.budget

import app.ledgera.bridge.BudgetEngine
import app.ledgera.model.BudgetItem
import app.ledgera.model.BudgetResultItem
import app.ledgera.model.CreateBudgetRequest
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
import kotlinx.coroutines.launch

data class BudgetDraft(
    val scopeType: String = "category",
    val scopeValue: String = "",
    val startDate: String = "",
    val endDate: String = "",
    val limitBase: String = "",
    val includeMandatory: Boolean = false,
)

data class BudgetUiState(
    val loading: Boolean = false,
    val budgets: List<BudgetItem> = emptyList(),
    val results: List<BudgetResultItem> = emptyList(),
    val suggestions: List<String> = emptyList(),
    val selectedBudgetId: Long? = null,
    val createDraft: BudgetDraft? = null,
    val editLimitBudgetId: Long? = null,
    val editLimit: String = "",
    val deleteBudgetId: Long? = null,
    val error: String? = null,
    val notice: String? = null,
)

class BudgetViewModel(
    private val engine: BudgetEngine,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
) {
    private val mutableState = MutableStateFlow(BudgetUiState(loading = true))
    val state: StateFlow<BudgetUiState> = mutableState.asStateFlow()
    private var suggestionsJob: Job? = null
    private var suggestionsGeneration = 0L

    init { refresh(reloadSuggestions = true) }

    fun refresh(reloadSuggestions: Boolean = false) {
        val previous = mutableState.value
        mutableState.value = previous.copy(loading = true, error = null)
        scope.launch {
            runCatching {
                val suggestionScopeType = previous.createDraft?.scopeType ?: "category"
                val suggestions = if (reloadSuggestions || previous.suggestions.isEmpty()) {
                    engine.budgetScopeSuggestions(suggestionScopeType)
                } else {
                    previous.suggestions
                }
                Triple(engine.listBudgets(), engine.listBudgetResults(), suggestions)
            }.onSuccess { (budgets, results, suggestions) ->
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    budgets = budgets,
                    results = results,
                    suggestions = suggestions,
                    selectedBudgetId = previous.selectedBudgetId?.takeIf { id -> budgets.any { it.id == id } },
                    createDraft = previous.createDraft,
                    editLimitBudgetId = previous.editLimitBudgetId?.takeIf { id -> budgets.any { it.id == id } },
                    deleteBudgetId = previous.deleteBudgetId?.takeIf { id -> budgets.any { it.id == id } },
                )
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(loading = false, error = error.message ?: "Failed to load budgets")
            }
        }
    }

    fun clearFeedback() { mutableState.value = mutableState.value.copy(error = null, notice = null) }
    fun selectBudget(id: Long) { mutableState.value = mutableState.value.copy(selectedBudgetId = id, error = null) }
    fun openCreateDialog() {
        val shouldLoadSuggestions = mutableState.value.suggestions.isEmpty()
        mutableState.value = mutableState.value.copy(createDraft = BudgetDraft(), error = null, notice = null)
        if (shouldLoadSuggestions) loadSuggestions("category")
    }

    fun closeCreateDialog() {
        cancelSuggestionsJob()
        mutableState.value = mutableState.value.copy(createDraft = null, error = null)
    }

    fun updateDraft(draft: BudgetDraft) {
        val previousScopeType = mutableState.value.createDraft?.scopeType
        mutableState.value = mutableState.value.copy(createDraft = draft, error = null, notice = null)
        if (draft.scopeType != previousScopeType) {
            loadSuggestions(draft.scopeType)
        }
    }

    private fun loadSuggestions(scopeType: String) {
        cancelSuggestionsJob()
        val generation = ++suggestionsGeneration
        mutableState.value = mutableState.value.copy(suggestions = emptyList())
        suggestionsJob = scope.launch {
            try {
                val suggestions = engine.budgetScopeSuggestions(scopeType)
                if (generation == suggestionsGeneration && mutableState.value.createDraft?.scopeType == scopeType) {
                    mutableState.value = mutableState.value.copy(suggestions = suggestions)
                }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Throwable) {
                if (generation == suggestionsGeneration && mutableState.value.createDraft?.scopeType == scopeType) {
                    mutableState.value = mutableState.value.copy(
                        error = error.message ?: "Failed to load budget suggestions",
                        suggestions = emptyList(),
                    )
                }
            }
        }
    }

    private fun cancelSuggestionsJob() {
        suggestionsGeneration += 1
        suggestionsJob?.cancel()
        suggestionsJob = null
    }

    fun createBudget() {
        val draft = mutableState.value.createDraft ?: return
        validateDraft(draft)?.let { return fail(it) }
        mutableState.value = mutableState.value.copy(loading = true, error = null)
        scope.launch {
            runCatching {
                engine.createBudget(
                    CreateBudgetRequest(
                        category = draft.scopeValue.trim(),
                        scopeType = draft.scopeType,
                        scopeValue = draft.scopeValue.trim(),
                        startDate = DateValidation.formatDmyToYmd(draft.startDate)!!,
                        endDate = DateValidation.formatDmyToYmd(draft.endDate)!!,
                        limitBase = draft.limitBase.trim(),
                        includeMandatory = draft.includeMandatory,
                    )
                )
            }.onSuccess {
                mutableState.value = mutableState.value.copy(createDraft = null, loading = false, notice = "Budget created")
                refresh()
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(loading = false, error = error.message ?: "Failed to create budget")
            }
        }
    }

    fun openEditLimit() {
        val selected = mutableState.value.budgets.firstOrNull { it.id == mutableState.value.selectedBudgetId } ?: return fail("Select a budget first")
        mutableState.value = mutableState.value.copy(editLimitBudgetId = selected.id, editLimit = selected.limitBase, error = null)
    }
    fun closeEditLimit() { mutableState.value = mutableState.value.copy(editLimitBudgetId = null, error = null) }
    fun updateEditLimit(value: String) { mutableState.value = mutableState.value.copy(editLimit = value, error = null) }
    fun saveEditLimit() {
        val state = mutableState.value
        val id = state.editLimitBudgetId ?: return
        if (state.editLimit.toDoubleOrNull()?.let { it > 0.0 } != true) return fail("Budget limit must be positive")
        mutableState.value = state.copy(loading = true, error = null)
        scope.launch {
            runCatching { engine.updateBudgetLimit(id, state.editLimit.trim()) }
                .onSuccess { mutableState.value = mutableState.value.copy(editLimitBudgetId = null, loading = false, notice = "Budget limit updated"); refresh() }
                .onFailure { error -> mutableState.value = mutableState.value.copy(loading = false, error = error.message ?: "Failed to update budget") }
        }
    }

    fun requestDelete() {
        if (mutableState.value.budgets.none { it.id == mutableState.value.selectedBudgetId }) return fail("Select a budget first")
        mutableState.value = mutableState.value.copy(deleteBudgetId = mutableState.value.selectedBudgetId, error = null)
    }
    fun closeDelete() { mutableState.value = mutableState.value.copy(deleteBudgetId = null, error = null) }
    fun deleteBudget() {
        val id = mutableState.value.deleteBudgetId ?: return
        mutableState.value = mutableState.value.copy(loading = true, error = null)
        scope.launch {
            runCatching { engine.deleteBudget(id) }
                .onSuccess { mutableState.value = mutableState.value.copy(deleteBudgetId = null, selectedBudgetId = null, loading = false, notice = "Budget deleted"); refresh() }
                .onFailure { error -> mutableState.value = mutableState.value.copy(loading = false, error = error.message ?: "Failed to delete budget") }
        }
    }

    private fun validateDraft(draft: BudgetDraft): String? {
        if (draft.scopeValue.trim().isEmpty()) return "Category or tag is required"
        val start = DateValidation.parseDmyStrict(draft.startDate)
        val end = DateValidation.parseDmyStrict(draft.endDate)
        if (start == null || end == null) return "Dates must use valid DD.MM.YYYY values"
        if (start > end) return "Start date must be before end date"
        if (draft.limitBase.toDoubleOrNull()?.let { it > 0.0 } != true) return "Budget limit must be positive"
        return null
    }

    private fun fail(message: String) { mutableState.value = mutableState.value.copy(error = message, notice = null) }
}
