package app.ledgera.settings

import app.ledgera.bridge.SettingsEngine
import app.ledgera.model.CurrencyRefreshRequest
import app.ledgera.model.CurrencyRefreshResult
import kotlinx.coroutines.CancellationException
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
    private val onSuccess: suspend (CurrencyRefreshResult) -> Unit = {},
    private val onFailure: suspend (Throwable) -> Unit = {},
) {
    private val refreshMutex = Mutex()
    private var scheduledJob: Job? = null

    fun start(autoUpdate: Boolean, intervalMinutes: Int) {
        stop()
        if (!autoUpdate || intervalMinutes <= 0) return
        scheduledJob = scope.launch {
            while (isActive) {
                try {
                    refreshNow()
                } catch (error: CancellationException) {
                    throw error
                } catch (_: Throwable) {
                    // The failure is surfaced through onFailure; the scheduler stays alive.
                }
                delay(intervalMinutes.toLong() * 60_000L)
            }
        }
    }

    suspend fun refreshNow(): CurrencyRefreshResult {
        return try {
            val result = refreshMutex.withLock {
                engine.refreshCurrencyRates(requestFactory())
            }
            onSuccess(result)
            result
        } catch (error: CancellationException) {
            throw error
        } catch (error: Throwable) {
            onFailure(error)
            throw error
        }
    }

    fun stop() {
        scheduledJob?.cancel()
        scheduledJob = null
    }
}
