package app.ledgera.reports

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.Alignment
import androidx.compose.ui.unit.dp
import app.ledgera.ui.AutocompleteTextField
import app.ledgera.ui.LedgerDateField
import app.ledgera.ui.toComposeTagColor

@Composable
fun ReportsScreen(
    viewModel: ReportsViewModel,
    scrollState: ScrollState,
    fileActions: ReportsFileActions = NoReportsFileActions,
) {
    val state by viewModel.state.collectAsState()
    Column(
        Modifier.fillMaxSize().verticalScroll(scrollState).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Reports", style = MaterialTheme.typography.headlineLarge)
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Surface(Modifier.fillMaxWidth(), tonalElevation = 2.dp, shape = MaterialTheme.shapes.medium) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LedgerDateField(state.periodStart, viewModel::updatePeriodStart, "From", Modifier.weight(1f), required = false, externalError = state.periodStartError)
                    LedgerDateField(state.periodEnd, viewModel::updatePeriodEnd, "To", Modifier.weight(1f), required = false, externalError = state.periodEndError)
                }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    FilterChip(state.walletId == null, { viewModel.updateWallet(null) }, label = { Text("All wallets") })
                    state.wallets.forEach { wallet ->
                        FilterChip(state.walletId == wallet.id, { viewModel.updateWallet(wallet.id) }, label = { Text(wallet.name) })
                    }
                }
                AutocompleteTextField(
                    value = state.category,
                    onValueChange = viewModel::updateCategory,
                    label = "Category",
                    suggestions = state.categories,
                    modifier = Modifier.fillMaxWidth(),
                    showSuggestionsOnBlank = false,
                )
                AutocompleteTextField(
                    value = state.tag,
                    onValueChange = viewModel::updateTag,
                    label = "Tags",
                    suggestions = state.tags,
                    modifier = Modifier.fillMaxWidth(),
                    showSuggestionsOnBlank = false,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(state.tagMode == "or", { viewModel.updateTagMode("or") }, label = { Text("Tags OR") })
                    FilterChip(state.tagMode == "and", { viewModel.updateTagMode("and") }, label = { Text("Tags AND") })
                    FilterChip(state.totalsMode == "fixed", { viewModel.updateTotalsMode("fixed") }, label = { Text("Fixed") })
                    FilterChip(state.totalsMode == "current", { viewModel.updateTotalsMode("current") }, label = { Text("Current") })
                    FilterChip(state.groupByCategory, { viewModel.updateGrouping(!state.groupByCategory) }, label = { Text("Group by category") })
                }
                Text(
                    if (state.totalsMode == "current") "Current amounts using export-time rates"
                    else "Fixed amounts using operation-time rates",
                    style = MaterialTheme.typography.bodySmall,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = viewModel::generate, enabled = !state.loading) { Text("Generate") }
                    Button(onClick = { viewModel.export("csv", fileActions) }, enabled = state.result != null && !state.loading) { Text("CSV") }
                    Button(onClick = { viewModel.export("xlsx", fileActions) }, enabled = state.result != null && !state.loading) { Text("XLSX") }
                    Button(onClick = { viewModel.export("pdf", fileActions) }, enabled = state.result != null && !state.loading) { Text("PDF") }
                }
            }
        }
        state.result?.let { result ->
            ReportSummaryCard(result)
            if (result.filters.groupByCategory) {
                ReportSection("Categories") {
                    val currentMode = result.filters.totalsMode.equals("current", ignoreCase = true)
                    result.categories.forEach { row ->
                        val amount = if (currentMode) row.totalCurrent else row.totalBase
                        Text("${row.category}: ${row.operationsCount} · ${"%.2f".format(amount)}")
                    }
                }
            } else {
                ReportSection("Operations") {
                    val currentMode = result.filters.totalsMode.equals("current", ignoreCase = true)
                    result.operations.forEach { row ->
                        val amount = if (currentMode) row.amountCurrent else row.amountBase
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                "${row.date} · ${row.typeLabel} · ${row.category} · ${"%.2f".format(amount)}",
                                Modifier.weight(1f),
                            )
                            ReportTagChips(row.tagsText, state.tagColors)
                        }
                    }
                }
            }
            ReportSection("Monthly") {
                val currentMode = result.filters.totalsMode.equals("current", ignoreCase = true)
                result.monthly.forEach { row ->
                    val income = if (currentMode) row.incomeCurrent else row.income
                    val expenses = if (currentMode) row.expensesCurrent else row.expenses
                    Text("${row.month}: income ${"%.2f".format(income)}, expenses ${"%.2f".format(expenses)}")
                }
            }
            ReportSection("Tags") {
                val currentMode = result.filters.totalsMode.equals("current", ignoreCase = true)
                result.tags.forEach { row ->
                    val amount = if (currentMode) row.totalCurrent else row.totalBase
                    Text("${row.tag}: ${row.operationsCount} · ${"%.2f".format(amount)}")
                }
            }
            if (result.debts.isNotEmpty()) ReportSection("Debts") {
                result.debts.forEach { row -> Text("${row.contactName} · ${row.kind} · ${row.remainingAmount} / ${row.totalAmount} ${row.currency}") }
            }
        }
    }
}

@Composable
private fun ReportSummaryCard(result: app.ledgera.model.ReportResult) {
    val currentMode = result.filters.totalsMode.equals("current", ignoreCase = true)
    val operationsTotal = if (currentMode) result.summary.recordsTotalCurrent else result.summary.recordsTotalFixed
    val finalBalance = if (currentMode) result.summary.finalBalanceCurrent else result.summary.finalBalanceFixed
    Surface(Modifier.fillMaxWidth(), tonalElevation = 2.dp, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(result.title, style = MaterialTheme.typography.titleLarge)
            Text("Initial: ${"%.2f".format(result.summary.initialBalance)} ${result.displayCurrency}")
            Text("Operations: ${"%.2f".format(operationsTotal)} ${result.baseCurrency}")
            Text("Final: ${"%.2f".format(finalBalance)} ${result.baseCurrency}")
            Text("Count: ${result.summary.recordsCount}")
            if (result.summary.fxDifference != 0.0) Text("FX difference: ${"%.2f".format(result.summary.fxDifference)}")
        }
    }
}

@Composable
private fun ReportSection(title: String, content: @Composable () -> Unit) {
    Surface(Modifier.fillMaxWidth(), tonalElevation = 2.dp, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}

@Composable
private fun ReportTagChips(tagsText: String, tagColors: Map<String, String>) {
    val tags = tagsText.split(Regex("\\s+")).filter(String::isNotBlank)
    if (tags.isEmpty()) return
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        tags.forEach { tag ->
            Box(
                Modifier
                    .clip(RoundedCornerShape(percent = 50))
                    .background(
                        tagColors[tag.lowercase()]?.toComposeTagColor()
                            ?: MaterialTheme.colorScheme.outline,
                    )
                    .padding(horizontal = 7.dp, vertical = 3.dp),
            ) {
                Text(
                    "#$tag",
                    color = MaterialTheme.colorScheme.onPrimary,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}
