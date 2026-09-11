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
import app.ledgera.model.WalletSettingsItem

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
    modifier: Modifier = Modifier,
    fileActions: SettingsFileActions = NoSettingsFileActions,
) {
    val state by viewModel.state.collectAsState()
    var showCreateWalletDialog by remember { mutableStateOf(false) }
    var walletPendingDelete by remember { mutableStateOf<WalletSettingsItem?>(null) }
    var showAuditReport by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        viewModel.refresh()
    }
    LaunchedEffect(showCreateWalletDialog, state.notice) {
        if (showCreateWalletDialog && state.notice?.startsWith("Wallet created") == true) {
            showCreateWalletDialog = false
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

    Column(
        modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
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
            engineError = state.error,
            submitting = state.loading,
            onSubmit = viewModel::createWallet,
            onCancel = { showCreateWalletDialog = false },
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
                    Text("Current wallets, operations, debts, mandatory templates, tags, and budgets will be replaced.")
                    Text("Rows: ${preview.importedRows} · Budgets: ${preview.budgetRows}")
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
                Text("${wallet.balance} ${wallet.currency}")
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
    engineError: String?,
    submitting: Boolean,
    onSubmit: (CreateWalletRequest) -> Unit,
    onCancel: () -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var initialBalance by remember { mutableStateOf("0") }
    var allowNegative by remember { mutableStateOf(false) }
    val currency = baseCurrency.ifBlank { "KZT" }
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
                    onValueChange = {},
                    label = { Text("Currency") },
                    enabled = false,
                    singleLine = true,
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
