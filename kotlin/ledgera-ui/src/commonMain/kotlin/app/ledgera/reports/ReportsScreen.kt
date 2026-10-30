package app.ledgera.reports

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
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
                ReportOperationsTable(result, state.tagColors)
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
private fun ReportOperationsTable(result: app.ledgera.model.ReportResult, tagColors: Map<String, String>) {
    val currentMode = result.filters.totalsMode.equals("current", ignoreCase = true)
    Surface(Modifier.fillMaxWidth(), tonalElevation = 2.dp, shape = MaterialTheme.shapes.medium) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Operations", style = MaterialTheme.typography.titleMedium)
            BoxWithConstraints(Modifier.fillMaxWidth()) {
                val tableWidth = maxOf(maxWidth, 1060.dp)
                val extraWidth = (tableWidth - 1060.dp).coerceAtLeast(0.dp)
                val dateWidth = 110.dp + extraWidth * 0.1f
                val typeWidth = 110.dp + extraWidth * 0.1f
                val categoryWidth = 210.dp + extraWidth * 0.2f
                val descriptionWidth = 260.dp + extraWidth * 0.3f
                val tagsWidth = 220.dp + extraWidth * 0.2f
                val amountWidth = 150.dp + extraWidth * 0.1f
                Column(Modifier.horizontalScroll(rememberScrollState()).width(tableWidth)) {
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .background(MaterialTheme.colorScheme.surfaceVariant)
                            .padding(vertical = 10.dp),
                    ) {
                        ReportTableCell("Date", dateWidth, isHeader = true)
                        ReportTableCell("Type", typeWidth, isHeader = true)
                        ReportTableCell("Category", categoryWidth, isHeader = true)
                        ReportTableCell("Description", descriptionWidth, isHeader = true)
                        ReportTableCell("Tags", tagsWidth, isHeader = true)
                        ReportTableCell("Amount", amountWidth, isHeader = true, alignEnd = true)
                    }
                    LazyColumn(Modifier.fillMaxWidth().heightIn(max = 420.dp)) {
                        items(result.operations) { row ->
                            val amount = if (currentMode) row.amountCurrent else row.amountBase
                            Column(Modifier.fillMaxWidth()) {
                                Row(
                                    Modifier.fillMaxWidth().padding(vertical = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    ReportTableCell(row.date, dateWidth)
                                    ReportTableCell(row.typeLabel, typeWidth)
                                    ReportTableCell(row.category, categoryWidth)
                                    ReportTableCell(row.description.ifBlank { "-" }, descriptionWidth)
                                    ReportTagChips(row.tagsText, tagColors, Modifier.width(tagsWidth))
                                    ReportTableCell("%.2f".format(amount), amountWidth, alignEnd = true)
                                }
                                HorizontalDivider(Modifier.fillMaxWidth())
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ReportTableCell(
    value: String,
    width: androidx.compose.ui.unit.Dp,
    isHeader: Boolean = false,
    alignEnd: Boolean = false,
) {
    Box(
        Modifier.width(width).padding(horizontal = 8.dp),
        contentAlignment = if (alignEnd) Alignment.CenterEnd else Alignment.CenterStart,
    ) {
        Text(
            value,
            fontWeight = if (isHeader) androidx.compose.ui.text.font.FontWeight.SemiBold else androidx.compose.ui.text.font.FontWeight.Normal,
            color = if (isHeader) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
        )
    }
}

@Composable
private fun ReportTagChips(
    tagsText: String,
    tagColors: Map<String, String>,
    modifier: Modifier = Modifier,
) {
    val tags = tagsText.split(Regex("\\s+")).filter(String::isNotBlank)
    if (tags.isEmpty()) {
        Box(modifier)
        return
    }
    Row(modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
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
