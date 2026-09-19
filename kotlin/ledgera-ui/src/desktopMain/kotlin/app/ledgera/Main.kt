package app.ledgera

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.OutlinedTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.WindowPlacement
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import app.ledgera.bridge.RustEngineAdapter
import app.ledgera.analytics.AnalyticsViewModel
import app.ledgera.budget.BudgetViewModel
import app.ledgera.debts.DebtsViewModel
import app.ledgera.mandatory.MandatoryViewModel
import app.ledgera.mandatory.MandatoryFileActions
import app.ledgera.operations.ImportFileSnapshotProvider
import app.ledgera.operations.OperationsViewModel
import app.ledgera.operations.OperationsFileActions
import app.ledgera.settings.SettingsViewModel
import app.ledgera.settings.SettingsFileActions
import app.ledgera.bridge.SettingsEngine
import app.ledgera.ui.ToastHost
import app.ledgera.reports.ReportsViewModel
import app.ledgera.reports.ReportsFileActions
import app.ledgera.shell.AppShell
import app.ledgera.shell.AppShellViewModel
import app.ledgera.theme.LedgeraTheme
import java.awt.Window as AwtWindow
import java.awt.FileDialog
import java.awt.Frame
import java.awt.event.ComponentEvent
import java.io.File
import java.io.FilenameFilter
import javax.swing.SwingUtilities
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

fun main(args: Array<String>) {
    val singleInstance = SingleInstanceSupport.acquire()
    if (singleInstance == null) {
        SingleInstanceSupport.requestActivation()
        return
    }

    singleInstance.use {
        runApplication(args)
    }
}

private fun runApplication(args: Array<String>) = application {
    val dbPath = args.asList().windowed(2, 1)
        .firstOrNull { it.first() == "--db-path" }
        ?.last()
    val windowState = rememberWindowState(placement = WindowPlacement.Maximized)

    Window(onCloseRequest = ::exitApplication, state = windowState, title = "Ledgera Beta.1") {
        RefreshDpiAfterStartup(window)
        LedgeraTheme {
            Surface {
                if (dbPath.isNullOrBlank()) {
                    Text("Start with --db-path <ledger.db>.")
                } else {
                    val newDatabase = !File(dbPath).exists()
                    val engine = RustEngineAdapter(dbPath)
                    var showInitialBalanceDialog by remember { mutableStateOf(newDatabase) }
                    var startupNotice by remember { mutableStateOf<String?>(null) }
                    ToastHost(
                        message = startupNotice,
                        onDismiss = { startupNotice = null },
                        modifier = Modifier.fillMaxSize(),
                    ) {
                        Box(Modifier.fillMaxSize()) {
                            AppShell(
                            viewModel = AppShellViewModel(engine),
                            operationsViewModel = OperationsViewModel(
                                engine,
                                importFileSnapshotProvider = DesktopImportFileSnapshotProvider,
                            ),
                            debtsViewModel = DebtsViewModel(engine),
                            mandatoryViewModel = MandatoryViewModel(
                                engine,
                                importFileSnapshotProvider = DesktopImportFileSnapshotProvider,
                            ),
                            settingsViewModel = SettingsViewModel(engine),
                            reportsViewModel = ReportsViewModel(engine),
                            budgetViewModel = BudgetViewModel(engine),
                            analyticsViewModel = AnalyticsViewModel(engine),
                            operationsFileActions = DesktopOperationsFileActions(window),
                            mandatoryFileActions = DesktopMandatoryFileActions(window),
                            reportsFileActions = DesktopReportsFileActions(window),
                            settingsFileActions = DesktopSettingsFileActions(window),
                            )
                            if (showInitialBalanceDialog) {
                                InitialBalanceDialog(engine) {
                                    showInitialBalanceDialog = false
                                    startupNotice = "Initial balance saved"
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun InitialBalanceDialog(engine: SettingsEngine, onCompleted: () -> Unit) {
    var value by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var submitting by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = {},
        title = { Text("Initial system wallet balance") },
        text = {
            Column {
                Text("Enter the starting balance for the system wallet.")
                OutlinedTextField(
                    value = value,
                    onValueChange = { value = it; error = null },
                    label = { Text("Balance") },
                    singleLine = true,
                    isError = error != null,
                    supportingText = { error?.let { Text(it) } },
                )
            }
        },
        confirmButton = {
            Button(
                enabled = !submitting,
                onClick = {
                    val number = value.trim().toBigDecimalOrNull()
                    if (number == null || number < java.math.BigDecimal.ZERO) {
                        error = "Enter a valid non-negative number"
                        return@Button
                    }
                    submitting = true
                    scope.launch {
                        runCatching { engine.setSystemWalletInitialBalance(value.trim()) }
                            .onSuccess { onCompleted() }
                            .onFailure { failure ->
                                submitting = false
                                error = failure.message ?: "Unable to save balance"
                            }
                    }
                },
            ) { Text("Continue") }
        },
    )
}

private class DesktopOperationsFileActions(private val owner: AwtWindow) : OperationsFileActions {
    override fun openImportPath(): String? =
        FileDialog(ownerFrame(), "Import operations", FileDialog.LOAD)
            .apply {
                file = "*.csv;*.xlsx"
                filenameFilter = operationsFileFilter
                isVisible = true
            }
            .selectedPath(defaultExtension = "xlsx")

    override fun saveExportPath(): String? =
        FileDialog(ownerFrame(), "Export operations", FileDialog.SAVE)
            .apply {
                file = "operations.xlsx"
                filenameFilter = operationsFileFilter
                isVisible = true
            }
            .selectedPath(defaultExtension = "xlsx")

    private fun ownerFrame(): Frame? = owner as? Frame

    private fun FileDialog.selectedPath(defaultExtension: String): String? {
        val selectedDirectory = directory ?: return null
        val selectedFile = file ?: return null
        val path = File(selectedDirectory, selectedFile).absolutePath
        return if (path.endsWith(".csv", ignoreCase = true) || path.endsWith(".xlsx", ignoreCase = true)) {
            path
        } else {
            "$path.$defaultExtension"
        }
    }

    private companion object {
        val operationsFileFilter = FilenameFilter { _, name ->
            name.endsWith(".csv", ignoreCase = true) || name.endsWith(".xlsx", ignoreCase = true)
        }
    }
}

private class DesktopMandatoryFileActions(private val owner: AwtWindow) : MandatoryFileActions {
    override fun openImportPath(): String? =
        FileDialog(ownerFrame(), "Import mandatory templates", FileDialog.LOAD)
            .apply {
                file = "*.csv;*.xlsx"
                filenameFilter = tabularFileFilter
                isVisible = true
            }
            .selectedPath(defaultExtension = "xlsx")

    override fun saveExportPath(): String? =
        FileDialog(ownerFrame(), "Export mandatory templates", FileDialog.SAVE)
            .apply {
                file = "mandatory.xlsx"
                filenameFilter = tabularFileFilter
                isVisible = true
            }
            .selectedPath(defaultExtension = "xlsx")

    private fun ownerFrame(): Frame? = owner as? Frame
}

private class DesktopReportsFileActions(private val owner: AwtWindow) : ReportsFileActions {
    override fun saveReportPath(extension: String): String? =
        FileDialog(owner as? Frame, "Export report", FileDialog.SAVE)
            .apply {
                file = "report.$extension"
                filenameFilter = FilenameFilter { _, name -> name.endsWith(".$extension", ignoreCase = true) }
                isVisible = true
            }
            .selectedPath(defaultExtension = extension)
}

private class DesktopSettingsFileActions(private val owner: AwtWindow) : SettingsFileActions {
    override fun openBackupPath(): String? =
        FileDialog(owner as? Frame, "Restore full backup", FileDialog.LOAD)
            .apply {
                file = "*.json"
                filenameFilter = FilenameFilter { _, name -> name.endsWith(".json", ignoreCase = true) }
                isVisible = true
            }
            .selectedPath(defaultExtension = "json")

    override fun saveBackupPath(): String? =
        FileDialog(owner as? Frame, "Export full backup", FileDialog.SAVE)
            .apply {
                file = "ledgera-backup.json"
                filenameFilter = FilenameFilter { _, name -> name.endsWith(".json", ignoreCase = true) }
                isVisible = true
            }
            .selectedPath(defaultExtension = "json")
}

private object DesktopImportFileSnapshotProvider : ImportFileSnapshotProvider {
    override fun snapshot(path: String): String? {
        val file = File(path)
        return if (file.isFile) "${file.length()}:${file.lastModified()}" else null
    }
}

private fun FileDialog.selectedPath(defaultExtension: String): String? {
    val selectedDirectory = directory ?: return null
    val selectedFile = file ?: return null
    val path = File(selectedDirectory, selectedFile).absolutePath
    return if (path.endsWith(".$defaultExtension", ignoreCase = true) ||
        path.endsWith(".csv", ignoreCase = true) || path.endsWith(".xlsx", ignoreCase = true) || path.endsWith(".pdf", ignoreCase = true)) {
        path
    } else {
        "$path.$defaultExtension"
    }
}

private val tabularFileFilter = FilenameFilter { _, name ->
    name.endsWith(".csv", ignoreCase = true) || name.endsWith(".xlsx", ignoreCase = true)
}

@Composable
private fun RefreshDpiAfterStartup(window: AwtWindow) {
    LaunchedEffect(window) {
        repeat(2) {
            delay(50)
            SwingUtilities.invokeLater {
                window.dispatchEvent(ComponentEvent(window, ComponentEvent.COMPONENT_RESIZED))
                window.invalidate()
                window.validate()
                window.repaint()
            }
        }
    }
}
