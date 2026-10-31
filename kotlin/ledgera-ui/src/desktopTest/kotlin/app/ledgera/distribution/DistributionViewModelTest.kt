package app.ledgera.distribution

import app.ledgera.bridge.DistributionEngine
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers

class DistributionViewModelTest {
    @Test
    fun closedMonthsAreAutoFrozenOnlyOncePerViewModelLifetime() {
        val engine = FakeDistributionEngine()
        val viewModel = DistributionViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        assertEquals(1, engine.freezeCalls)

        viewModel.refresh()

        assertEquals(1, engine.freezeCalls)
        viewModel.close()
    }
}

private class FakeDistributionEngine : DistributionEngine {
    var freezeCalls = 0

    override suspend fun freezeClosedDistributionMonths(cutoffMonth: String): List<String> {
        freezeCalls += 1
        return emptyList()
    }
}
