package app.ledgera.budget

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import app.ledgera.model.BudgetResultItem
import app.ledgera.ui.AutocompleteTextField
import app.ledgera.ui.LedgerDateField

@Composable
fun BudgetScreen(viewModel: BudgetViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.refresh() }
    Box(modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Budget", style = MaterialTheme.typography.headlineLarge)
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            BudgetList(state, viewModel)
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Button(onClick = viewModel::openEditLimit, enabled = state.selectedBudgetId != null) { Text("Edit limit") }
                OutlinedButton(onClick = viewModel::requestDelete, enabled = state.selectedBudgetId != null) { Text("Delete") }
                TextButton(onClick = viewModel::refresh) { Text("Refresh") }
            }
        }
        FloatingActionButton(onClick = viewModel::openCreateDialog, modifier = Modifier.align(androidx.compose.ui.Alignment.BottomEnd).padding(28.dp)) { Text("+") }
    }
    state.createDraft?.let { draft ->
        BudgetCreateDialog(state, draft, viewModel)
    }
    state.editLimitBudgetId?.let {
        AlertDialog(
            onDismissRequest = viewModel::closeEditLimit,
            title = { Text("Edit budget limit") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(state.editLimit, viewModel::updateEditLimit, label = { Text("Limit") }, singleLine = true)
                    state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                }
            },
            confirmButton = { Button(onClick = viewModel::saveEditLimit) { Text("Save") } },
            dismissButton = { TextButton(onClick = viewModel::closeEditLimit) { Text("Cancel") } },
        )
    }
    state.deleteBudgetId?.let { id ->
        AlertDialog(
            onDismissRequest = viewModel::closeDelete,
            title = { Text("Delete budget?") },
            text = { Text("The selected budget and its tracking result will be removed.") },
            confirmButton = { Button(onClick = viewModel::deleteBudget) { Text("Delete") } },
            dismissButton = { TextButton(onClick = viewModel::closeDelete) { Text("Cancel") } },
        )
    }
}

@Composable
private fun BudgetList(state: BudgetUiState, viewModel: BudgetViewModel) {
    Card(Modifier.fillMaxWidth().heightIn(min = 160.dp, max = 560.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Budgets", style = MaterialTheme.typography.titleMedium)
            if (state.loading && state.results.isEmpty()) CircularProgressIndicator()
            else if (state.results.isEmpty()) Text("No budgets found.")
            else LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(state.results, key = { it.budget.id }) { result ->
                    BudgetRow(result, state.selectedBudgetId == result.budget.id) { viewModel.selectBudget(result.budget.id) }
                }
            }
        }
    }
}

@Composable
private fun BudgetRow(result: BudgetResultItem, selected: Boolean, onClick: () -> Unit) {
    val tone = when (result.paceStatus) {
        "overspent" -> MaterialTheme.colorScheme.error
        "overpace" -> Color(0xFF9A6700)
        else -> MaterialTheme.colorScheme.primary
    }
    Card(
        Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = if (selected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("${result.budget.scopeType}: ${result.budget.scopeValue}", style = MaterialTheme.typography.titleMedium)
                Text("${result.budget.limitBase}", style = MaterialTheme.typography.titleMedium)
            }
            Text("${result.budget.startDate} -> ${result.budget.endDate} · ${result.status}")
            Text("Spent ${result.spentBase} · Remaining ${result.remainingBase}")
            LinearProgressIndicator({ (result.usagePct / 100.0).coerceIn(0.0, 1.0).toFloat() }, Modifier.fillMaxWidth(), color = tone)
            Text("${result.usagePct.formatOne()}% used · ${result.paceStatus}", color = tone)
            result.forecastStatusKey?.let { key -> Text(forecastText(key, result), style = MaterialTheme.typography.bodySmall) }
        }
    }
}

private fun forecastText(key: String, result: BudgetResultItem): String = when (key) {
    "budget.forecast.overspend_in_days" -> "Forecast: overspend in ${result.forecastDaysLeft ?: 0} days"
    "budget.forecast.overspend" -> "Forecast: overspend"
    else -> "Forecast remaining: ${result.forecastRemainingBase ?: "-"}"
}

private fun Double.formatOne(): String = "%.1f".format(this)

@Composable
private fun BudgetCreateDialog(state: BudgetUiState, draft: BudgetDraft, viewModel: BudgetViewModel) {
    AlertDialog(
        onDismissRequest = viewModel::closeCreateDialog,
        title = { Text("New budget") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(draft.scopeType == "category", { viewModel.updateDraft(draft.copy(scopeType = "category", scopeValue = "")) }, label = { Text("Category") })
                    FilterChip(draft.scopeType == "tag", { viewModel.updateDraft(draft.copy(scopeType = "tag", scopeValue = "")) }, label = { Text("Tag") })
                }
                AutocompleteTextField(draft.scopeValue, { viewModel.updateDraft(draft.copy(scopeValue = it)) }, if (draft.scopeType == "tag") "Tag" else "Category", state.suggestions, Modifier.fillMaxWidth(), showSuggestionsOnBlank = false)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LedgerDateField(draft.startDate, { viewModel.updateDraft(draft.copy(startDate = it)) }, "From", Modifier.weight(1f), required = true, allowFuture = true)
                    LedgerDateField(draft.endDate, { viewModel.updateDraft(draft.copy(endDate = it)) }, "To", Modifier.weight(1f), required = true, allowFuture = true)
                }
                OutlinedTextField(draft.limitBase, { viewModel.updateDraft(draft.copy(limitBase = it)) }, label = { Text("Limit") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(draft.includeMandatory, { viewModel.updateDraft(draft.copy(includeMandatory = !draft.includeMandatory)) }, label = { Text("Include mandatory") })
                }
                state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = { Button(onClick = viewModel::createBudget) { Text("Create") } },
        dismissButton = { TextButton(onClick = viewModel::closeCreateDialog) { Text("Cancel") } },
    )
}
