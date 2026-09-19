package app.ledgera.analytics

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import app.ledgera.model.AnalyticsBreakdownRow
import app.ledgera.model.AnalyticsDailyRow
import app.ledgera.model.AnalyticsMonthlyRow
import app.ledgera.ui.LedgerDateField
import app.ledgera.ui.AutocompleteTextField
import kotlin.math.max

@Composable
fun AnalyticsScreen(viewModel: AnalyticsViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsState()
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Analytics", style = MaterialTheme.typography.headlineLarge)
        state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Card {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LedgerDateField(state.periodStart, viewModel::updatePeriodStart, "From", Modifier.weight(1f), required = true)
                    LedgerDateField(state.periodEnd, viewModel::updatePeriodEnd, "To", Modifier.weight(1f), required = true)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(state.breakdownMode == "category", { viewModel.updateBreakdownMode("category") }, label = { Text("Category") })
                    FilterChip(state.breakdownMode == "tag", { viewModel.updateBreakdownMode("tag") }, label = { Text("Tag") })
                    FilterChip(state.tagMode == "or", { viewModel.updateTagMode("or") }, label = { Text("Tags OR") })
                    FilterChip(state.tagMode == "and", { viewModel.updateTagMode("and") }, label = { Text("Tags AND") })
                    FilterChip(state.totalsMode == "fixed", { viewModel.updateTotalsMode("fixed") }, label = { Text("Fixed") })
                    FilterChip(state.totalsMode == "current", { viewModel.updateTotalsMode("current") }, label = { Text("Current") })
                    FilterChip(state.groupByCategory, { viewModel.updateGrouping(!state.groupByCategory) }, label = { Text("Group by category") })
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
                    OutlinedButton(onClick = viewModel::generate, enabled = !state.loading) { Text("Generate") }
                }
                if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            }
        }
        state.snapshot?.let { snapshot ->
            SummaryCard(snapshot.summary)
            ChartCard("Capital dynamics") { LineChart(snapshot.capital.map { it.month to it.balanceBase }) }
            val breakdown = if (state.breakdownMode == "tag") snapshot.tags else snapshot.categories
            BreakdownCard(state.breakdownMode, breakdown)
            ChartCard("Breakdown") { PieChart(breakdown) }
            MonthlyCard(snapshot.monthly)
            ChartCard("Daily cashflow") { BarChart(snapshot.daily.map { it.day to (it.incomeBase to it.expensesBase) }) }
            ChartCard("Monthly cashflow") { BarChart(snapshot.infographicMonthly.map { it.month to (it.incomeBase to it.expensesBase) }) }
        }
    }
}

@Composable
private fun SummaryCard(summary: app.ledgera.model.AnalyticsSummary) {
    Card { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Summary", style = MaterialTheme.typography.titleLarge)
        Text("Net worth: %.2f".format(summary.netWorthBase))
        Text("Savings rate: %.2f%%".format(summary.savingsRate))
        Text("Burn rate: %.2f".format(summary.burnRate))
        Text("Average monthly income: %.2f".format(summary.averageMonthlyIncome))
        Text("Average monthly expenses: %.2f".format(summary.averageMonthlyExpenses))
        Text("Year income: %.2f".format(summary.yearIncome))
        Text("Year expenses: %.2f".format(summary.yearExpense))
    } }
}

@Composable
private fun BreakdownCard(mode: String, rows: List<AnalyticsBreakdownRow>) {
    Card { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(if (mode == "tag") "Tag breakdown" else "Category breakdown", style = MaterialTheme.typography.titleLarge)
        rows.forEach { row -> Text("${row.label}: ${"%.2f".format(row.amountBase)} (${row.recordCount})") }
        if (mode == "tag") Text("Tag totals are non-additive when one operation has multiple tags", style = MaterialTheme.typography.bodySmall)
    } }
}

@Composable
private fun MonthlyCard(rows: List<AnalyticsMonthlyRow>) {
    Card { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Monthly report", style = MaterialTheme.typography.titleLarge)
        rows.forEach { row -> Text("${row.month}: income ${"%.2f".format(row.incomeBase)}, expenses ${"%.2f".format(row.expensesBase)}, cashflow ${"%.2f".format(row.cashflowBase)}") }
    } }
}

@Composable
private fun ChartCard(title: String, content: @Composable () -> Unit) {
    Card { Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, style = MaterialTheme.typography.titleLarge)
        Box(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).height(220.dp)) { content() }
    } }
}

@Composable
private fun LineChart(points: List<Pair<String, Double>>) {
    if (points.isEmpty()) { Text("No data") ; return }
    val lineColor = MaterialTheme.colorScheme.primary
    Canvas(Modifier.fillMaxWidth().height(210.dp)) {
        val values = points.map { it.second }
        val min = values.minOrNull() ?: 0.0
        val max = values.maxOrNull() ?: 1.0
        val span = max(max - min, 1.0)
        val step = size.width / max(1, points.lastIndex).toFloat()
        val coordinates = values.mapIndexed { index, value -> Offset(index * step, size.height - ((value - min) / span * size.height).toFloat()) }
        coordinates.zipWithNext().forEach { (a, b) -> drawLine(lineColor, a, b, strokeWidth = 4f) }
        coordinates.forEach { drawCircle(lineColor, 4f, it) }
    }
}

@Composable
private fun PieChart(rows: List<AnalyticsBreakdownRow>) {
    var selected by remember { mutableStateOf<String?>(null) }
    val total = rows.sumOf { it.amountBase }
    if (rows.isEmpty() || total <= 0.0) { Text("No data") ; return }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Canvas(
            Modifier.fillMaxWidth().height(190.dp).pointerInput(rows) {
                awaitPointerEventScope {
                    while (true) {
                        val event = awaitPointerEvent()
                        val position = event.changes.firstOrNull()?.position ?: continue
                        val center = Offset(size.width / 2f, size.height / 2f)
                        val dx = position.x - center.x
                        val dy = position.y - center.y
                        val distance = kotlin.math.sqrt(dx * dx + dy * dy)
                        if (distance > minOf(size.width, size.height) / 2f) continue
                        val angle = (Math.toDegrees(kotlin.math.atan2(dy.toDouble(), dx.toDouble())) + 450.0) % 360.0
                        var cursor = 0.0
                        rows.firstOrNull { row ->
                            val next = cursor + row.amountBase / total * 360.0
                            val match = angle >= cursor && angle < next
                            cursor = next
                            match
                        }?.let { selected = it.label }
                    }
                }
            },
        ) {
            var start = -90f
            rows.forEachIndexed { index, row ->
                val sweep = (row.amountBase / total * 360.0).toFloat()
                drawArc(Color.hsv((index * 53f) % 360f, 0.65f, 0.85f), start, sweep, true, size = Size(minOf(size.width, size.height), minOf(size.width, size.height)), topLeft = Offset((size.width - minOf(size.width, size.height)) / 2f, 0f))
                start += sweep
            }
        }
        selected?.let { label -> rows.firstOrNull { it.label == label }?.let { row -> Text("$label: %.2f (%.1f%%)".format(row.amountBase, row.amountBase / total * 100.0)) } }
    }
}

@Composable
private fun BarChart(rows: List<Pair<String, Pair<Double, Double>>>) {
    if (rows.isEmpty()) { Text("No data") ; return }
    Canvas(Modifier.width(max(420, rows.size * 44).dp).height(210.dp)) {
        val maxValue = rows.maxOf { max(it.second.first, it.second.second) }.coerceAtLeast(1.0)
        val group = size.width / rows.size
        rows.forEachIndexed { index, row ->
            val x = group * index + group / 2f
            val incomeHeight = (row.second.first / maxValue * size.height * .8).toFloat()
            val expenseHeight = (row.second.second / maxValue * size.height * .8).toFloat()
            drawRect(Color(0xFF2C7A68), Offset(x - 8f, size.height / 2f - incomeHeight), Size(7f, incomeHeight))
            drawRect(Color(0xFFC94C4C), Offset(x + 1f, size.height / 2f), Size(7f, expenseHeight))
        }
    }
}
