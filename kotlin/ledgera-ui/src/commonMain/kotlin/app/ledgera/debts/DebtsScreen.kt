package app.ledgera.debts

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
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
import androidx.compose.material3.Checkbox
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
import app.ledgera.model.DebtActionDraft
import app.ledgera.model.DebtDraft
import app.ledgera.model.DebtItem
import app.ledgera.model.DebtPaymentItem
import app.ledgera.model.WalletOption
import app.ledgera.ui.LedgerDateField

@Composable
fun DebtsScreen(viewModel: DebtsViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    Box(modifier = modifier.fillMaxSize()) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Debts", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Bold)

        Column(
            Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                DebtsListCard(
                    debts = state.debts,
                    selectedDebtId = state.selectedDebtId,
                    loading = state.loading,
                    onSelectDebt = viewModel::selectDebt,
                    modifier = Modifier.weight(0.58f),
                )
                DebtHistoryCard(
                    selectedDebt = state.debts.firstOrNull { it.id == state.selectedDebtId },
                    history = state.selectedHistory,
                    onPay = { viewModel.openDebtAction("payment") },
                    onWriteOff = { viewModel.openDebtAction("write_off") },
                    onClose = { viewModel.openDebtAction("close") },
                    onDeleteDebt = viewModel::requestDeleteSelectedDebt,
                    onDeletePayment = viewModel::requestDeletePayment,
                    modifier = Modifier.weight(0.42f),
                )
            }
        }

        DebtCreateFab(
            modifier = Modifier.align(Alignment.BottomEnd).padding(32.dp),
            onCreateDebt = { viewModel.openCreateDialog("debt") },
            onCreateLoan = { viewModel.openCreateDialog("loan") },
        )

        state.createDraft?.let { draft ->
            CreateDebtDialog(
                draft = draft,
                wallets = state.wallets,
                baseCurrency = state.baseCurrency,
                engineError = state.error,
                submitting = state.createInProgress,
                onDraftChange = viewModel::updateDraft,
                onSubmit = viewModel::createDebt,
                onCancel = viewModel::closeCreateDialog,
            )
        }

        state.actionDraft?.let { draft ->
            DebtActionDialog(
                draft = draft,
                wallets = state.wallets,
                selectedDebt = state.debts.firstOrNull { it.id == draft.debtId },
                engineError = state.error,
                submitting = state.actionInProgress,
                onDraftChange = viewModel::updateActionDraft,
                onSubmit = viewModel::submitDebtAction,
                onCancel = viewModel::closeActionDialog,
            )
        }

        state.deleteDebtId?.let { debtId ->
            state.debts.firstOrNull { it.id == debtId }?.let { debt ->
                DeleteDebtConfirmDialog(
                    debt = debt,
                    engineError = state.error,
                    submitting = state.deleteInProgress,
                    onConfirm = viewModel::deleteSelectedDebt,
                    onCancel = viewModel::closeDeleteDebtDialog,
                )
            }
        }

        state.deletePayment?.let { payment ->
            DeletePaymentConfirmDialog(
                payment = payment,
                deleteLinkedRecord = state.deleteLinkedRecord,
                engineError = state.error,
                submitting = state.deleteInProgress,
                onDeleteLinkedRecordChange = viewModel::updateDeleteLinkedRecord,
                onConfirm = viewModel::deleteSelectedPayment,
                onCancel = viewModel::closeDeletePaymentDialog,
            )
        }
    }
}

@Composable
private fun DebtCreateFab(
    onCreateDebt: () -> Unit,
    onCreateLoan: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.End,
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        AnimatedVisibility(
            visible = expanded,
            enter = fadeIn() + slideInVertically(initialOffsetY = { it / 2 }),
            exit = fadeOut() + slideOutVertically(targetOffsetY = { it / 2 }),
        ) {
            Column(
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                FloatingActionButton(
                    onClick = {
                        expanded = false
                        onCreateLoan()
                    },
                    containerColor = MaterialTheme.colorScheme.tertiary,
                    contentColor = MaterialTheme.colorScheme.onTertiary,
                ) {
                    Text("Loan", fontWeight = FontWeight.Bold)
                }
                FloatingActionButton(
                    onClick = {
                        expanded = false
                        onCreateDebt()
                    },
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                ) {
                    Text("Debt", fontWeight = FontWeight.Bold)
                }
            }
        }
        FloatingActionButton(
            onClick = { expanded = !expanded },
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
        ) {
            Text(if (expanded) "×" else "+", style = MaterialTheme.typography.headlineMedium)
        }
    }
}

@Composable
private fun DebtsListCard(
    debts: List<DebtItem>,
    selectedDebtId: Long?,
    loading: Boolean,
    onSelectDebt: (Long) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Open and closed debts", style = MaterialTheme.typography.titleMedium)
            if (loading && debts.isEmpty()) {
                CircularProgressIndicator()
            } else if (debts.isEmpty()) {
                Text("No debts or loans found in the selected database.")
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(debts, key = { it.id }) { debt ->
                        DebtRow(
                            debt = debt,
                            selected = debt.id == selectedDebtId,
                            onClick = { onSelectDebt(debt.id) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DebtRow(debt: DebtItem, selected: Boolean, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) {
                MaterialTheme.colorScheme.secondaryContainer
            } else {
                MaterialTheme.colorScheme.surface
            },
        ),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(debt.contactName, fontWeight = FontWeight.SemiBold)
                Text("${debt.remainingAmount} / ${debt.totalAmount} ${debt.currency}")
            }
            Text("${debt.kindLabel()} · ${debt.status} · created ${debt.createdAt}")
            debt.closedAt?.let {
                Text("closed $it", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun DebtHistoryCard(
    selectedDebt: DebtItem?,
    history: List<DebtPaymentItem>,
    onPay: () -> Unit,
    onWriteOff: () -> Unit,
    onClose: () -> Unit,
    onDeleteDebt: () -> Unit,
    onDeletePayment: (DebtPaymentItem) -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("History", style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val actionsEnabled = selectedDebt != null && selectedDebt.status != "closed"
                    OutlinedButton(onClick = onPay, enabled = actionsEnabled) { Text("Pay") }
                    OutlinedButton(onClick = onWriteOff, enabled = actionsEnabled) { Text("Write off") }
                    Button(onClick = onClose, enabled = actionsEnabled) { Text("Close") }
                    OutlinedButton(onClick = onDeleteDebt, enabled = selectedDebt != null) { Text("Delete debt") }
                }
            }
            if (selectedDebt == null) {
                Text("Select a debt or loan to view history.")
            } else if (history.isEmpty()) {
                Text("No payments registered for ${selectedDebt.contactName}.")
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(history, key = { it.id }) { payment ->
                        PaymentRow(payment, onDelete = { onDeletePayment(payment) })
                    }
                }
            }
        }
    }
}

@Composable
private fun PaymentRow(payment: DebtPaymentItem, onDelete: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(payment.operationType)
                Text(
                    payment.paymentDate + if (payment.isWriteOff) " · write-off" else "",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(payment.principalPaid)
                TextButton(onClick = onDelete) {
                    Text("Delete")
                }
            }
        }
    }
}

@Composable
private fun DeleteDebtConfirmDialog(
    debt: DebtItem,
    engineError: String?,
    submitting: Boolean,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text(if (debt.kind == "loan") "Delete loan" else "Delete debt") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Delete selected debt or loan? Linked operation rows will be kept as standalone records. Payment history will be removed.")
                Text("${debt.contactName} · ${debt.remainingAmount} / ${debt.totalAmount} ${debt.currency}")
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(onClick = onConfirm, enabled = !submitting) {
                Text(if (submitting) "Deleting..." else "Delete")
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
private fun DeletePaymentConfirmDialog(
    payment: DebtPaymentItem,
    deleteLinkedRecord: Boolean,
    engineError: String?,
    submitting: Boolean,
    onDeleteLinkedRecordChange: (Boolean) -> Unit,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text("Delete payment") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Delete selected payment? The debt or loan remaining amount will be recalculated.")
                Text("${payment.paymentDate} · ${payment.principalPaid}")
                if (payment.recordId != null) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = deleteLinkedRecord,
                            onCheckedChange = onDeleteLinkedRecordChange,
                            enabled = !submitting,
                        )
                        Text("Delete linked operation row too")
                    }
                } else {
                    Text("This payment has no linked operation row.")
                }
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(onClick = onConfirm, enabled = !submitting) {
                Text(if (submitting) "Deleting..." else "Delete")
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
private fun CreateDebtDialog(
    draft: DebtDraft,
    wallets: List<WalletOption>,
    baseCurrency: String,
    engineError: String?,
    submitting: Boolean,
    onDraftChange: (DebtDraft) -> Unit,
    onSubmit: () -> Unit,
    onCancel: () -> Unit,
) {
    val validationError = DebtsValidation.validateCreateDraft(draft, baseCurrency)
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text(if (draft.kind == "loan") "Add loan" else "Add debt") },
        text = {
            Column(
                Modifier.widthIn(min = 420.dp, max = 520.dp)
                    .heightIn(max = 640.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text("Wallet", fontWeight = FontWeight.SemiBold)
                Row(
                    Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    wallets.forEach { wallet ->
                        val selected = wallet.id == draft.walletId
                        if (selected) {
                            Button(onClick = { onDraftChange(draft.copy(walletId = wallet.id)) }) {
                                Text("${wallet.name} · ${wallet.currency}")
                            }
                        } else {
                            OutlinedButton(onClick = { onDraftChange(draft.copy(walletId = wallet.id)) }) {
                                Text("${wallet.name} · ${wallet.currency}")
                            }
                        }
                    }
                }
                KindSelector(draft, onDraftChange)
                OutlinedTextField(
                    value = draft.contactName,
                    onValueChange = { onDraftChange(draft.copy(contactName = it.lineSafe())) },
                    label = { Text("Contact") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                LedgerDateField(
                    value = draft.createdAt,
                    onValueChange = { onDraftChange(draft.copy(createdAt = it.lineSafe())) },
                    modifier = Modifier.fillMaxWidth(),
                    label = "Date",
                    allowFuture = false,
                    showErrorOutline = false,
                    showErrorText = false,
                )
                OutlinedTextField(
                    value = draft.amount,
                    onValueChange = { onDraftChange(draft.copy(amount = it.lineSafe())) },
                    label = { Text("Amount") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = draft.currency,
                    onValueChange = { onDraftChange(draft.copy(currency = it.lineSafe().uppercase())) },
                    label = { Text("Currency") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = draft.description,
                    onValueChange = { onDraftChange(draft.copy(description = it.lineSafe())) },
                    label = { Text("Description") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                validationError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(onClick = onSubmit, enabled = !submitting && validationError == null) {
                Text(if (submitting) "Saving..." else "Create")
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
private fun DebtActionDialog(
    draft: DebtActionDraft,
    wallets: List<WalletOption>,
    selectedDebt: DebtItem?,
    engineError: String?,
    submitting: Boolean,
    onDraftChange: (DebtActionDraft) -> Unit,
    onSubmit: () -> Unit,
    onCancel: () -> Unit,
) {
    val requiresWallet = draft.action != "write_off"
    val validationError = DebtsValidation.validateActionDraft(draft, requiresWallet)
    val title = when (draft.action) {
        "write_off" -> "Write off debt"
        "close" -> "Close debt"
        else -> "Register payment"
    }
    AlertDialog(
        onDismissRequest = { if (!submitting) onCancel() },
        title = { Text(title) },
        text = {
            Column(
                Modifier.widthIn(min = 420.dp, max = 520.dp)
                    .heightIn(max = 560.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                selectedDebt?.let {
                    Text("${it.contactName} · ${it.remainingAmount} ${it.currency} remaining")
                }
                if (requiresWallet) {
                    Text("Wallet", fontWeight = FontWeight.SemiBold)
                    Row(
                        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        wallets.forEach { wallet ->
                            val selected = wallet.id == draft.walletId
                            if (selected) {
                                Button(onClick = { onDraftChange(draft.copy(walletId = wallet.id)) }) {
                                    Text("${wallet.name} · ${wallet.currency}")
                                }
                            } else {
                                OutlinedButton(onClick = { onDraftChange(draft.copy(walletId = wallet.id)) }) {
                                    Text("${wallet.name} · ${wallet.currency}")
                                }
                            }
                        }
                    }
                }
                LedgerDateField(
                    value = draft.paymentDate,
                    onValueChange = { onDraftChange(draft.copy(paymentDate = it.lineSafe())) },
                    modifier = Modifier.fillMaxWidth(),
                    label = "Date",
                    allowFuture = false,
                    showErrorOutline = false,
                    showErrorText = false,
                )
                OutlinedTextField(
                    value = draft.amount,
                    onValueChange = {
                        if (draft.action != "close") {
                            onDraftChange(draft.copy(amount = it.lineSafe()))
                        }
                    },
                    label = { Text(if (draft.action == "close") "Remaining amount" else "Amount") },
                    singleLine = true,
                    readOnly = draft.action == "close",
                    modifier = Modifier.fillMaxWidth(),
                )
                if (draft.action != "write_off") {
                    OutlinedTextField(
                        value = draft.description,
                        onValueChange = { onDraftChange(draft.copy(description = it.lineSafe())) },
                        label = { Text("Description") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                validationError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                engineError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(onClick = onSubmit, enabled = !submitting && validationError == null) {
                Text(if (submitting) "Saving..." else "Save")
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
private fun KindSelector(draft: DebtDraft, onDraftChange: (DebtDraft) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (draft.kind == "debt") {
            Button(onClick = { onDraftChange(draft.copy(kind = "debt")) }) { Text("Debt") }
        } else {
            OutlinedButton(onClick = { onDraftChange(draft.copy(kind = "debt")) }) { Text("Debt") }
        }
        if (draft.kind == "loan") {
            Button(onClick = { onDraftChange(draft.copy(kind = "loan")) }) { Text("Loan") }
        } else {
            OutlinedButton(onClick = { onDraftChange(draft.copy(kind = "loan")) }) { Text("Loan") }
        }
    }
}

private fun DebtItem.kindLabel(): String =
    if (kind == "loan") "loan" else "debt"

private fun String.lineSafe(): String =
    lineSequence().firstOrNull().orEmpty()
