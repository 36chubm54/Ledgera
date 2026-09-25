package app.ledgera.mandatory

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import app.ledgera.model.MandatoryImportResult
import app.ledgera.model.MandatoryAddToRecordsDraft
import app.ledgera.model.MandatoryTemplateDraft
import app.ledgera.model.MandatoryTemplateItem
import app.ledgera.model.WalletOption
import app.ledgera.ui.LedgerDateField
import app.ledgera.validation.DateValidation

interface MandatoryFileActions {
    fun openImportPath(): String?
    fun saveExportPath(): String?
}

object NoMandatoryFileActions : MandatoryFileActions {
    override fun openImportPath(): String? = null
    override fun saveExportPath(): String? = null
}

@Composable
fun MandatoryScreen(
    viewModel: MandatoryViewModel,
    modifier: Modifier = Modifier,
    fileActions: MandatoryFileActions = NoMandatoryFileActions,
) {
    val state by viewModel.state.collectAsState()
    var confirmExport by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    Box(modifier = modifier.fillMaxSize()) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Mandatory", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)

        MandatoryListCard(
            templates = state.templates,
                selectedTemplateId = state.selectedTemplateId,
                loading = state.loading,
                onSelect = viewModel::selectTemplate,
                modifier = Modifier.weight(0.66f),
            )
            MandatoryActionsCard(
                selected = state.templates.firstOrNull { it.id == state.selectedTemplateId },
                inProgress = state.inProgress,
                onAddToRecords = viewModel::openAddToRecordsDialog,
                onApplyAutoPay = viewModel::applyAutoPayments,
                onImport = { viewModel.previewImportMandatory(fileActions.openImportPath()) },
                onExport = { confirmExport = true },
                onDelete = viewModel::requestDeleteSelectedTemplate,
                onDeleteAll = viewModel::requestDeleteAllTemplates,
                modifier = Modifier.weight(0.34f),
            )
        }

        FloatingActionButton(
            modifier = Modifier.align(Alignment.BottomEnd).padding(32.dp),
            onClick = viewModel::openCreateDialog,
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
        ) {
            Text("+", style = MaterialTheme.typography.headlineMedium)
        }

        state.editDraft?.let { draft ->
            MandatoryTemplateDialog(
                draft = draft,
                wallets = state.wallets,
                baseCurrency = state.baseCurrency,
                engineError = state.error,
                submitting = state.inProgress,
                onDraftChange = viewModel::updateDraft,
                onSubmit = viewModel::saveTemplate,
                onCancel = viewModel::closeEditDialog,
            )
        }

        state.addToRecordsDraft?.let { draft ->
            AddMandatoryToRecordsDialog(
                draft = draft,
                wallets = state.wallets,
                engineError = state.error,
                submitting = state.inProgress,
                onDraftChange = viewModel::updateAddToRecordsDraft,
                onSubmit = viewModel::addToRecords,
                onCancel = viewModel::closeAddToRecordsDialog,
            )
        }

        state.deleteTemplateId?.let { templateId ->
            DeleteMandatoryTemplateDialog(
                templateId = templateId,
                engineError = state.error,
                submitting = state.inProgress,
                onConfirm = viewModel::deleteSelectedTemplate,
                onCancel = viewModel::closeDeleteTemplateDialog,
            )
        }

        if (state.confirmDeleteAll) {
            DeleteAllMandatoryTemplatesDialog(
                engineError = state.error,
                submitting = state.inProgress,
                onConfirm = viewModel::deleteAllTemplates,
                onCancel = viewModel::closeDeleteAllDialog,
            )
        }

        if (confirmExport) {
            ExportMandatoryConfirmDialog(
                onConfirm = {
                    confirmExport = false
                    viewModel.exportMandatory(fileActions.saveExportPath())
                },
                onCancel = { confirmExport = false },
            )
        }

        state.importPreview?.let { preview ->
            ImportMandatoryPreviewDialog(
                preview = preview,
                path = state.importPath.orEmpty(),
                submitting = state.loading,
                engineError = state.error,
                onConfirm = viewModel::confirmImportMandatory,
                onCancel = viewModel::cancelImportPreview,
            )
        }
    }
}

@Composable
private fun MandatoryListCard(
    templates: List<MandatoryTemplateItem>,
    selectedTemplateId: Long?,
    loading: Boolean,
    onSelect: (Long) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Mandatory templates", style = MaterialTheme.typography.titleMedium)
            if (loading && templates.isEmpty()) {
                CircularProgressIndicator()
            } else if (templates.isEmpty()) {
                Text("No mandatory templates found in the selected database.")
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(templates, key = { it.id }) { template ->
                        MandatoryTemplateRow(
                            template = template,
                            selected = selectedTemplateId == template.id,
                            onClick = { onSelect(template.id) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun MandatoryTemplateRow(
    template: MandatoryTemplateItem,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surface
            },
        ),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(template.description, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Text("${template.category} · ${template.period} · wallet #${template.walletId}")
                Text(if (template.autoPay) "Auto-pay anchor ${template.date}" else "Manual template")
            }
            Text("${template.amountBase} ${template.currency}", style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
private fun MandatoryActionsCard(
    selected: MandatoryTemplateItem?,
    inProgress: Boolean,
    onAddToRecords: () -> Unit,
    onApplyAutoPay: () -> Unit,
    onImport: () -> Unit,
    onExport: () -> Unit,
    onDelete: () -> Unit,
    onDeleteAll: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Actions", style = MaterialTheme.typography.titleMedium)
            Text(
                selected?.let { "Selected: ${it.description}" } ?: "Select a mandatory template to add or delete it.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Button(onClick = onAddToRecords, enabled = selected != null && !inProgress) {
                    Text("Add to records")
                }
                OutlinedButton(onClick = onApplyAutoPay, enabled = !inProgress) {
                    Text("Apply auto-pay")
                }
                OutlinedButton(onClick = onImport, enabled = !inProgress) {
                    Text("Import")
                }
                OutlinedButton(onClick = onExport, enabled = !inProgress) {
                    Text("Export")
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                OutlinedButton(onClick = onDelete, enabled = selected != null && !inProgress) {
                    Text("Delete")
                }
                TextButton(onClick = onDeleteAll, enabled = !inProgress) {
                    Text("Delete all")
                }
            }
        }
    }
}

@Composable
private fun MandatoryTemplateDialog(
    draft: MandatoryTemplateDraft,
    wallets: List<WalletOption>,
    baseCurrency: String,
    engineError: String?,
    submitting: Boolean,
    onDraftChange: (MandatoryTemplateDraft) -> Unit,
    onSubmit: () -> Unit,
    onCancel: () -> Unit,
) {
    val validationError = if (draft.id == null) {
        MandatoryValidation.validateCreateDraft(draft, baseCurrency)
    } else {
        MandatoryValidation.validateUpdateDraft(draft)
    }
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text(if (draft.id == null) "Add mandatory template" else "Edit mandatory template") },
        text = {
            Column(
                Modifier.widthIn(min = 420.dp, max = 560.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                WalletChips(
                    title = "Wallet",
                    wallets = wallets,
                    selectedWalletId = draft.walletId,
                    onSelected = { onDraftChange(draft.copy(walletId = it)) },
                )
                if (draft.id == null) {
                    SingleLineField(
                        value = draft.amountOriginal,
                        onValueChange = { onDraftChange(draft.copy(amountOriginal = it, amountBase = it)) },
                        label = "Amount",
                    )
                    SingleLineField(
                        value = draft.currency,
                        onValueChange = { onDraftChange(draft.copy(currency = MandatoryValidation.normalizeCurrency(it))) },
                        label = "Currency",
                    )
                }
                SingleLineField(
                    value = draft.amountBase,
                    onValueChange = { onDraftChange(draft.copy(amountBase = it)) },
                    label = "Amount in base currency",
                )
                SingleLineField(
                    value = draft.category,
                    onValueChange = { onDraftChange(draft.copy(category = it)) },
                    label = "Category",
                    enabled = draft.id == null,
                )
                SingleLineField(
                    value = draft.description,
                    onValueChange = { onDraftChange(draft.copy(description = it)) },
                    label = "Description",
                    enabled = draft.id == null,
                )
                PeriodChips(draft.period) { onDraftChange(draft.copy(period = it)) }
                LedgerDateField(
                    value = draft.date,
                    onValueChange = { onDraftChange(draft.copy(date = it)) },
                    label = "Auto-pay anchor",
                    required = false,
                    allowFuture = true,
                    showErrorOutline = false,
                    showErrorText = false,
                )
                Text(
                    if (draft.date.isBlank()) {
                        "Auto-pay disabled"
                    } else {
                        "Auto-pay enabled from ${formatDateForInputHint(draft.date)}"
                    },
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                validationError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(onClick = onSubmit, enabled = !submitting && validationError == null) {
                Text(if (draft.id == null) "Create" else "Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel, enabled = !submitting) {
                Text("Cancel")
            }
        },
    )
}

@Composable
private fun AddMandatoryToRecordsDialog(
    draft: MandatoryAddToRecordsDraft,
    wallets: List<WalletOption>,
    engineError: String?,
    submitting: Boolean,
    onDraftChange: (MandatoryAddToRecordsDraft) -> Unit,
    onSubmit: () -> Unit,
    onCancel: () -> Unit,
) {
    val validationError = MandatoryValidation.validateAddToRecordsDraft(draft)
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text("Add mandatory template to records") },
        text = {
            Column(
                Modifier.widthIn(min = 420.dp, max = 560.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                WalletChips(
                    title = "Wallet",
                    wallets = wallets,
                    selectedWalletId = draft.walletId,
                    onSelected = { onDraftChange(draft.copy(walletId = it)) },
                )
                LedgerDateField(
                    value = draft.date,
                    onValueChange = { onDraftChange(draft.copy(date = it)) },
                    label = "Date",
                    allowFuture = false,
                    showErrorOutline = false,
                    showErrorText = false,
                )
                validationError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(onClick = onSubmit, enabled = !submitting && validationError == null) {
                Text("Add")
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel, enabled = !submitting) {
                Text("Cancel")
            }
        },
    )
}

@Composable
private fun DeleteMandatoryTemplateDialog(
    templateId: Long,
    engineError: String?,
    submitting: Boolean,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text("Delete mandatory template?") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Delete selected mandatory template (id=$templateId)? Existing operation rows are kept.")
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = { Button(onClick = onConfirm, enabled = !submitting) { Text("Delete") } },
        dismissButton = { TextButton(onClick = onCancel, enabled = !submitting) { Text("Cancel") } },
    )
}

@Composable
private fun DeleteAllMandatoryTemplatesDialog(
    engineError: String?,
    submitting: Boolean,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text("Delete all mandatory templates?") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Delete all mandatory templates? Existing operation rows are kept.")
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = { Button(onClick = onConfirm, enabled = !submitting) { Text("Delete all") } },
        dismissButton = { TextButton(onClick = onCancel, enabled = !submitting) { Text("Cancel") } },
    )
}

@Composable
private fun ExportMandatoryConfirmDialog(onConfirm: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Export mandatory templates") },
        text = {
            Text(
                "Export creates a readable file with financial data. Save it only to a trusted location."
            )
        },
        confirmButton = {
            Button(onClick = onConfirm) { Text("Export") }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

@Composable
private fun ImportMandatoryPreviewDialog(
    preview: MandatoryImportResult,
    path: String,
    submitting: Boolean,
    engineError: String?,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text("Import preview") },
        text = {
            Column(
                Modifier.widthIn(min = 420.dp, max = 560.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(path, style = MaterialTheme.typography.bodySmall)
                Text("Templates to import: ${preview.imported}")
                Text("Rows skipped: ${preview.skipped}")
                if (preview.errors.isNotEmpty()) {
                    Text("First errors", fontWeight = FontWeight.SemiBold)
                    preview.errors.take(5).forEach { error ->
                        Text("- $error", color = MaterialTheme.colorScheme.error)
                    }
                }
                if (preview.blockingErrors) {
                    Text(
                        "This preview has blocking validation errors. Fix the file and run preview again.",
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                Text(
                    "Current mandatory templates will be replaced. Generated operation rows are kept.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            Button(onClick = onConfirm, enabled = !submitting && !preview.blockingErrors) {
                Text("Import")
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel, enabled = !submitting) {
                Text("Cancel")
            }
        },
    )
}

private fun formatDateForInputHint(value: String): String =
    DateValidation.formatYmdToDmy(value).ifBlank { value }

@Composable
private fun WalletChips(
    title: String,
    wallets: List<WalletOption>,
    selectedWalletId: Long,
    onSelected: (Long) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(title, style = MaterialTheme.typography.labelLarge)
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            wallets.forEach { wallet ->
                val selected = wallet.id == selectedWalletId
                if (selected) {
                    Button(onClick = { onSelected(wallet.id) }) {
                        Text("${wallet.name} · ${wallet.currency}")
                    }
                } else {
                    OutlinedButton(onClick = { onSelected(wallet.id) }) {
                        Text("${wallet.name} · ${wallet.currency}")
                    }
                }
            }
        }
    }
}

@Composable
private fun PeriodChips(selectedPeriod: String, onSelected: (String) -> Unit) {
    val periods = listOf("daily", "weekly", "monthly", "yearly")
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Period", style = MaterialTheme.typography.labelLarge)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            periods.forEach { period ->
                if (period == selectedPeriod) {
                    Button(onClick = { onSelected(period) }) { Text(period) }
                } else {
                    OutlinedButton(onClick = { onSelected(period) }) { Text(period) }
                }
            }
        }
    }
}

@Composable
private fun SingleLineField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    enabled: Boolean = true,
) {
    OutlinedTextField(
        value = value,
        onValueChange = { onValueChange(it.lineSequence().firstOrNull().orEmpty()) },
        label = { Text(label) },
        singleLine = true,
        enabled = enabled,
        modifier = Modifier.fillMaxWidth(),
    )
}
