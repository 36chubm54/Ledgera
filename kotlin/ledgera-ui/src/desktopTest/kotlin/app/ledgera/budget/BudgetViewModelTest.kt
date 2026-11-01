package app.ledgera.budget

import app.ledgera.bridge.BudgetEngine
import app.ledgera.model.BudgetItem
import app.ledgera.model.BudgetResultItem
import app.ledgera.model.CreateBudgetRequest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers

class BudgetViewModelTest {
    @Test
    fun nonActiveBudgetUsesLifecycleStateForVisualStatus() {
        assertEquals("future", budgetVisualState("future", "on_track"))
        assertEquals("expired", budgetVisualState("expired", "on_track"))
        assertEquals("overpace", budgetVisualState("active", "overpace"))
    }

    @Test
    fun futureBudgetDateIsAcceptedAndConvertedAtEngineBoundary() {
        val engine = FakeBudgetEngine()
        val viewModel = BudgetViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.openCreateDialog()
        viewModel.updateDraft(
            BudgetDraft(
                scopeType = "category",
                scopeValue = "Travel",
                startDate = "31.12.2026",
                endDate = "31.12.2026",
                limitBase = "1000",
            )
        )
        viewModel.createBudget()

        assertEquals("2026-12-31", engine.created?.startDate)
        assertEquals("2026-12-31", engine.created?.endDate)
        assertEquals("Budget created", viewModel.state.value.notice)
    }

    @Test
    fun invalidLimitDoesNotCallEngine() {
        val engine = FakeBudgetEngine()
        val viewModel = BudgetViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.openCreateDialog()
        viewModel.updateDraft(BudgetDraft(scopeValue = "Food", startDate = "01.01.2026", endDate = "31.01.2026", limitBase = "0"))
        viewModel.createBudget()

        assertEquals("Budget limit must be positive", viewModel.state.value.error)
        assertEquals(null, engine.created)
    }

    @Test
    fun typingWithinOneScopeDoesNotReloadSuggestions() {
        val engine = FakeBudgetEngine()
        val viewModel = BudgetViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.openCreateDialog()
        val initialCalls = engine.suggestionCalls
        viewModel.updateDraft(BudgetDraft(scopeValue = "F"))
        viewModel.updateDraft(BudgetDraft(scopeValue = "Fo"))

        assertEquals(initialCalls, engine.suggestionCalls)
    }
}

private class FakeBudgetEngine : BudgetEngine {
    var created: CreateBudgetRequest? = null
    var suggestionCalls: Int = 0

    override suspend fun listBudgets(): List<BudgetItem> = emptyList()
    override suspend fun listBudgetResults(today: String?): List<BudgetResultItem> = emptyList()
    override suspend fun budgetScopeSuggestions(scopeType: String): List<String> {
        suggestionCalls += 1
        return listOf("Food", "Travel")
    }
    override suspend fun createBudget(request: CreateBudgetRequest): BudgetItem {
        created = request
        return BudgetItem(1, request.category, request.scopeType, request.scopeValue, request.startDate, request.endDate, request.limitBase, 100000, request.includeMandatory)
    }
    override suspend fun updateBudgetLimit(budgetId: Long, limitBase: String): BudgetItem = error("unused")
    override suspend fun deleteBudget(budgetId: Long): Boolean = true
}
