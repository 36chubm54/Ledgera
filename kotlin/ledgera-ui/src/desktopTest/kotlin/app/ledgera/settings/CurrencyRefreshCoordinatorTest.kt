package app.ledgera.settings

import app.ledgera.bridge.SettingsEngine
import app.ledgera.model.AuditFinding
import app.ledgera.model.CreateWalletRequest
import app.ledgera.model.CurrencyRefreshRequest
import app.ledgera.model.CurrencyRefreshResult
import app.ledgera.model.WalletDeleteResult
import app.ledgera.model.WalletSettingsItem
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking

class CurrencyRefreshCoordinatorTest {
    @Test
    fun concurrentRefreshesAreSerialized() = runBlocking {
        val engine = CountingSettingsEngine()
        val coordinator = CurrencyRefreshCoordinator(
            engine = engine,
            scope = this,
            requestFactory = { request() },
        )

        val first = async(Dispatchers.Default) { coordinator.refreshNow() }
        val second = async(Dispatchers.Default) { coordinator.refreshNow() }

        first.await()
        second.await()

        assertEquals(1, engine.maxConcurrent)
        assertEquals(2, engine.refreshCalls)
    }

    @Test
    fun refreshFailureIsForwardedToCallback() = runBlocking {
        val expected = IllegalStateException("provider unavailable")
        var received: Throwable? = null
        val coordinator = CurrencyRefreshCoordinator(
            engine = CountingSettingsEngine(refreshError = expected),
            scope = this,
            requestFactory = { request() },
            onFailure = { received = it },
        )

        runCatching { coordinator.refreshNow() }

        assertEquals(expected, received)
    }
}

private fun request() = CurrencyRefreshRequest(
    refreshId = "test-refresh",
    backend = "rust",
    baseCurrency = "KZT",
    primaryProvider = "static",
    fallbackProvider = "cache",
    effectiveDate = "2026-10-19",
    fetchedAt = "2026-10-19",
)

private class CountingSettingsEngine(
    private val refreshError: Throwable? = null,
) : SettingsEngine {
    var refreshCalls = 0
    var maxConcurrent = 0
    private var concurrent = 0

    override suspend fun baseCurrency(): String = "KZT"

    override suspend fun refreshCurrencyRates(request: CurrencyRefreshRequest): CurrencyRefreshResult {
        refreshError?.let { throw it }
        synchronized(this) {
            refreshCalls += 1
            concurrent += 1
            maxConcurrent = maxOf(maxConcurrent, concurrent)
        }
        delay(15)
        synchronized(this) { concurrent -= 1 }
        return CurrencyRefreshResult(
            refreshId = request.refreshId,
            status = "success",
            selectedProvider = "static",
            ratesCount = 1,
            effectiveDate = request.effectiveDate,
            fetchedAt = request.fetchedAt,
            fallbackChain = "static,cache",
            diagnostic = "",
            stale = false,
        )
    }

    override suspend fun listWalletsForSettings(): List<WalletSettingsItem> = emptyList()

    override suspend fun createWallet(request: CreateWalletRequest): WalletSettingsItem = error("unused")

    override suspend fun deleteWallet(walletId: Long): WalletDeleteResult = error("unused")

    override suspend fun runAudit(): List<AuditFinding> = emptyList()
}
