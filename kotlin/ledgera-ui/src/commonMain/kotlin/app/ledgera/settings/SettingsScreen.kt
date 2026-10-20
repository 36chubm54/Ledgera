package app.ledgera.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.ledgera.model.AuditFinding
import app.ledgera.model.AuditSummary
import app.ledgera.model.CreateWalletRequest
import app.ledgera.model.CurrencyRate
import app.ledgera.model.CurrencyProviderDefinition
import app.ledgera.model.CurrencyProviderDefinitionRequest
import app.ledgera.model.CurrencyProviderSettingRequest
import app.ledgera.model.CurrencyProviderTestRequest
import app.ledgera.model.WalletSettingsItem
import app.ledgera.ui.LedgerDateField
import app.ledgera.validation.CurrencyValidation
import app.ledgera.validation.DateValidation
import app.ledgera.validation.currentLedgerDate

interface SettingsFileActions {
    fun openBackupPath(): String?
    fun saveBackupPath(): String?
}

object NoSettingsFileActions : SettingsFileActions {
    override fun openBackupPath(): String? = null
    override fun saveBackupPath(): String? = null
}

@Composable
fun SettingsScreen(
    viewModel: SettingsViewModel,
    scrollState: androidx.compose.foundation.ScrollState,
    modifier: Modifier = Modifier,
    fileActions: SettingsFileActions = NoSettingsFileActions,
) {
    val state by viewModel.state.collectAsState()
    var showCreateWalletDialog by remember { mutableStateOf(false) }
    var showCurrencyRateDialog by remember { mutableStateOf(false) }
    var showCurrencyRateHistory by remember { mutableStateOf(false) }
    var editingCurrencyRate by remember { mutableStateOf<CurrencyRate?>(null) }
    var walletPendingDelete by remember { mutableStateOf<WalletSettingsItem?>(null) }
    var showAuditReport by remember { mutableStateOf(false) }
    var showProviderDialog by remember { mutableStateOf(false) }
    var editingProvider by remember { mutableStateOf<CurrencyProviderDefinition?>(null) }
    var showExchangeRateCredentialDialog by remember { mutableStateOf(false) }
    var credentialProvider by remember { mutableStateOf<CurrencyProviderDefinition?>(null) }

    LaunchedEffect(Unit) {
        viewModel.refresh()
    }
    LaunchedEffect(showCreateWalletDialog, state.notice) {
        if (showCreateWalletDialog && state.notice?.startsWith("Wallet created") == true) {
            showCreateWalletDialog = false
        }
    }
    LaunchedEffect(showCurrencyRateDialog, state.notice) {
        if (showCurrencyRateDialog && state.notice?.startsWith("Currency rate saved") == true) {
            showCurrencyRateDialog = false
            editingCurrencyRate = null
        }
    }
    LaunchedEffect(walletPendingDelete, state.notice) {
        if (
            walletPendingDelete != null &&
            (state.notice?.startsWith("Wallet deleted") == true ||
                state.notice?.startsWith("Wallet deactivated") == true)
        ) {
            walletPendingDelete = null
        }
    }
    LaunchedEffect(state.notice) {
        if (state.notice?.startsWith("Provider saved") == true) {
            showProviderDialog = false
            editingProvider = null
        }
        if (state.notice == "Credential saved") {
            showExchangeRateCredentialDialog = false
            credentialProvider = null
        }
    }

    Column(
        modifier = modifier.fillMaxSize().verticalScroll(scrollState).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Settings", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)

        WalletsSection(
            wallets = state.wallets,
            loading = state.loading,
            onAddWallet = {
                viewModel.clearFeedback()
                showCreateWalletDialog = true
            },
            onDeleteWallet = { wallet ->
                viewModel.clearFeedback()
                walletPendingDelete = wallet
            },
        )
        CurrencySection(
            baseCurrency = state.baseCurrency,
            currencies = state.supportedCurrencies,
            rates = state.currencyRates,
            refreshStatus = state.currencyRefreshStatus,
            providerStatuses = state.currencyProviderStatuses,
            loading = state.loading,
            error = state.error,
            onAddRate = { viewModel.clearFeedback(); editingCurrencyRate = null; showCurrencyRateDialog = true },
            onUpdateRate = { rate ->
                viewModel.clearFeedback()
                editingCurrencyRate = rate
                showCurrencyRateDialog = true
            },
            onDeleteRate = viewModel::deleteCurrencyRate,
            onSetBase = viewModel::setBaseCurrency,
            onRefresh = viewModel::refreshCurrencyRates,
            onShowHistory = { showCurrencyRateHistory = true },
        )
        OnlineProvidersSection(
            definitions = state.currencyProviderDefinitions,
            statuses = state.currencyProviderStatuses,
            settings = state.currencyProviderSettings,
            credentialStatuses = state.currencyProviderCredentialStatuses,
            exchangeRateCredentialStatus = state.exchangeRateCredentialStatus,
            loading = state.loading,
            onAdd = { viewModel.clearFeedback(); editingProvider = null; showProviderDialog = true },
            onEdit = { provider -> viewModel.clearFeedback(); editingProvider = provider; showProviderDialog = true },
            onDelete = viewModel::deleteCurrencyProvider,
            onConfigureExchangeRate = { viewModel.clearFeedback(); showExchangeRateCredentialDialog = true },
            onConfigureCredential = { provider ->
                viewModel.clearFeedback()
                credentialProvider = provider
            },
            onSetMode = { provider, mode ->
                viewModel.setCurrencyProviderMode(
                    CurrencyProviderSettingRequest(
                        providerId = provider.providerId,
                        mode = mode,
                        primaryEnabled = mode == "primary",
                        fallbackEnabled = mode == "fallback",
                        credentialStatus = state.currencyProviderCredentialStatuses[provider.providerId]
                            .toProviderCredentialStatus(),
                    )
                )
            },
            onTest = { provider ->
                viewModel.testCurrencyProvider(
                    CurrencyProviderTestRequest(
                        providerId = provider.providerId,
                        baseCurrency = state.baseCurrency,
                        effectiveDate = currentSettingsDate(),
                        testedAt = currentSettingsDate(),
                    )
                )
            },
        )
        AuditSection(
            running = state.auditRunning,
            summary = state.auditSummary,
            hasFindings = state.auditFindings.isNotEmpty(),
            onRunAudit = {
                viewModel.clearFeedback()
                viewModel.runAudit()
            },
            onViewReport = { showAuditReport = true },
        )
        BackupSection(
            loading = state.loading,
            onRestore = { viewModel.previewBackup(fileActions.openBackupPath()) },
            onExport = { viewModel.exportBackup(fileActions.saveBackupPath()) },
        )
    }

    if (showCreateWalletDialog) {
        CreateWalletDialog(
            baseCurrency = state.baseCurrency,
            supportedCurrencies = state.supportedCurrencies,
            engineError = state.error,
            submitting = state.loading,
            onSubmit = viewModel::createWallet,
            onCancel = { showCreateWalletDialog = false },
        )
    }
    if (showCurrencyRateDialog) {
        CurrencyRateDialog(
            baseCurrency = state.baseCurrency,
            existingRate = editingCurrencyRate,
            existingRates = state.currencyRates,
            error = state.error,
            submitting = state.loading,
            onSave = { base, currency, rate, date, source -> viewModel.saveCurrencyRate(base, currency, rate, date, source) },
            onCancel = { showCurrencyRateDialog = false; editingCurrencyRate = null },
        )
    }
    if (showCurrencyRateHistory) {
        CurrencyRateHistoryDialog(
            rates = state.currencyRates,
            loading = state.loading,
            error = state.error,
            onUpdate = { rate ->
                viewModel.clearFeedback()
                editingCurrencyRate = rate
                showCurrencyRateHistory = false
                showCurrencyRateDialog = true
            },
            onDelete = viewModel::deleteCurrencyRate,
            onClose = { showCurrencyRateHistory = false },
        )
    }
    if (showProviderDialog) {
        CustomProviderDialog(
            baseCurrency = state.baseCurrency,
            existingProvider = editingProvider,
            loading = state.loading,
            error = state.error,
            onSave = { request -> viewModel.saveCurrencyProvider(request) },
            onCancel = { showProviderDialog = false; editingProvider = null },
        )
    }
    if (showExchangeRateCredentialDialog) {
        ExchangeRateCredentialDialog(
            status = state.exchangeRateCredentialStatus,
            loading = state.loading,
            error = state.error,
            onSave = { secret ->
                viewModel.saveCurrencyProviderCredential("exchange_rate", secret)
            },
            onCancel = { showExchangeRateCredentialDialog = false },
        )
    }
    credentialProvider?.let { provider ->
        ExchangeRateCredentialDialog(
            status = state.currencyProviderCredentialStatuses[provider.providerId] ?: "Missing",
            loading = state.loading,
            error = state.error,
            title = "${provider.displayName} API key",
            onSave = { secret -> viewModel.saveCurrencyProviderCredential(provider.providerId, secret) },
            onCancel = { credentialProvider = null },
        )
    }
    walletPendingDelete?.let { wallet ->
        DeleteWalletConfirmDialog(
            wallet = wallet,
            engineError = state.error,
            submitting = state.loading,
            onConfirm = { viewModel.deleteWallet(wallet.id) },
            onCancel = { walletPendingDelete = null },
        )
    }
    if (showAuditReport) {
        AuditReportDialog(
            findings = state.auditFindings,
            onClose = { showAuditReport = false },
        )
    }
    state.backupPreview?.let { preview ->
        AlertDialog(
            onDismissRequest = viewModel::cancelBackupPreview,
            title = { Text("Restore backup?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Current wallets, operations, debts, mandatory templates, tags, budgets, and Distribution will be replaced.")
                    Text("Rows: ${preview.importedRows} · Assets: ${preview.assetRows} · Snapshots: ${preview.assetSnapshotRows} · Goals: ${preview.goalRows} · Distribution: ${preview.distributionRows} · Rates: ${preview.currencyRateRows}")
                    state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                }
            },
            confirmButton = {
                Button(onClick = viewModel::restoreBackup, enabled = !state.loading) { Text("Restore") }
            },
            dismissButton = { TextButton(onClick = viewModel::cancelBackupPreview) { Text("Cancel") } },
        )
    }
}

@Composable
private fun BackupSection(loading: Boolean, onRestore: () -> Unit, onExport: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Full backup", style = MaterialTheme.typography.titleMedium)
            Text("Export or restore the complete JSON database snapshot, including budgets.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onExport, enabled = !loading) { Text("Export JSON") }
                TextButton(onClick = onRestore, enabled = !loading) { Text("Restore JSON") }
            }
        }
    }
}

@Composable
private fun CurrencySection(
    baseCurrency: String,
    currencies: List<String>,
    rates: List<app.ledgera.model.CurrencyRate>,
    refreshStatus: app.ledgera.model.CurrencyRefreshStatus?,
    providerStatuses: List<app.ledgera.model.CurrencyProviderStatus>,
    loading: Boolean,
    error: String?,
    onAddRate: () -> Unit,
    onUpdateRate: (CurrencyRate) -> Unit,
    onDeleteRate: (Long) -> Unit,
    onSetBase: (String) -> Unit,
    onRefresh: () -> Unit,
    onShowHistory: () -> Unit,
) {
    var requestedBase by remember(baseCurrency) { mutableStateOf(baseCurrency) }
    Card(Modifier.fillMaxWidth().height(360.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Currencies", style = MaterialTheme.typography.titleMedium)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(requestedBase, { requestedBase = it.uppercase().take(3) }, label = { Text("Base currency") }, modifier = Modifier.weight(1f), singleLine = true)
                Button(onClick = { onSetBase(requestedBase) }, enabled = !loading && requestedBase.length == 3) { Text("Set") }
                Button(onClick = onAddRate, enabled = !loading) { Text("Add rate") }
            }
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("Supported: ${currencies.joinToString()}", style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = onShowHistory, enabled = !loading && rates.size > 1) { Text("Rate history") }
                TextButton(onClick = onRefresh, enabled = !loading) { Text("Refresh now") }
            }
            refreshStatus?.let { status ->
                Text(
                    "Automatic refresh: ${status.status} · ${status.selectedProvider.ifBlank { "none" }} · ${status.effectiveDate}",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (status.status == "success") MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.error,
                )
            }
            if (providerStatuses.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(
                        "Available providers: ${providerStatuses.joinToString { it.name }}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Text(
                        "Selected provider: ${providerStatuses.filter { it.selected }.joinToString { it.name }.ifBlank { "not selected" }}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            LazyColumn(
                modifier = Modifier.fillMaxWidth().weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                val visibleRates = rates
                    .groupBy { it.baseCurrency.uppercase() to it.currency.uppercase() }
                    .values
                    .mapNotNull { group -> group.maxWithOrNull(compareBy<CurrencyRate> { it.effectiveDate }.thenBy { it.id }) }
                    .sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.currency })
                items(visibleRates, key = { it.id }) { rate ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("${rate.currency}/${rate.baseCurrency} = ${rate.rate} · ${rate.effectiveDate}")
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            TextButton(onClick = { onUpdateRate(rate) }, enabled = !loading) { Text("Update") }
                            TextButton(onClick = { onDeleteRate(rate.id) }, enabled = !loading) { Text("Delete") }
                        }
                    }
                }
                error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
            }
        }
    }
}

private fun String?.toProviderCredentialStatus(): String = when {
    this.orEmpty().startsWith("Environment", ignoreCase = true) -> "environment"
    this.orEmpty().startsWith("Configured", ignoreCase = true) -> "configured"
    this.orEmpty().startsWith("Invalid", ignoreCase = true) -> "invalid"
    else -> "missing"
}

@Composable
private fun OnlineProvidersSection(
    definitions: List<CurrencyProviderDefinition>,
    statuses: List<app.ledgera.model.CurrencyProviderStatus>,
    settings: List<app.ledgera.model.CurrencyProviderSetting>,
    credentialStatuses: Map<String, String>,
    exchangeRateCredentialStatus: String,
    loading: Boolean,
    onAdd: () -> Unit,
    onEdit: (CurrencyProviderDefinition) -> Unit,
    onDelete: (String) -> Unit,
    onConfigureExchangeRate: () -> Unit,
    onConfigureCredential: (CurrencyProviderDefinition) -> Unit,
    onSetMode: (CurrencyProviderDefinition, String) -> Unit,
    onTest: (CurrencyProviderDefinition) -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Online providers", style = MaterialTheme.typography.titleMedium)
                Button(onClick = onAdd, enabled = !loading) { Text("Add custom") }
            }
            Text("Built-in: ${statuses.filter { !it.name.startsWith("custom:") }.joinToString { it.name }}", style = MaterialTheme.typography.bodySmall)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("exchange_rate credential: $exchangeRateCredentialStatus", style = MaterialTheme.typography.bodySmall)
                TextButton(onClick = onConfigureExchangeRate, enabled = !loading) { Text("Configure key") }
            }
            if (definitions.isEmpty()) {
                Text("No custom providers configured.", style = MaterialTheme.typography.bodySmall)
            } else {
                Column(
                    Modifier.fillMaxWidth().heightIn(max = 260.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    definitions.forEach { provider ->
                        val status = statuses.firstOrNull { it.name == provider.providerId }
                        val setting = settings.firstOrNull { it.providerId == provider.providerId }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(provider.displayName, fontWeight = FontWeight.Medium)
                                Text("${provider.providerId} · ${provider.authMode} · ${if (provider.active) "active" else "test required"}", style = MaterialTheme.typography.bodySmall)
                                if (provider.authMode != "none") {
                                    Text("Credential: ${credentialStatuses[provider.providerId] ?: "Missing"}", style = MaterialTheme.typography.bodySmall)
                                }
                                status?.let { Text("Status: ${it.lastStatus}${it.diagnostic.takeIf(String::isNotBlank)?.let { detail -> " · $detail" } ?: ""}", style = MaterialTheme.typography.bodySmall) }
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                if (provider.authMode != "none") {
                                    TextButton(onClick = { onConfigureCredential(provider) }, enabled = !loading) { Text("Configure key") }
                                }
                                TextButton(
                                    onClick = { onSetMode(provider, if (setting?.mode == "primary") "fallback" else "primary") },
                                    enabled = !loading && provider.active,
                                ) { Text(if (setting?.mode == "primary") "Fallback" else "Primary") }
                                TextButton(
                                    onClick = { onSetMode(provider, if (setting?.mode == "fallback") "manual-only" else "fallback") },
                                    enabled = !loading && provider.active,
                                ) { Text(if (setting?.mode == "fallback") "Manual" else "Fallback") }
                                TextButton(onClick = { onTest(provider) }, enabled = !loading) { Text("Test") }
                                TextButton(onClick = { onEdit(provider) }, enabled = !loading) { Text("Edit") }
                                TextButton(onClick = { onDelete(provider.providerId) }, enabled = !loading) { Text("Delete") }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ExchangeRateCredentialDialog(
    status: String,
    loading: Boolean,
    error: String?,
    title: String = "ExchangeRate API key",
    onSave: (String) -> Unit,
    onCancel: () -> Unit,
) {
    var secret by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Status: $status", style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(
                    value = secret,
                    onValueChange = { secret = it },
                    label = { Text("API key") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("The key is stored in Windows Credential Manager and is not included in backups.", style = MaterialTheme.typography.bodySmall)
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(onClick = { onSave(secret) }, enabled = secret.isNotBlank() && !loading) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onCancel, enabled = !loading) { Text("Cancel") } },
    )
}

@Composable
private fun CustomProviderDialog(
    baseCurrency: String,
    existingProvider: CurrencyProviderDefinition? = null,
    loading: Boolean,
    error: String?,
    onSave: (CurrencyProviderDefinitionRequest) -> Unit,
    onCancel: () -> Unit,
) {
    var slug by remember(existingProvider) { mutableStateOf(existingProvider?.providerId?.removePrefix("custom:") ?: "") }
    var displayName by remember(existingProvider) { mutableStateOf(existingProvider?.displayName ?: "") }
    var endpoint by remember(existingProvider) { mutableStateOf(existingProvider?.endpoint ?: "") }
    var responseFormat by remember(existingProvider) { mutableStateOf(existingProvider?.responseFormat ?: "json") }
    var currencyPath by remember(existingProvider) { mutableStateOf(existingProvider?.currencyPath ?: "$.rates") }
    var ratePath by remember(existingProvider) { mutableStateOf(existingProvider?.ratePath ?: "$.rates") }
    var effectiveDatePath by remember(existingProvider) { mutableStateOf(existingProvider?.effectiveDatePath ?: "") }
    var aliasesJson by remember(existingProvider) { mutableStateOf(existingProvider?.aliasesJson ?: "{}") }
    var responseBase by remember(existingProvider) { mutableStateOf(existingProvider?.responseBaseCurrency ?: "USD") }
    var semantics by remember(existingProvider) { mutableStateOf(existingProvider?.rateSemantics ?: "quote_per_base") }
    var authMode by remember(existingProvider) { mutableStateOf(existingProvider?.authMode ?: "none") }
    var credentialRef by remember(existingProvider) { mutableStateOf(existingProvider?.credentialRef ?: "") }
    var requestBody by remember(existingProvider) { mutableStateOf(existingProvider?.requestBody ?: "") }
    var timeoutSeconds by remember(existingProvider) { mutableStateOf((existingProvider?.timeoutSeconds ?: 10).toString()) }
    var retryCount by remember(existingProvider) { mutableStateOf((existingProvider?.retryCount ?: 0).toString()) }
    var redirectLimit by remember(existingProvider) { mutableStateOf((existingProvider?.redirectLimit ?: 3).toString()) }
    var showAdvancedDialog by remember(existingProvider?.providerId) { mutableStateOf(false) }
    val valid = slug.matches(Regex("[a-z0-9][a-z0-9_-]{1,63}")) &&
        displayName.isNotBlank() && endpoint.startsWith("https://") &&
        currencyPath.isNotBlank() && ratePath.isNotBlank() && responseBase.matches(Regex("[A-Za-z]{3}")) &&
        (authMode == "none" || credentialRef.isNotBlank()) &&
        timeoutSeconds.toLongOrNull()?.let { it in 1..120 } == true &&
        retryCount.toLongOrNull()?.let { it in 0..3 } == true &&
        redirectLimit.toLongOrNull()?.let { it in 0..5 } == true
    AlertDialog(
        onDismissRequest = { if (!loading) onCancel() },
        title = { Text(if (existingProvider == null) "Add custom provider" else "Edit custom provider") },
        text = {
            Column(Modifier.width(DialogContentWidth).heightIn(max = 520.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(slug, { slug = it.lowercase() }, label = { Text("Slug") }, placeholder = { Text("my-provider") }, singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = existingProvider == null)
                OutlinedTextField(displayName, { displayName = it }, label = { Text("Display name") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(endpoint, { endpoint = it }, label = { Text("HTTPS endpoint") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(responseFormat, { responseFormat = it.lowercase() }, label = { Text("Format: json or xml") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(currencyPath, { currencyPath = it }, label = { Text("Currency path") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(ratePath, { ratePath = it }, label = { Text("Rate path") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(responseBase, { responseBase = it.uppercase().take(3) }, label = { Text("Response base") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(semantics, { semantics = it.lowercase() }, label = { Text("Rate semantics") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(authMode, { authMode = it.lowercase() }, label = { Text("Auth: none, api_key_header, api_key_query, bearer") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                if (authMode != "none") OutlinedTextField(credentialRef, { credentialRef = it }, label = { Text("Credential reference") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                TextButton(onClick = { showAdvancedDialog = true }, enabled = !loading) { Text("Advanced provider parameters") }
                Text("Base currency: $baseCurrency. Provider stays inactive until Test succeeds.", style = MaterialTheme.typography.bodySmall)
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSave(
                        CurrencyProviderDefinitionRequest(
                            providerId = "custom:$slug",
                            displayName = displayName,
                            endpoint = endpoint,
                            responseFormat = responseFormat,
                            currencyPath = currencyPath,
                            ratePath = ratePath,
                            effectiveDatePath = effectiveDatePath,
                            aliasesJson = aliasesJson,
                            responseBaseCurrency = responseBase,
                            rateSemantics = semantics,
                            authMode = authMode,
                            credentialRef = credentialRef,
                            requestBody = requestBody,
                            timeoutSeconds = timeoutSeconds.toLong(),
                            retryCount = retryCount.toLong(),
                            redirectLimit = redirectLimit.toLong(),
                        )
                    )
                },
                enabled = valid && !loading,
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onCancel, enabled = !loading) { Text("Cancel") } },
    )
    if (showAdvancedDialog) {
        AdvancedProviderParametersDialog(
            effectiveDatePath = effectiveDatePath,
            aliasesJson = aliasesJson,
            requestBody = requestBody,
            timeoutSeconds = timeoutSeconds,
            retryCount = retryCount,
            redirectLimit = redirectLimit,
            loading = loading,
            onEffectiveDatePathChange = { effectiveDatePath = it },
            onAliasesJsonChange = { aliasesJson = it },
            onRequestBodyChange = { requestBody = it },
            onTimeoutSecondsChange = { timeoutSeconds = it.filter(Char::isDigit) },
            onRetryCountChange = { retryCount = it.filter(Char::isDigit) },
            onRedirectLimitChange = { redirectLimit = it.filter(Char::isDigit) },
            onClose = { showAdvancedDialog = false },
        )
    }
}

@Composable
private fun AdvancedProviderParametersDialog(
    effectiveDatePath: String,
    aliasesJson: String,
    requestBody: String,
    timeoutSeconds: String,
    retryCount: String,
    redirectLimit: String,
    loading: Boolean,
    onEffectiveDatePathChange: (String) -> Unit,
    onAliasesJsonChange: (String) -> Unit,
    onRequestBodyChange: (String) -> Unit,
    onTimeoutSecondsChange: (String) -> Unit,
    onRetryCountChange: (String) -> Unit,
    onRedirectLimitChange: (String) -> Unit,
    onClose: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = { if (!loading) onClose() },
        title = { Text("Advanced provider parameters") },
        text = {
            Column(
                Modifier.width(DialogContentWidth).heightIn(max = 520.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("These settings are kept in the provider draft until you save it.", style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(effectiveDatePath, onEffectiveDatePathChange, label = { Text("Effective date path") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(aliasesJson, onAliasesJsonChange, label = { Text("Currency aliases JSON") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(requestBody, onRequestBodyChange, label = { Text("POST request body") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(timeoutSeconds, onTimeoutSecondsChange, label = { Text("Timeout seconds (1-120)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(retryCount, onRetryCountChange, label = { Text("Retries (0-3)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(redirectLimit, onRedirectLimitChange, label = { Text("Redirects (0-5)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = { TextButton(onClick = onClose, enabled = !loading) { Text("Done") } },
    )
}

@Composable
private fun CurrencyRateHistoryDialog(
    rates: List<CurrencyRate>,
    loading: Boolean,
    error: String?,
    onUpdate: (CurrencyRate) -> Unit,
    onDelete: (Long) -> Unit,
    onClose: () -> Unit,
) {
    val history = rates.sortedWith(
        compareByDescending<CurrencyRate> { it.effectiveDate }
            .thenBy(String.CASE_INSENSITIVE_ORDER) { it.currency }
            .thenByDescending { it.id },
    )
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text("Currency rate history") },
        text = {
            Column(Modifier.width(DialogContentWidth), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (history.isEmpty()) {
                    Text("No saved currency rates.")
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxWidth().heightIn(max = 420.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(history, key = { it.id }) { rate ->
                            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Row(
                                    Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Column(Modifier.weight(1f)) {
                                        Text("${rate.currency}/${rate.baseCurrency} = ${rate.rate}")
                                        Text(
                                            "${rate.effectiveDate} · ${rate.source}",
                                            style = MaterialTheme.typography.bodySmall,
                                        )
                                    }
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        TextButton(onClick = { onUpdate(rate) }, enabled = !loading) { Text("Update") }
                                        TextButton(onClick = { onDelete(rate.id) }, enabled = !loading) { Text("Delete") }
                                    }
                                }
                                HorizontalDivider()
                            }
                        }
                    }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = { TextButton(onClick = onClose) { Text("Close") } },
    )
}

@Composable
private fun CurrencyRateDialog(
    baseCurrency: String,
    existingRate: CurrencyRate? = null,
    existingRates: List<CurrencyRate> = emptyList(),
    error: String?,
    submitting: Boolean,
    onSave: (String, String, String, String, String) -> Unit,
    onCancel: () -> Unit,
) {
    var currency by remember(existingRate?.id) { mutableStateOf(existingRate?.currency.orEmpty()) }
    var rate by remember(existingRate?.id) { mutableStateOf(existingRate?.rate.orEmpty()) }
    var date by remember(existingRate?.id) { mutableStateOf(existingRate?.effectiveDate.orEmpty()) }
    var source by remember(existingRate?.id) { mutableStateOf(existingRate?.source ?: "manual") }
    val currencyError = CurrencyValidation.validateSupportedCurrency(currency)
        ?.takeIf { currency != baseCurrency }
    val dateError = DateValidation.validateGuiNotFuture(date)
    val rateError = if (rate.toDoubleOrNull()?.let { it > 0.0 } == true) null else "Rate must be greater than zero"
    val sourceError = when {
        source.trim().isEmpty() -> "Manual source label is required"
        source.trim().length > 64 -> "Manual source label must be 64 characters or fewer"
        !Regex("[A-Za-z0-9_. -]+").matches(source.trim()) -> "Manual source label contains unsupported characters"
        else -> null
    }
    val replacesExisting = existingRates.any {
        it.id != existingRate?.id &&
            it.baseCurrency.equals(baseCurrency, ignoreCase = true) &&
            it.currency.equals(currency.trim(), ignoreCase = true) &&
            it.effectiveDate == (DateValidation.formatGuiDateToYmd(date) ?: date.trim())
    }
    val valid = currencyError == null && currency != baseCurrency && dateError == null && rateError == null && sourceError == null
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text(if (existingRate == null) "Add currency rate" else "Update currency rate") },
        text = {
        Column(Modifier.width(DialogContentWidth), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(currency, { currency = it.uppercase().take(3) }, label = { Text("Currency") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                OutlinedTextField(rate, { rate = it }, label = { Text("Rate to $baseCurrency") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
                LedgerDateField(
                    value = date,
                    onValueChange = { date = it },
                    label = "Effective date",
                    externalError = dateError,
                    showErrorOutline = false,
                    showErrorText = false,
                )
                OutlinedTextField(
                    source,
                    { source = it },
                    label = { Text("Manual source label") },
                    supportingText = { Text("Use a short label such as manual or bank") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )
                if (replacesExisting) {
                    Text("A rate for this date already exists. Saving will replace it.", color = MaterialTheme.colorScheme.error)
                }
                listOfNotNull(currencyError, rateError, dateError, sourceError).firstOrNull()?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(
                onClick = { onSave(baseCurrency, currency, rate, DateValidation.formatGuiDateToYmd(date).orEmpty(), source) },
                enabled = valid && !submitting,
            ) { Text(if (existingRate == null) "Save" else "Update") }
        },
        dismissButton = { TextButton(onClick = onCancel) { Text("Cancel") } },
    )
}

@Composable
private fun WalletsSection(
    wallets: List<WalletSettingsItem>,
    loading: Boolean,
    onAddWallet: () -> Unit,
    onDeleteWallet: (WalletSettingsItem) -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Wallets", style = MaterialTheme.typography.titleMedium)
                Button(onClick = onAddWallet) { Text("Add wallet") }
            }
            if (loading) {
                CircularProgressIndicator()
            } else if (wallets.isEmpty()) {
                Text("No wallets found in the selected database.")
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 450.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(wallets, key = { it.id }) { wallet ->
                        WalletRow(wallet, onDeleteWallet)
                    }
                }
            }
        }
    }
}

@Composable
private fun WalletRow(wallet: WalletSettingsItem, onDeleteWallet: (WalletSettingsItem) -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(wallet.name, fontWeight = FontWeight.SemiBold)
                Text("${wallet.balance} ${wallet.balanceCurrency}")
            }
            Text("Initial ${wallet.initialBalance} ${wallet.currency}")
            Text(
                listOfNotNull(
                    if (wallet.system) "system" else null,
                    if (wallet.allowNegative) "allow negative" else "no negative",
                    if (wallet.active) "active" else "inactive",
                ).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (wallet.active && !wallet.system) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = { onDeleteWallet(wallet) }) {
                        Text("Delete")
                    }
                }
            }
        }
    }
}

@Composable
private fun AuditSection(
    running: Boolean,
    summary: AuditSummary?,
    hasFindings: Boolean,
    onRunAudit: () -> Unit,
    onViewReport: () -> Unit,
) {
    Card(Modifier.fillMaxWidth().heightIn(min = 144.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Audit", style = MaterialTheme.typography.titleMedium)
                Button(onClick = onRunAudit, enabled = !running) {
                    Text(if (running) "Running..." else "Run audit")
                }
            }
            if (running) {
                CircularProgressIndicator()
            }
            summary?.let {
                Text(
                    "Errors ${it.errors} · Warnings ${it.warnings} · Passed ${it.ok} · Total ${it.total}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } ?: Text(
                "Run a read-only Rust AuditEngine v2 report for the selected database.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (hasFindings) {
                TextButton(onClick = onViewReport) {
                    Text("View report")
                }
            }
        }
    }
}

@Composable
private fun AuditReportDialog(findings: List<AuditFinding>, onClose: () -> Unit) {
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text("Audit report") },
        text = {
            LazyColumn(
                modifier = Modifier.width(DialogContentWidth).heightIn(max = 520.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                auditGroup("Errors", findings, "error")?.let { group ->
                    item { AuditFindingGroup(group.title, group.findings) }
                }
                auditGroup("Warnings", findings, "warning")?.let { group ->
                    item { AuditFindingGroup(group.title, group.findings) }
                }
                auditGroup("Passed", findings, "ok")?.let { group ->
                    item { AuditFindingGroup(group.title, group.findings) }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onClose) { Text("Close") }
        },
    )
}

@Composable
private fun AuditFindingGroup(title: String, findings: List<AuditFinding>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        findings.forEach { finding ->
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(finding.check, fontWeight = FontWeight.Medium)
                Text(finding.message)
                if (finding.entity.isNotBlank()) {
                    Text(
                        finding.entity,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        HorizontalDivider()
    }
}

private data class AuditFindingGroupData(
    val title: String,
    val findings: List<AuditFinding>,
)

private fun auditGroup(
    title: String,
    findings: List<AuditFinding>,
    severity: String,
): AuditFindingGroupData? {
    val group = findings.filter { it.severity.equals(severity, ignoreCase = true) }
    return if (group.isEmpty()) null else AuditFindingGroupData(title, group)
}

@Composable
private fun DeleteWalletConfirmDialog(
    wallet: WalletSettingsItem,
    engineError: String?,
    submitting: Boolean,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Delete wallet") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(wallet.name, fontWeight = FontWeight.SemiBold)
                Text(
                    "Delete wallet? Empty wallets without history are removed permanently. " +
                        "Wallets with zero balance and history are deactivated."
                )
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(onClick = onConfirm, enabled = !submitting) {
                Text(if (submitting) "Deleting..." else "Delete")
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

@Composable
private fun CreateWalletDialog(
    baseCurrency: String,
    supportedCurrencies: List<String>,
    engineError: String?,
    submitting: Boolean,
    onSubmit: (CreateWalletRequest) -> Unit,
    onCancel: () -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var initialBalance by remember { mutableStateOf("0") }
    var allowNegative by remember { mutableStateOf(false) }
    var currency by remember(baseCurrency, supportedCurrencies) {
        mutableStateOf(baseCurrency.ifBlank { supportedCurrencies.firstOrNull() ?: "KZT" })
    }
    val validationError = SettingsValidation.validateWalletFields(
        name = name,
        currency = currency,
        initialBalance = initialBalance,
        baseCurrency = baseCurrency,
    )

    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Add wallet") },
        text = {
            Column(
                modifier = Modifier.width(DialogContentWidth).heightIn(max = 420.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                OutlinedTextField(
                    modifier = Modifier.fillMaxWidth(),
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Name") },
                    singleLine = true,
                )
                OutlinedTextField(
                    modifier = Modifier.fillMaxWidth(),
                    value = currency,
                    onValueChange = { currency = it.uppercase().filter(Char::isLetter).take(3) },
                    label = { Text("Currency") },
                    singleLine = true,
                    supportingText = { Text("Supported: ${supportedCurrencies.joinToString()}") },
                )
                OutlinedTextField(
                    modifier = Modifier.fillMaxWidth(),
                    value = initialBalance,
                    onValueChange = { initialBalance = it },
                    label = { Text("Initial balance") },
                    singleLine = true,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = allowNegative, onCheckedChange = { allowNegative = it })
                    Text("Allow negative balance")
                }
                Spacer(Modifier.height(2.dp))
                (validationError ?: engineError)?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSubmit(
                        CreateWalletRequest(
                            name = name,
                            currency = currency,
                            initialBalance = initialBalance.ifBlank { "0" },
                            allowNegative = allowNegative,
                        )
                    )
                },
                enabled = validationError == null && !submitting,
            ) {
                Text(if (submitting) "Creating..." else "Create")
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

private val DialogContentWidth = 360.dp

private fun currentSettingsDate(): String = currentLedgerDate().let {
    "%04d-%02d-%02d".format(it.year, it.month, it.day)
}
