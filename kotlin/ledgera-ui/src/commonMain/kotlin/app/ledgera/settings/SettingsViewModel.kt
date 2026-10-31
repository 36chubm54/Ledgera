package app.ledgera.settings

import app.ledgera.bridge.SettingsEngine
import app.ledgera.model.AuditFinding
import app.ledgera.model.AuditSummary
import app.ledgera.model.CreateWalletRequest
import app.ledgera.model.UpdateWalletProfileRequest
import app.ledgera.model.FullBackupResult
import app.ledgera.model.WalletSettingsItem
import app.ledgera.model.CurrencyRate
import app.ledgera.model.CurrencyProviderStatus
import app.ledgera.model.CurrencyProviderDefinition
import app.ledgera.model.CurrencyProviderDefinitionRequest
import app.ledgera.model.CurrencyProviderSetting
import app.ledgera.model.CurrencyProviderSettingRequest
import app.ledgera.model.CurrencyProviderTestRequest
import app.ledgera.model.CurrencyProviderTestResult
import app.ledgera.model.CurrencyRefreshStatus
import app.ledgera.model.CurrencyRefreshRequest
import app.ledgera.model.CurrencyRefreshResult
import app.ledgera.validation.DateValidation
import app.ledgera.validation.currentLedgerDate
import app.ledgera.validation.currentUtcTimestamp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlin.random.Random

data class SettingsUiState(
    val loading: Boolean = false,
    val wallets: List<WalletSettingsItem> = emptyList(),
    val walletColorPalette: List<String> = emptyList(),
    val walletIconCatalog: List<String> = listOf("wallet", "cash", "card", "bank", "savings", "investment"),
    val baseCurrency: String = "KZT",
    val supportedCurrencies: List<String> = listOf("KZT"),
    val currencyRates: List<CurrencyRate> = emptyList(),
    val currencyRefreshStatus: CurrencyRefreshStatus? = null,
    val currencyProviderStatuses: List<CurrencyProviderStatus> = emptyList(),
    val currencyProviderDefinitions: List<CurrencyProviderDefinition> = emptyList(),
    val currencyProviderSettings: List<CurrencyProviderSetting> = emptyList(),
    val currencyProviderCredentialStatuses: Map<String, String> = emptyMap(),
    val exchangeRateCredentialStatus: String = "Missing",
    val auditRunning: Boolean = false,
    val auditFindings: List<AuditFinding> = emptyList(),
    val auditSummary: AuditSummary? = null,
    val error: String? = null,
    val notice: String? = null,
    val backupPreview: FullBackupResult? = null,
    val backupPath: String? = null,
    val restoreVersion: Long = 0,
)

class SettingsViewModel(
    private val engine: SettingsEngine,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
    private val onCurrencyRefreshSuccess: suspend () -> Unit = {},
    private val onWalletProfileChanged: suspend () -> Unit = {},
) {
    private val mutableState = MutableStateFlow(SettingsUiState(loading = true))
    val state: StateFlow<SettingsUiState> = mutableState.asStateFlow()
    private val currencyRefreshCoordinator = CurrencyRefreshCoordinator(
        engine = engine,
        scope = scope,
        requestFactory = ::buildCurrencyRefreshRequest,
        onSuccess = { result -> handleCurrencyRefreshSuccess(result) },
        onFailure = ::handleCurrencyRefreshFailure,
    )

    fun refresh(preserveNotice: String? = null) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = preserveNotice)
        launchSafely {
            runCatching {
                val baseCurrency = engine.baseCurrency()
                val wallets = engine.listWalletsForSettings()
                val walletColorPalette = runCatching { engine.walletColorPalette() }.getOrDefault(emptyList())
                val walletIconCatalog = runCatching { engine.walletIconCatalog() }.getOrDefault(emptyList())
                val currencies = engine.supportedCurrencies()
                val rates = engine.currencyRates()
                val refreshStatus = runCatching { engine.currencyRefreshStatus() }.getOrNull()
                val providerStatuses = runCatching { engine.currencyProviderStatuses() }.getOrDefault(emptyList())
                val providerDefinitions = runCatching { engine.currencyProviderDefinitions() }.getOrDefault(emptyList())
                val providerSettings = runCatching { engine.currencyProviderSettings() }.getOrDefault(emptyList())
                val exchangeRateCredentialStatus = runCatching {
                    engine.currencyProviderCredentialStatus("exchange_rate")
                }.getOrDefault("Missing")
                val credentialStatuses = providerDefinitions
                    .filter { it.authMode != "none" }
                    .associate { definition ->
                        definition.providerId to runCatching {
                            engine.currencyProviderCredentialStatus(definition.providerId)
                        }.getOrDefault("Missing")
                    }
                    .toMutableMap()
                    .apply { put("exchange_rate", exchangeRateCredentialStatus) }
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    wallets = wallets,
                    walletColorPalette = walletColorPalette,
                    walletIconCatalog = walletIconCatalog.ifEmpty {
                        listOf("wallet", "cash", "card", "bank", "savings", "investment")
                    },
                    baseCurrency = baseCurrency,
                    supportedCurrencies = currencies.ifEmpty { listOf(baseCurrency) },
                    currencyRates = rates,
                    currencyRefreshStatus = refreshStatus,
                    currencyProviderStatuses = providerStatuses,
                    currencyProviderDefinitions = providerDefinitions,
                    currencyProviderSettings = providerSettings,
                    currencyProviderCredentialStatuses = credentialStatuses,
                    exchangeRateCredentialStatus = exchangeRateCredentialStatus,
                )
            }.onFailure(::showError)
        }
    }

    fun clearFeedback() {
        mutableState.value = mutableState.value.copy(error = null, notice = null)
    }

    fun clearNotice() {
        mutableState.value = mutableState.value.copy(notice = null)
    }

    fun startCurrencyRefresh(autoUpdate: Boolean, intervalMinutes: Int) {
        currencyRefreshCoordinator.start(autoUpdate, intervalMinutes)
    }

    fun stopCurrencyRefresh() {
        currencyRefreshCoordinator.stop()
    }

    fun refreshCurrencyRates() {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            currencyRefreshCoordinator.refreshNow()
        }
    }

    fun setBaseCurrency(currency: String) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.setBaseCurrency(currency) }
                .onSuccess { refresh() }
                .onFailure(::showError)
        }
    }

    fun saveCurrencyRate(baseCurrency: String, currency: String, rate: String, effectiveDate: String, source: String) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.upsertCurrencyRate(baseCurrency, currency, rate, effectiveDate, source) }
                .onSuccess { refresh("Currency rate saved") }
                .onFailure(::showError)
        }
    }

    fun deleteCurrencyRate(rateId: Long) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.deleteCurrencyRate(rateId) }
                .onSuccess { refresh("Currency rate deleted") }
                .onFailure(::showError)
        }
    }

    fun saveCurrencyProvider(request: CurrencyProviderDefinitionRequest) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.upsertCurrencyProviderDefinition(request) }
                .onSuccess { refresh("Provider saved; test connection to activate it") }
                .onFailure(::showError)
        }
    }

    fun deleteCurrencyProvider(providerId: String) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.deleteCurrencyProviderDefinition(providerId) }
                .onSuccess { refresh("Provider deleted") }
                .onFailure(::showError)
        }
    }

    fun setCurrencyProviderMode(request: CurrencyProviderSettingRequest) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.upsertCurrencyProviderSetting(request) }
                .onSuccess { refresh("Provider mode updated") }
                .onFailure(::showError)
        }
    }

    fun testCurrencyProvider(request: CurrencyProviderTestRequest) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            val resolvedRequest = if (request.apiKey.isBlank()) {
                request.copy(apiKey = engine.resolveCurrencyProviderCredential(request.providerId))
            } else {
                request
            }
            runCatching { engine.testCurrencyProvider(resolvedRequest) }
                .onSuccess { result ->
                    mutableState.value = mutableState.value.copy(
                        loading = false,
                        error = result.diagnostic.ifBlank { null },
                        notice = if (result.activated) "Provider test succeeded" else "Provider test failed",
                    )
                    refresh(mutableState.value.notice)
                }
                .onFailure(::showError)
        }
    }

    fun saveCurrencyProviderCredential(providerId: String, secret: String) {
        if (secret.isBlank()) {
            showError(IllegalArgumentException("API key is required"))
            return
        }
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.setCurrencyProviderCredential(providerId, secret.trim()) }
                .onSuccess { refresh("Credential saved") }
                .onFailure(::showError)
        }
    }

    fun previewBackup(path: String?) {
        val normalized = path?.trim().orEmpty()
        if (normalized.isEmpty()) return showError(IllegalArgumentException("Backup file is required"))
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.previewFullBackup(normalized) }
                .onSuccess { result ->
                    mutableState.value = mutableState.value.copy(
                        loading = false,
                        backupPreview = result,
                        backupPath = normalized,
                    )
                }.onFailure(::showError)
        }
    }

    fun cancelBackupPreview() {
        mutableState.value = mutableState.value.copy(backupPreview = null, backupPath = null, error = null)
    }

    fun restoreBackup() {
        val path = mutableState.value.backupPath ?: return showError(IllegalArgumentException("Backup file is required"))
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val result = engine.importFullBackup(path)
                val baseCurrency = engine.baseCurrency()
                val wallets = engine.listWalletsForSettings()
                result to (baseCurrency to wallets)
            }.onSuccess { (result, data) ->
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    wallets = data.second,
                    baseCurrency = data.first,
                    backupPreview = null,
                    backupPath = null,
                    restoreVersion = mutableState.value.restoreVersion + 1,
                        notice = "Backup restored: ${result.importedRows} rows, ${result.assetRows} assets, ${result.goalRows} goals, ${result.distributionRows} Distribution entries",
                )
            }.onFailure(::showError)
        }
    }

    fun exportBackup(path: String?) {
        val normalized = path?.trim().orEmpty()
        if (normalized.isEmpty()) return showError(IllegalArgumentException("Backup file is required"))
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching { engine.exportFullBackup(normalized) }
                .onSuccess { result ->
                    mutableState.value = mutableState.value.copy(
                        loading = false,
                        notice = "Backup exported: ${result.importedRows} rows, ${result.assetRows} assets, ${result.goalRows} goals, ${result.distributionRows} Distribution entries",
                    )
                }.onFailure(::showError)
        }
    }

    fun createWallet(request: CreateWalletRequest) {
        val validationError = SettingsValidation.validateWalletFields(
            name = request.name,
            currency = request.currency,
            initialBalance = request.initialBalance,
            baseCurrency = mutableState.value.baseCurrency,
        )
        if (validationError != null) {
            mutableState.value = mutableState.value.copy(error = validationError, notice = null)
            return
        }
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val created = engine.createWallet(request.copy(initialBalance = request.initialBalance.ifBlank { "0" }))
                refresh("Wallet created (id=${created.id})")
                onWalletProfileChanged()
            }.onFailure(::showError)
        }
    }

    fun updateWalletProfile(request: UpdateWalletProfileRequest) {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val updated = engine.updateWalletProfile(request)
                refresh("Wallet profile saved (id=${updated.id})")
                onWalletProfileChanged()
            }.onFailure(::showError)
        }
    }

    fun deleteWallet(walletId: Long) {
        if (walletId <= 0) {
            mutableState.value = mutableState.value.copy(error = "Wallet is required", notice = null)
            return
        }
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val result = engine.deleteWallet(walletId)
                refresh(walletDeleteNotice(result.walletId, result.action))
            }.onFailure(::showError)
        }
    }

    fun runAudit() {
        mutableState.value = mutableState.value.copy(auditRunning = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val findings = engine.runAudit()
                val summary = findings.toAuditSummary()
                mutableState.value = mutableState.value.copy(
                    auditRunning = false,
                    auditFindings = findings,
                    auditSummary = summary,
                    error = null,
                    notice = "Audit completed: ${summary.errors} errors, ${summary.warnings} warnings",
                )
            }.onFailure(::showError)
        }
    }

    private fun showError(error: Throwable) {
        mutableState.value = mutableState.value.copy(
            loading = false,
            auditRunning = false,
            error = error.message ?: error::class.simpleName ?: "Unknown error",
            notice = null,
        )
    }

    private suspend fun buildCurrencyRefreshRequest(): CurrencyRefreshRequest {
        val date = DateValidation.formatYmd(currentLedgerDate())
        val providers = runCatching { engine.currencyProviderStatuses() }.getOrDefault(emptyList())
        val settings = runCatching { engine.currencyProviderSettings() }.getOrDefault(emptyList())
        val primary = settings.firstOrNull { it.primaryEnabled || it.mode == "primary" }?.providerId
            ?: providers.firstOrNull { it.selected }?.name
            ?: "nbk"
        val fallback = settings.firstOrNull {
            it.providerId != primary && (it.fallbackEnabled || it.mode == "fallback")
        }?.providerId
            ?: providers.firstOrNull { it.name == "exchange_rate" && it.name != primary }?.name
            ?: "static"
        val credentialProvider = listOf(primary, fallback).firstOrNull { provider ->
            provider == "exchange_rate" || provider.startsWith("custom:")
        }
        val apiKey = if (credentialProvider.isNullOrBlank()) {
            ""
        } else {
            runCatching { engine.resolveCurrencyProviderCredential(credentialProvider) }.getOrDefault("")
        }
        return CurrencyRefreshRequest(
            refreshId = "desktop-${date}-${Random.nextLong().toString(16)}",
            backend = "rust",
            baseCurrency = engine.baseCurrency(),
            primaryProvider = primary,
            fallbackProvider = fallback,
            effectiveDate = date,
            fetchedAt = currentUtcTimestamp(),
            apiKey = apiKey,
        )
    }

    private suspend fun handleCurrencyRefreshSuccess(result: CurrencyRefreshResult) {
        mutableState.value = mutableState.value.copy(
            loading = false,
            notice = "Currency refresh completed: ${result.ratesCount} rates",
            error = result.diagnostic.ifBlank { null },
        )
        refresh(mutableState.value.notice)
        onCurrencyRefreshSuccess()
    }

    private suspend fun handleCurrencyRefreshFailure(error: Throwable) {
        showError(error)
    }

    private fun launchSafely(block: suspend () -> Unit) {
        try {
            scope.launch { block() }
        } catch (error: Throwable) {
            showError(error)
        }
    }

    private fun walletDeleteNotice(walletId: Long, action: String): String =
        when (action) {
            "hard_deleted" -> "Wallet deleted (id=$walletId)"
            "soft_deleted" -> "Wallet deactivated (id=$walletId)"
            else -> "Wallet updated (id=$walletId)"
        }
}

private fun List<AuditFinding>.toAuditSummary(): AuditSummary {
    val errors = count { it.severity.equals("error", ignoreCase = true) }
    val warnings = count { it.severity.equals("warning", ignoreCase = true) }
    val ok = count { it.severity.equals("ok", ignoreCase = true) }
    return AuditSummary(errors = errors, warnings = warnings, ok = ok, total = size)
}
