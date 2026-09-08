package app.ledgera.reports

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.ledgera.ui.LedgerDateField

@Composable
fun ReportsScreen(viewModel: ReportsViewModel, fileActions: ReportsFileActions = NoReportsFileActions) {
    val state by viewModel.state.collectAsState()
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Reports", style = MaterialTheme.typography.headlineLarge)
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Surface(tonalElevation = 2.dp, shape = MaterialTheme.shapes.medium) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LedgerDateField(state.periodStart, viewModel::updatePeriodStart, "From", Modifier.weight(1f), required = false)
                    LedgerDateField(state.periodEnd, viewModel::updatePeriodEnd, "To", Modifier.weight(1f), required = false)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(state.walletId == null, { viewModel.updateWallet(null) }, label = { Text("All wallets") })
                    state.wallets.forEach { wallet ->
                        FilterChip(state.walletId == wallet.id, { viewModel.updateWallet(wallet.id) }, label = { Text(wallet.name) })
                    }
                }
                OutlinedTextField(state.category, viewModel::updateCategory, Modifier.fillMaxWidth(), label = { Text("Category") }, singleLine = true)
                if (state.category.isNotBlank()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        state.categories.filter { it.contains(state.category, ignoreCase = true) }.take(8).forEach { value ->
                            FilterChip(selected = value == state.category, onClick = { viewModel.updateCategory(value) }, label = { Text(value) })
                        }
                    }
                }
                OutlinedTextField(state.tag, viewModel::updateTag, Modifier.fillMaxWidth(), label = { Text("Tags") }, singleLine = true)
                if (state.tag.isNotBlank()) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        state.tags.filter { it.contains(state.tag.substringAfterLast(',').trim(), ignoreCase = true) }.take(8).forEach { value ->
                            FilterChip(selected = false, onClick = { viewModel.updateTag(value) }, label = { Text(value) })
                        }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(state.tagMode == "or", { viewModel.updateTagMode("or") }, label = { Text("Tags OR") })
                    FilterChip(state.tagMode == "and", { viewModel.updateTagMode("and") }, label = { Text("Tags AND") })
                    FilterChip(state.totalsMode == "fixed", { viewModel.updateTotalsMode("fixed") }, label = { Text("Fixed") })
                    FilterChip(state.totalsMode == "current", { viewModel.updateTotalsMode("current") }, label = { Text("Current") })
                }
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
            ReportSection("Operations") {
                result.operations.forEach { row ->
                    Text("${row.date} · ${row.typeLabel} · ${row.category} · ${"%.2f".format(row.amountBase)}")
                    if (row.tagsText.isNotBlank()) Text(row.tagsText, style = MaterialTheme.typography.bodySmall)
                }
            }
            ReportSection("Monthly") {
                result.monthly.forEach { row -> Text("${row.month}: income ${"%.2f".format(row.income)}, expenses ${"%.2f".format(row.expenses)}") }
            }
            ReportSection("Categories") {
                result.categories.forEach { row -> Text("${row.category}: ${row.operationsCount} · ${"%.2f".format(row.totalBase)}") }
            }
            ReportSection("Tags") {
                result.tags.forEach { row -> Text("${row.tag}: ${row.operationsCount} · ${"%.2f".format(row.totalBase)}") }
            }
            if (result.debts.isNotEmpty()) ReportSection("Debts") {
                result.debts.forEach { row -> Text("${row.contactName} · ${row.kind} · ${row.remainingAmount} / ${row.totalAmount} ${row.currency}") }
            }
        }
    }
}

@Composable
private fun ReportSummaryCard(result: app.ledgera.model.ReportResult) {
    Surface(tonalElevation = 2.dp, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(result.title, style = MaterialTheme.typography.titleLarge)
            Text("Initial: ${"%.2f".format(result.summary.initialBalance)} ${result.displayCurrency}")
            Text("Operations: ${"%.2f".format(result.summary.recordsTotalFixed)} ${result.baseCurrency}")
            Text("Final: ${"%.2f".format(result.summary.finalBalanceFixed)} ${result.baseCurrency}")
            Text("Count: ${result.summary.recordsCount}")
            if (result.summary.fxDifference != 0.0) Text("FX difference: ${"%.2f".format(result.summary.fxDifference)}")
        }
    }
}

@Composable
private fun ReportSection(title: String, content: @Composable () -> Unit) {
    Surface(tonalElevation = 2.dp, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}
