package app.ledgera.operations

import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.TextButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.ledgera.model.CreateOperationRequest
import app.ledgera.model.CreateTransferRequest
import app.ledgera.model.OperationDraft
import app.ledgera.model.OperationFilter
import app.ledgera.model.OperationImportResult
import app.ledgera.model.TransferDraft
import app.ledgera.model.WalletOption
import app.ledgera.ui.AutocompleteTextField
import app.ledgera.ui.LedgerDateField
import app.ledgera.ui.TagAutocompleteField
import app.ledgera.ui.toComposeTagColor
import app.ledgera.validation.currentLedgerDate

interface OperationsFileActions {
    fun openImportPath(): String?
    fun saveExportPath(): String?
}

object NoOperationsFileActions : OperationsFileActions {
    override fun openImportPath(): String? = null
    override fun saveExportPath(): String? = null
}

@Composable
fun OperationsScreen(
    viewModel: OperationsViewModel,
    modifier: Modifier = Modifier,
    fileActions: OperationsFileActions = NoOperationsFileActions,
) {
    val state by viewModel.state.collectAsState()
    var showCreateDialog by remember { mutableStateOf(false) }
    var showTransferDialog by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    var confirmTransferDelete by remember { mutableStateOf(false) }
    var confirmDeleteAll by remember { mutableStateOf(false) }
    var confirmSelectiveDelete by remember { mutableStateOf(false) }
    var confirmExport by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }
    LaunchedEffect(showCreateDialog, state.notice) {
        if (showCreateDialog && state.notice == "Operation added") {
            showCreateDialog = false
        }
    }
    LaunchedEffect(showTransferDialog, state.notice) {
        if (showTransferDialog && state.notice?.startsWith("Transfer created") == true) {
            showTransferDialog = false
        }
    }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Operations", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)
        OperationFilters(
            filter = state.filter,
            wallets = state.wallets,
            categories = state.categories,
            onFilterChanged = { filter -> viewModel.refresh(filter) },
        )

        Row(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Column(
                modifier = Modifier
                    .widthIn(min = 360.dp, max = 460.dp)
                    .fillMaxHeight(),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                AddOperationLauncher(
                    wallets = state.wallets,
                    onAddOperation = {
                        viewModel.clearFeedback()
                        showCreateDialog = true
                    },
                    onAddTransfer = {
                        viewModel.clearFeedback()
                        showTransferDialog = true
                    },
                    onImport = { viewModel.previewImportRecords(fileActions.openImportPath()) },
                    onExport = { confirmExport = true },
                    selectiveDeleteMode = state.selectiveDeleteMode,
                    selectedCount = state.selectedBulkRecordIds.size + state.selectedBulkTransferIds.size,
                    hasBulkDeleteCandidates = state.hasBulkDeleteCandidates,
                    onDeleteAll = { confirmDeleteAll = true },
                    onSelectiveDelete = viewModel::startSelectiveDelete,
                    onDeleteSelected = { confirmSelectiveDelete = true },
                    onCancelSelectiveDelete = viewModel::cancelSelectiveDelete,
                )
            }

            Column(
                modifier = Modifier.weight(1f).fillMaxHeight(),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (state.loading) {
                    CircularProgressIndicator()
                } else if (state.records.isEmpty()) {
                    Text("No operations for the selected filter.")
                } else {
                    val journalItems = operationJournalItems(
                        records = state.records,
                        selectedRecordId = state.selectedRecordId,
                        selectedBulkRecordIds = state.selectedBulkRecordIds,
                        selectedBulkTransferIds = state.selectedBulkTransferIds,
                        tagColors = state.tagColors,
                    )
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(journalItems, key = { it.key }) { item ->
                            OperationRow(
                                item = item,
                                selectiveDeleteMode = state.selectiveDeleteMode,
                                onClick = {
                                    if (state.selectiveDeleteMode) {
                                        if (item.transferId != null) {
                                            viewModel.toggleBulkTransfer(item.transferId)
                                        } else {
                                            item.selectableRecordId?.let(viewModel::toggleBulkRecord)
                                        }
                                    } else if (item.transferId != null) {
                                        viewModel.selectTransfer(item.transferId)
                                    } else {
                                        item.selectableRecordId?.let(viewModel::select)
                                    }
                                },
                            )
                        }
                    }
                }
            }
        }
    }

    if (showCreateDialog) {
        CreateOperationDialog(
            wallets = state.wallets,
            baseCurrency = state.baseCurrency,
            incomeCategorySuggestions = state.incomeCategories,
            expenseCategorySuggestions = state.expenseCategories,
            incomeDescriptionSuggestions = state.incomeDescriptionSuggestions,
            expenseDescriptionSuggestions = state.expenseDescriptionSuggestions,
            tagSuggestions = state.tags,
            tagColors = state.tagColors,
            tagPalette = state.tagPalette,
            engineError = state.error,
            submitting = state.loading,
            onSubmit = { request ->
                viewModel.create(request)
            },
            onCancel = { showCreateDialog = false },
        )
    }
    if (showTransferDialog) {
        CreateTransferDialog(
            wallets = state.wallets,
            baseCurrency = state.baseCurrency,
            descriptionSuggestions = state.descriptionSuggestions,
            engineError = state.error,
            submitting = state.loading,
            onSubmit = viewModel::createTransfer,
            onCancel = { showTransferDialog = false },
        )
    }
    state.editDraft?.let { draft ->
        EditOperationDialog(
            draft = draft,
            wallets = state.wallets,
            baseCurrency = state.baseCurrency,
            incomeCategorySuggestions = state.incomeCategories,
            expenseCategorySuggestions = state.expenseCategories,
            incomeDescriptionSuggestions = state.incomeDescriptionSuggestions,
            expenseDescriptionSuggestions = state.expenseDescriptionSuggestions,
            tagSuggestions = state.tags,
            tagColors = state.tagColors,
            tagPalette = state.tagPalette,
            onDraftChanged = viewModel::updateDraft,
            onSave = viewModel::updateSelected,
            onCancel = {
                confirmDelete = false
                viewModel.clearSelection()
            },
            onDelete = { confirmDelete = true },
        )
    }
    state.transferDraft?.let { draft ->
        EditTransferDialog(
            draft = draft,
            wallets = state.wallets,
            baseCurrency = state.baseCurrency,
            descriptionSuggestions = state.descriptionSuggestions,
            engineError = state.error,
            submitting = state.loading,
            onDraftChanged = viewModel::updateTransferDraft,
            onSave = viewModel::updateSelectedTransfer,
            onCancel = {
                confirmTransferDelete = false
                viewModel.clearSelection()
            },
            onDelete = { confirmTransferDelete = true },
        )
    }
    if (confirmTransferDelete && state.transferDraft != null) {
        DeleteTransferConfirmDialog(
            onConfirm = {
                confirmTransferDelete = false
                viewModel.deleteSelectedTransfer()
            },
            onCancel = { confirmTransferDelete = false },
        )
    }
    if (confirmDelete && state.selectedRecordId != null) {
        DeleteConfirmDialog(
            onConfirm = {
                confirmDelete = false
                viewModel.deleteSelected()
            },
            onCancel = { confirmDelete = false },
        )
    }
    if (confirmDeleteAll) {
        DeleteAllConfirmDialog(
            onConfirm = {
                confirmDeleteAll = false
                viewModel.deleteAllOperations()
            },
            onCancel = { confirmDeleteAll = false },
        )
    }
    if (confirmSelectiveDelete) {
        DeleteSelectedOperationsConfirmDialog(
            selectedCount = state.selectedBulkRecordIds.size + state.selectedBulkTransferIds.size,
            onConfirm = {
                confirmSelectiveDelete = false
                viewModel.deleteSelectedOperations()
            },
            onCancel = { confirmSelectiveDelete = false },
        )
    }
    if (confirmExport) {
        ExportOperationsConfirmDialog(
            onConfirm = {
                confirmExport = false
                viewModel.exportRecords(fileActions.saveExportPath())
            },
            onCancel = { confirmExport = false },
        )
    }
    state.importPreview?.let { preview ->
        ImportPreviewDialog(
            preview = preview,
            path = state.importPath.orEmpty(),
            submitting = state.loading,
            engineError = state.error,
            onConfirm = viewModel::confirmImportRecords,
            onCancel = viewModel::cancelImportPreview,
        )
    }
}

@Composable
private fun AddOperationLauncher(
    wallets: List<WalletOption>,
    onAddOperation: () -> Unit,
    onAddTransfer: () -> Unit,
    onImport: () -> Unit,
    onExport: () -> Unit,
    selectiveDeleteMode: Boolean,
    selectedCount: Int,
    hasBulkDeleteCandidates: Boolean,
    onDeleteAll: () -> Unit,
    onSelectiveDelete: () -> Unit,
    onDeleteSelected: () -> Unit,
    onCancelSelectiveDelete: () -> Unit,
) {
    val walletCount = wallets.size
    Card(Modifier.fillMaxWidth().fillMaxHeight()) {
        Column(
            Modifier
                .fillMaxHeight()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Operations", style = MaterialTheme.typography.titleMedium)
            Text("$walletCount active wallet${if (walletCount == 1) "" else "s"} available.")
            if (wallets.isNotEmpty()) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f)
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    wallets.forEach { wallet ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(wallet.name)
                            Text("${wallet.balance} ${wallet.currency}")
                        }
                    }
                }
            } else {
                Spacer(Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onAddOperation, enabled = walletCount > 0) {
                    Text("Add operation")
                }
                Button(onClick = onAddTransfer, enabled = walletCount >= 2) {
                    Text("Add transfer")
                }
            }
            Text("Journal actions", style = MaterialTheme.typography.titleSmall)
            if (selectiveDeleteMode) {
                Text("$selectedCount selected")
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = onDeleteSelected,
                        enabled = selectedCount > 0,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("Delete selected")
                    }
                    TextButton(onClick = onCancelSelectiveDelete, modifier = Modifier.weight(1f)) {
                        Text("Cancel")
                    }
                }
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = onImport, modifier = Modifier.weight(1f)) {
                        Text("Import")
                    }
                    TextButton(onClick = onExport, modifier = Modifier.weight(1f)) {
                        Text("Export")
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(
                        onClick = onDeleteAll,
                        enabled = hasBulkDeleteCandidates,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("Delete all")
                    }
                    TextButton(
                        onClick = onSelectiveDelete,
                        enabled = hasBulkDeleteCandidates,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("Selective delete")
                    }
                }
            }
        }
    }
}

@Composable
private fun OperationFilters(
    filter: OperationFilter,
    wallets: List<WalletOption>,
    categories: List<String>,
    onFilterChanged: (OperationFilter) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = filter.recordType == null,
                onClick = { onFilterChanged(filter.copy(recordType = null)) },
                label = { Text("All") },
            )
            FilterChip(
                selected = filter.recordType == "income",
                onClick = { onFilterChanged(filter.copy(recordType = "income")) },
                label = { Text("Income") },
            )
            FilterChip(
                selected = filter.recordType == "expense",
                onClick = { onFilterChanged(filter.copy(recordType = "expense")) },
                label = { Text("Expense") },
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LedgerDateField(
                modifier = Modifier.weight(1f),
                value = filter.startDate.orEmpty(),
                onValueChange = { onFilterChanged(filter.copy(startDate = it.ifBlank { null })) },
                label = "From",
                required = false,
                allowFuture = false,
            )
            LedgerDateField(
                modifier = Modifier.weight(1f),
                value = filter.endDate.orEmpty(),
                onValueChange = { onFilterChanged(filter.copy(endDate = it.ifBlank { null })) },
                label = "To",
                required = false,
                allowFuture = false,
            )
        }
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterChip(
                selected = filter.walletId == null,
                onClick = { onFilterChanged(filter.copy(walletId = null)) },
                label = { Text("All wallets") },
            )
            wallets.forEach { wallet ->
                FilterChip(
                    selected = filter.walletId == wallet.id,
                    onClick = { onFilterChanged(filter.copy(walletId = wallet.id)) },
                    label = { Text(wallet.name) },
                )
            }
        }
        if (categories.isNotEmpty()) {
            Text("Categories: ${categories.joinToString(", ")}", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun CreateTransferDialog(
    wallets: List<WalletOption>,
    baseCurrency: String,
    descriptionSuggestions: List<String>,
    engineError: String?,
    submitting: Boolean,
    onSubmit: (CreateTransferRequest) -> Unit,
    onCancel: () -> Unit,
) {
    var fromWalletId by remember { mutableStateOf(wallets.firstOrNull()?.id ?: 0L) }
    var toWalletId by remember { mutableStateOf(wallets.drop(1).firstOrNull()?.id ?: 0L) }
    var date by remember { mutableStateOf(todayText()) }
    var amount by remember { mutableStateOf("") }
    var currency by remember { mutableStateOf(baseCurrency) }
    var commissionAmount by remember { mutableStateOf("0") }
    var commissionCurrency by remember { mutableStateOf(baseCurrency) }
    var description by remember { mutableStateOf("") }

    LaunchedEffect(wallets, baseCurrency) {
        if (wallets.none { it.id == fromWalletId }) {
            fromWalletId = wallets.firstOrNull()?.id ?: 0L
        }
        if (wallets.none { it.id == toWalletId } || toWalletId == fromWalletId) {
            toWalletId = wallets.firstOrNull { it.id != fromWalletId }?.id ?: 0L
        }
        if (currency.isBlank()) {
            currency = baseCurrency
        }
        if (commissionCurrency.isBlank()) {
            commissionCurrency = baseCurrency
        }
    }

    val validationError = OperationValidation.validateTransferFields(
        fromWalletId = fromWalletId,
        toWalletId = toWalletId,
        date = date,
        amount = amount,
        currency = currency,
        commissionAmount = commissionAmount,
        commissionCurrency = commissionCurrency,
        baseCurrency = baseCurrency,
    )

    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Add transfer") },
        text = {
            Column(
                modifier = dialogFormModifier(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (wallets.size < 2) {
                    Text(
                        "At least two active wallets are required to create a transfer.",
                        color = MaterialTheme.colorScheme.error,
                    )
                } else {
                    Text("From wallet", style = MaterialTheme.typography.labelLarge)
                    WalletChips(wallets, fromWalletId) { wallet ->
                        fromWalletId = wallet.id
                        if (toWalletId == wallet.id) {
                            toWalletId = wallets.firstOrNull { it.id != wallet.id }?.id ?: 0L
                        }
                    }
                    Text("To wallet", style = MaterialTheme.typography.labelLarge)
                    WalletChips(wallets, toWalletId) { wallet ->
                        toWalletId = wallet.id
                    }
                }
                LedgerDateField(
                    modifier = dialogFieldModifier(),
                    value = date,
                    onValueChange = { date = it },
                    label = "Date",
                    allowFuture = false,
                )
                OutlinedTextField(
                    modifier = dialogFieldModifier(),
                    value = amount,
                    onValueChange = { amount = it },
                    label = { Text("Amount") },
                    singleLine = true,
                )
                OutlinedTextField(
                    modifier = dialogFieldModifier(),
                    value = currency,
                    onValueChange = { currency = OperationValidation.normalizeCurrency(it) },
                    label = { Text("Currency") },
                    singleLine = true,
                )
                OutlinedTextField(
                    modifier = dialogFieldModifier(),
                    value = commissionAmount,
                    onValueChange = { commissionAmount = it },
                    label = { Text("Commission") },
                    singleLine = true,
                )
                OutlinedTextField(
                    modifier = dialogFieldModifier(),
                    value = commissionCurrency,
                    onValueChange = { commissionCurrency = OperationValidation.normalizeCurrency(it) },
                    label = { Text("Commission currency") },
                    singleLine = true,
                )
                AutocompleteTextField(
                    modifier = dialogFieldModifier(),
                    value = description,
                    onValueChange = { description = it },
                    label = "Description",
                    suggestions = descriptionSuggestions,
                    menuWidth = DialogContentWidth,
                    showSuggestionsOnBlank = false,
                )
                (validationError ?: engineError)?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSubmit(
                        CreateTransferRequest(
                            fromWalletId = fromWalletId,
                            toWalletId = toWalletId,
                            date = date,
                            amount = amount,
                            currency = currency,
                            description = description,
                            commissionAmount = commissionAmount.ifBlank { "0" },
                            commissionCurrency = commissionCurrency.ifBlank { baseCurrency },
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

@Composable
private fun WalletChips(
    wallets: List<WalletOption>,
    selectedWalletId: Long,
    onWalletChanged: (WalletOption) -> Unit,
) {
    Row(
        modifier = Modifier.width(DialogContentWidth).horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        wallets.forEach { wallet ->
            FilterChip(
                selected = wallet.id == selectedWalletId,
                onClick = { onWalletChanged(wallet) },
                label = { Text("${wallet.name} · ${wallet.currency}") },
            )
        }
    }
}

@Composable
private fun CreateOperationDialog(
    wallets: List<WalletOption>,
    baseCurrency: String,
    incomeCategorySuggestions: List<String>,
    expenseCategorySuggestions: List<String>,
    incomeDescriptionSuggestions: List<String>,
    expenseDescriptionSuggestions: List<String>,
    tagSuggestions: List<String>,
    tagColors: Map<String, String>,
    tagPalette: List<String>,
    engineError: String?,
    submitting: Boolean,
    onSubmit: (CreateOperationRequest) -> Unit,
    onCancel: () -> Unit,
) {
    var type by remember { mutableStateOf("income") }
    var date by remember { mutableStateOf(todayText()) }
    var amount by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var tags by remember { mutableStateOf("") }
    var selectedTagColors by remember { mutableStateOf(tagColors) }
    var walletId by remember { mutableStateOf(wallets.firstOrNull()?.id ?: 0L) }
    var currency by remember { mutableStateOf(baseCurrency) }

    LaunchedEffect(wallets, baseCurrency) {
        if (wallets.none { it.id == walletId }) {
            walletId = wallets.firstOrNull()?.id ?: 0L
        }
        if (currency.isBlank()) {
            currency = baseCurrency
        }
    }

    val validationError = OperationValidation.validateFields(
        type = type,
        date = date,
        walletId = walletId,
        amountOriginal = amount,
        currency = currency,
        category = category,
        tagsText = tags,
        baseCurrency = baseCurrency,
    )

    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Add operation") },
        text = {
            CreateOperationForm(
                wallets = wallets,
                type = type,
                date = date,
                amount = amount,
                category = category,
                description = description,
                tags = tags,
                walletId = walletId,
                currency = currency,
                categorySuggestions = if (type == "income") incomeCategorySuggestions else expenseCategorySuggestions,
                descriptionSuggestions = if (type == "income") {
                    incomeDescriptionSuggestions
                } else {
                    expenseDescriptionSuggestions
                },
                tagSuggestions = tagSuggestions,
                tagColors = selectedTagColors,
                tagPalette = tagPalette,
                validationError = validationError,
                engineError = engineError,
                onTypeChanged = { type = it },
                onDateChanged = { date = it },
                onAmountChanged = { amount = it },
                onCategoryChanged = { category = it },
                onDescriptionChanged = { description = it },
                onTagsChanged = { tags = it },
                onTagColorChanged = { name, color ->
                    selectedTagColors = selectedTagColors + (name.lowercase() to color)
                },
                onWalletChanged = { wallet ->
                    walletId = wallet.id
                    if (currency.isBlank()) {
                        currency = baseCurrency
                    }
                },
                onCurrencyChanged = { currency = OperationValidation.normalizeCurrency(it) },
            )
        },
        confirmButton = {
            Button(
                onClick = {
                    onSubmit(
                        CreateOperationRequest(
                            type = type,
                            date = date,
                            walletId = walletId,
                            amountOriginal = amount,
                            currency = currency,
                            rateAtOperation = "1",
                            amountBase = amount,
                            category = category,
                            description = description,
                            tags = OperationValidation.parseTags(tags),
                            tagColors = selectedTagColors,
                        )
                    )
                },
                enabled = validationError == null && !submitting,
            ) {
                Text(if (submitting) "Adding..." else "Add")
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

private fun todayText(): String {
    val today = currentLedgerDate()
    return "${today.day.toString().padStart(2, '0')}.${today.month.toString().padStart(2, '0')}.${today.year.toString().padStart(4, '0')}"
}

@Composable
private fun CreateOperationForm(
    wallets: List<WalletOption>,
    type: String,
    date: String,
    amount: String,
    category: String,
    description: String,
    tags: String,
    walletId: Long,
    currency: String,
    categorySuggestions: List<String>,
    descriptionSuggestions: List<String>,
    tagSuggestions: List<String>,
    tagColors: Map<String, String>,
    tagPalette: List<String>,
    validationError: String?,
    engineError: String?,
    onTypeChanged: (String) -> Unit,
    onDateChanged: (String) -> Unit,
    onAmountChanged: (String) -> Unit,
    onCategoryChanged: (String) -> Unit,
    onDescriptionChanged: (String) -> Unit,
    onTagsChanged: (String) -> Unit,
    onTagColorChanged: (String, String) -> Unit,
    onWalletChanged: (WalletOption) -> Unit,
    onCurrencyChanged: (String) -> Unit,
) {
    Column(
        modifier = dialogFormModifier(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (wallets.isEmpty()) {
            Text(
                "No active wallets found in the selected database. Create or copy a ledger DB with at least one wallet.",
                color = MaterialTheme.colorScheme.error,
            )
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(type == "income", { onTypeChanged("income") }, label = { Text("Income") })
                FilterChip(type == "expense", { onTypeChanged("expense") }, label = { Text("Expense") })
            }
            Text("Wallet", style = MaterialTheme.typography.labelLarge)
            Row(
                modifier = Modifier.width(DialogContentWidth).horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                wallets.forEach { wallet ->
                    FilterChip(
                        selected = wallet.id == walletId,
                        onClick = { onWalletChanged(wallet) },
                        label = { Text("${wallet.name} · ${wallet.currency}") },
                    )
                }
            }
        }
        LedgerDateField(
            modifier = dialogFieldModifier(),
            value = date,
            onValueChange = onDateChanged,
            label = "Date",
            allowFuture = false,
        )
        OutlinedTextField(
            modifier = dialogFieldModifier(),
            value = amount,
            onValueChange = onAmountChanged,
            label = { Text("Amount") },
            singleLine = true,
        )
        OutlinedTextField(
            modifier = dialogFieldModifier(),
            value = currency,
            onValueChange = onCurrencyChanged,
            label = { Text("Currency") },
            singleLine = true,
        )
        AutocompleteTextField(
            modifier = dialogFieldModifier(),
            value = category,
            onValueChange = onCategoryChanged,
            label = "Category",
            suggestions = categorySuggestions,
            menuWidth = DialogContentWidth,
        )
        AutocompleteTextField(
            modifier = dialogFieldModifier(),
            value = description,
            onValueChange = onDescriptionChanged,
            label = "Description",
            suggestions = descriptionSuggestions,
            menuWidth = DialogContentWidth,
            showSuggestionsOnBlank = false,
        )
        TagAutocompleteField(
            modifier = dialogFieldModifier(),
            value = tags,
            onValueChange = onTagsChanged,
            suggestions = tagSuggestions,
            menuWidth = DialogContentWidth,
            tagColors = tagColors,
            palette = tagPalette,
            onTagColorChanged = onTagColorChanged,
        )
        (validationError ?: engineError)?.let {
            Text(it, color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun EditOperationDialog(
    draft: OperationDraft,
    wallets: List<WalletOption>,
    baseCurrency: String,
    incomeCategorySuggestions: List<String>,
    expenseCategorySuggestions: List<String>,
    incomeDescriptionSuggestions: List<String>,
    expenseDescriptionSuggestions: List<String>,
    tagSuggestions: List<String>,
    tagColors: Map<String, String>,
    tagPalette: List<String>,
    onDraftChanged: (OperationDraft) -> Unit,
    onSave: () -> Unit,
    onCancel: () -> Unit,
    onDelete: () -> Unit,
) {
    val validationError = OperationValidation.validateFields(
        type = draft.type,
        date = draft.date,
        walletId = draft.walletId,
        amountOriginal = draft.amountOriginal,
        currency = draft.currency,
        category = draft.category,
        tagsText = draft.tagsText,
        baseCurrency = baseCurrency,
    )

    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Edit operation") },
        text = {
            Column(
                modifier = dialogFormModifier(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                EditOperationFields(
                    draft = draft,
                    wallets = wallets,
                    categorySuggestions = if (draft.type == "income") {
                        incomeCategorySuggestions
                    } else {
                        expenseCategorySuggestions
                    },
                    descriptionSuggestions = if (draft.type == "income") {
                        incomeDescriptionSuggestions
                    } else {
                        expenseDescriptionSuggestions
                    },
                    tagSuggestions = tagSuggestions,
                    tagColors = draft.tagColors.ifEmpty { tagColors },
                    tagPalette = tagPalette,
                    onDraftChanged = onDraftChanged,
                )
                validationError?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onDelete) { Text("Delete") }
                Button(onClick = onSave, enabled = validationError == null) { Text("Save") }
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

@Composable
private fun EditOperationFields(
    draft: OperationDraft,
    wallets: List<WalletOption>,
    categorySuggestions: List<String>,
    descriptionSuggestions: List<String>,
    tagSuggestions: List<String>,
    tagColors: Map<String, String>,
    tagPalette: List<String>,
    onDraftChanged: (OperationDraft) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(draft.type == "income", { onDraftChanged(draft.copy(type = "income")) }, label = { Text("Income") })
            FilterChip(draft.type == "expense", { onDraftChanged(draft.copy(type = "expense")) }, label = { Text("Expense") })
        }
        Row(
            modifier = Modifier.width(DialogContentWidth).horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            wallets.forEach { wallet ->
                FilterChip(
                    selected = wallet.id == draft.walletId,
                    onClick = {
                        onDraftChanged(draft.copy(walletId = wallet.id))
                    },
                    label = { Text("${wallet.name} · ${wallet.currency}") },
                )
            }
        }
        LedgerDateField(
            modifier = dialogFieldModifier(),
            value = draft.date,
            onValueChange = { onDraftChanged(draft.copy(date = it)) },
            label = "Date",
            allowFuture = false,
        )
        OutlinedTextField(
            modifier = dialogFieldModifier(),
            value = draft.amountOriginal,
            onValueChange = { onDraftChanged(draft.copy(amountOriginal = it)) },
            label = { Text("Amount") },
            singleLine = true,
        )
        OutlinedTextField(
            modifier = dialogFieldModifier(),
            value = draft.currency,
            onValueChange = { onDraftChanged(draft.copy(currency = OperationValidation.normalizeCurrency(it))) },
            label = { Text("Currency") },
            singleLine = true,
        )
        AutocompleteTextField(
            modifier = dialogFieldModifier(),
            value = draft.category,
            onValueChange = { onDraftChanged(draft.copy(category = it)) },
            label = "Category",
            suggestions = categorySuggestions,
            menuWidth = DialogContentWidth,
        )
        AutocompleteTextField(
            modifier = dialogFieldModifier(),
            value = draft.description,
            onValueChange = { onDraftChanged(draft.copy(description = it)) },
            label = "Description",
            suggestions = descriptionSuggestions,
            menuWidth = DialogContentWidth,
            showSuggestionsOnBlank = false,
        )
        TagAutocompleteField(
            modifier = dialogFieldModifier(),
            value = draft.tagsText,
            onValueChange = { onDraftChanged(draft.copy(tagsText = it)) },
            suggestions = tagSuggestions,
            menuWidth = DialogContentWidth,
            tagColors = tagColors,
            palette = tagPalette,
            onTagColorChanged = { name, color ->
                onDraftChanged(draft.copy(tagColors = draft.tagColors + (name.lowercase() to color)))
            },
        )
    }
}

@Composable
private fun EditTransferDialog(
    draft: TransferDraft,
    wallets: List<WalletOption>,
    baseCurrency: String,
    descriptionSuggestions: List<String>,
    engineError: String?,
    submitting: Boolean,
    onDraftChanged: (TransferDraft) -> Unit,
    onSave: () -> Unit,
    onCancel: () -> Unit,
    onDelete: () -> Unit,
) {
    val validationError = OperationValidation.validateTransferFields(
        fromWalletId = draft.fromWalletId,
        toWalletId = draft.toWalletId,
        date = draft.date,
        amount = draft.amount,
        currency = draft.currency,
        commissionAmount = "0",
        commissionCurrency = baseCurrency,
        baseCurrency = baseCurrency,
    )

    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Edit transfer #${draft.id}") },
        text = {
            Column(
                modifier = dialogFormModifier(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("From wallet", style = MaterialTheme.typography.labelLarge)
                WalletChips(wallets, draft.fromWalletId) { wallet ->
                    val nextToWallet = if (draft.toWalletId == wallet.id) {
                        wallets.firstOrNull { it.id != wallet.id }?.id ?: 0L
                    } else {
                        draft.toWalletId
                    }
                    onDraftChanged(draft.copy(fromWalletId = wallet.id, toWalletId = nextToWallet))
                }
                Text("To wallet", style = MaterialTheme.typography.labelLarge)
                WalletChips(wallets, draft.toWalletId) { wallet ->
                    onDraftChanged(draft.copy(toWalletId = wallet.id))
                }
                LedgerDateField(
                    modifier = dialogFieldModifier(),
                    value = draft.date,
                    onValueChange = { onDraftChanged(draft.copy(date = it)) },
                    label = "Date",
                    allowFuture = false,
                )
                OutlinedTextField(
                    modifier = dialogFieldModifier(),
                    value = draft.amount,
                    onValueChange = { onDraftChanged(draft.copy(amount = it)) },
                    label = { Text("Amount") },
                    singleLine = true,
                )
                OutlinedTextField(
                    modifier = dialogFieldModifier(),
                    value = draft.currency,
                    onValueChange = {
                        onDraftChanged(draft.copy(currency = OperationValidation.normalizeCurrency(it)))
                    },
                    label = { Text("Currency") },
                    singleLine = true,
                )
                AutocompleteTextField(
                    modifier = dialogFieldModifier(),
                    value = draft.description,
                    onValueChange = { onDraftChanged(draft.copy(description = it)) },
                    label = "Description",
                    suggestions = descriptionSuggestions,
                    menuWidth = DialogContentWidth,
                    showSuggestionsOnBlank = false,
                )
                Text(
                    "Transfer commission is edited as a standalone operation and deleted with the transfer.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                (validationError ?: engineError)?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onDelete, enabled = !submitting) { Text("Delete") }
                Button(onClick = onSave, enabled = validationError == null && !submitting) {
                    Text(if (submitting) "Saving..." else "Save")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

private val DialogContentWidth = 360.dp

private fun dialogFieldModifier(): Modifier = Modifier.fillMaxWidth()

@Composable
private fun dialogFormModifier(): Modifier =
    Modifier
        .width(DialogContentWidth)
        .heightIn(max = 560.dp)
        .verticalScroll(rememberScrollState())

@Composable
private fun DeleteConfirmDialog(onConfirm: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Delete operation") },
        text = { Text("Delete selected standalone operation?") },
        confirmButton = {
            Button(onClick = onConfirm) { Text("Delete") }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

@Composable
private fun DeleteTransferConfirmDialog(onConfirm: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Delete transfer") },
        text = { Text("Delete selected transfer and linked operation rows?") },
        confirmButton = {
            Button(onClick = onConfirm) { Text("Delete") }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

@Composable
private fun DeleteAllConfirmDialog(onConfirm: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Delete all operations") },
        text = {
            Text(
                "Delete all standalone operations, generated mandatory rows, transfers, and debt-linked operation rows? Matching debt payment history rows will be removed too. Unsupported rows will be kept."
            )
        },
        confirmButton = {
            Button(onClick = onConfirm) { Text("Delete all") }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

@Composable
private fun DeleteSelectedOperationsConfirmDialog(
    selectedCount: Int,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Delete selected operations") },
        text = { Text("Delete $selectedCount selected operations and transfers?") },
        confirmButton = {
            Button(onClick = onConfirm, enabled = selectedCount > 0) { Text("Delete selected") }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text("Cancel") }
        },
    )
}

@Composable
private fun ExportOperationsConfirmDialog(onConfirm: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Export operations") },
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
private fun ImportPreviewDialog(
    preview: OperationImportResult,
    path: String,
    submitting: Boolean,
    engineError: String?,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text("Import preview") },
        text = {
            Column(
                Modifier.width(DialogContentWidth).heightIn(max = 420.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(path, style = MaterialTheme.typography.bodySmall)
                Text("Rows to import: ${preview.imported}")
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
                    "Current standalone operations and transfers will be replaced. Verified debt-linked rows replace their source operation rows; unsupported linked rows are kept.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            Button(onClick = onConfirm, enabled = !submitting && preview.imported > 0 && !preview.blockingErrors) {
                Text("Import")
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel, enabled = !submitting) { Text("Cancel") }
        },
    )
}

@Composable
private fun OperationRow(
    item: OperationJournalItem,
    selectiveDeleteMode: Boolean,
    onClick: () -> Unit,
) {
    Card(
        Modifier
            .fillMaxWidth()
            .clickable(enabled = !selectiveDeleteMode || item.bulkSelectable, onClick = onClick)
    ) {
        Row(Modifier.padding(14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (selectiveDeleteMode) {
                Checkbox(
                    checked = item.selected,
                    onCheckedChange = { onClick() },
                    enabled = item.bulkSelectable,
                )
            }
            Column(Modifier.weight(1f)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(
                        item.title,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(item.amount)
                }
                Spacer(Modifier.height(4.dp))
                Text(item.meta)
                if (item.linkedLabel != null) {
                    Text(
                        item.linkedLabel,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (selectiveDeleteMode && !item.bulkSelectable) {
                    Text(
                        "Linked record is kept",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (item.description.isNotBlank()) {
                    Text(item.description)
                }
                if (item.tags.isNotEmpty()) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        modifier = Modifier.padding(top = 2.dp),
                    ) {
                        item.tags.forEach { tag ->
                            Box(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(percent = 50))
                                    .background(
                                        item.tagColors[tag.lowercase()]
                                            ?.toComposeTagColor()
                                            ?: MaterialTheme.colorScheme.outline,
                                    )
                                    .padding(horizontal = 8.dp, vertical = 4.dp),
                            ) {
                                Text(
                                    "#$tag",
                                    color = Color.White,
                                    style = MaterialTheme.typography.labelMedium,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
