package app.ledgera.settings

import app.ledgera.bridge.SettingsEngine
import app.ledgera.model.AuditFinding
import app.ledgera.model.AuditSummary
import app.ledgera.model.CreateWalletRequest
import app.ledgera.model.FullBackupResult
import app.ledgera.model.WalletSettingsItem
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class SettingsUiState(
    val loading: Boolean = false,
    val wallets: List<WalletSettingsItem> = emptyList(),
    val baseCurrency: String = "KZT",
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
) {
    private val mutableState = MutableStateFlow(SettingsUiState(loading = true))
    val state: StateFlow<SettingsUiState> = mutableState.asStateFlow()

    fun refresh() {
        mutableState.value = mutableState.value.copy(loading = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val baseCurrency = engine.baseCurrency()
                val wallets = engine.listWalletsForSettings()
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    wallets = wallets,
                    baseCurrency = baseCurrency,
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
                    notice = "Backup restored: ${result.importedRows} rows, ${result.budgetRows} budgets",
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
                        notice = "Backup exported: ${result.importedRows} rows, ${result.budgetRows} budgets",
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
                val baseCurrency = engine.baseCurrency()
                val wallets = engine.listWalletsForSettings()
                mutableState.value = SettingsUiState(
                    loading = false,
                    wallets = wallets,
                    baseCurrency = baseCurrency,
                    notice = "Wallet created (id=${created.id})",
                )
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
                val baseCurrency = engine.baseCurrency()
                val wallets = engine.listWalletsForSettings()
                mutableState.value = SettingsUiState(
                    loading = false,
                    wallets = wallets,
                    baseCurrency = baseCurrency,
                    notice = walletDeleteNotice(result.walletId, result.action),
                )
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
