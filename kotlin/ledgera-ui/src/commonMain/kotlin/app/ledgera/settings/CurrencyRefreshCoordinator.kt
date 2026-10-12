package app.ledgera.settings

import app.ledgera.bridge.SettingsEngine
import app.ledgera.model.CurrencyRefreshRequest
import app.ledgera.model.CurrencyRefreshResult
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Owns automatic refresh lifetime and guarantees that only one refresh is active. */
class CurrencyRefreshCoordinator(
    private val engine: SettingsEngine,
    private val scope: CoroutineScope,
    private val requestFactory: suspend () -> CurrencyRefreshRequest,
) {
    private val refreshMutex = Mutex()
    private var scheduledJob: Job? = null

    fun start(autoUpdate: Boolean, intervalMinutes: Int) {
        stop()
        if (!autoUpdate || intervalMinutes <= 0) return
        scheduledJob = scope.launch {
            while (isActive) {
                refreshNow()
                delay(intervalMinutes.toLong() * 60_000L)
            }
        }
    }

    suspend fun refreshNow(): CurrencyRefreshResult? = refreshMutex.withLock {
        runCatching { engine.refreshCurrencyRates(requestFactory()) }.getOrNull()
    }

    fun stop() {
        scheduledJob?.cancel()
        scheduledJob = null
    }
}
