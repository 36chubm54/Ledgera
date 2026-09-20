package app.ledgera.analytics

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.Surface
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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.compose.animation.core.animateFloatAsState
import app.ledgera.model.AnalyticsBreakdownRow
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
                    FilterChip(state.breakdownMode == "category", { viewModel.updateBreakdownMode("category"); viewModel.generate() }, label = { Text("Category") })
                    FilterChip(state.breakdownMode == "tag", { viewModel.updateBreakdownMode("tag"); viewModel.generate() }, label = { Text("Tag") })
                    FilterChip(state.tagMode == "or", { viewModel.updateTagMode("or"); viewModel.generate() }, label = { Text("Tags OR") })
                    FilterChip(state.tagMode == "and", { viewModel.updateTagMode("and"); viewModel.generate() }, label = { Text("Tags AND") })
                    FilterChip(state.totalsMode == "fixed", { viewModel.updateTotalsMode("fixed"); viewModel.generate() }, label = { Text("Fixed") })
                    FilterChip(state.totalsMode == "current", { viewModel.updateTotalsMode("current"); viewModel.generate() }, label = { Text("Current") })
                    FilterChip(state.groupByCategory, { viewModel.updateGrouping(!state.groupByCategory); viewModel.generate() }, label = { Text("Group by category") })
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
            val breakdown = when {
                state.groupByCategory -> snapshot.groupedCategories
                state.breakdownMode == "tag" -> snapshot.tags
                else -> snapshot.categories
            }
            BreakdownSummaryCard(
                title = if (state.groupByCategory) "Grouped category breakdown"
                else if (state.breakdownMode == "tag") "Tag breakdown" else "Category breakdown",
                rows = breakdown,
            )
            MonthlyCard(snapshot.monthly)
            InfographicsSection(
                breakdown = snapshot.infographicCategories,
                daily = snapshot.infographicDaily.map { it.day to (it.incomeBase to it.expensesBase) },
                monthly = snapshot.infographicMonthly.map { it.month to (it.incomeBase to it.expensesBase) },
                piePeriod = state.piePeriod,
                dailyMonth = state.dailyMonth,
                monthlyYear = state.monthlyYear,
                months = state.infographicMonths,
                years = state.infographicYears,
                onPiePeriodChange = viewModel::updatePiePeriod,
                onDailyMonthChange = viewModel::updateDailyMonth,
                onMonthlyYearChange = viewModel::updateMonthlyYear,
                onRefresh = viewModel::generate,
            )
        }
    }
}

@Composable
private fun BreakdownSummaryCard(title: String, rows: List<AnalyticsBreakdownRow>) {
    Card {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge)
            if (rows.isEmpty()) {
                Text("No breakdown data", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                rows.forEach { row ->
                    Text("${row.label}: ${"%.2f".format(row.amountBase)} (${row.recordCount})")
                }
            }
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
private fun InfographicsSection(
    breakdown: List<AnalyticsBreakdownRow>,
    daily: List<Pair<String, Pair<Double, Double>>>,
    monthly: List<Pair<String, Pair<Double, Double>>>,
    piePeriod: String,
    dailyMonth: String,
    monthlyYear: String,
    months: List<String>,
    years: List<String>,
    onPiePeriodChange: (String) -> Unit,
    onDailyMonthChange: (String) -> Unit,
    onMonthlyYearChange: (String) -> Unit,
    onRefresh: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Infographics", style = MaterialTheme.typography.headlineSmall)
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            if (maxWidth < 760.dp) {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    InfographicCard("Expenses by category") {
                        SelectorRow("Period", if (piePeriod == "all_time") "All time" else piePeriod, listOf("all_time") + months, onPiePeriodChange, onRefresh)
                        CategoryChart(breakdown)
                    }
                    InfographicCard("Daily cashflow") {
                        SelectorRow("Month", dailyMonth.ifEmpty { months.lastOrNull().orEmpty() }, months, onDailyMonthChange, onRefresh)
                        CashflowChart(daily, labelStep = 3)
                    }
                }
            } else {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    InfographicCard("Expenses by category", Modifier.weight(1f)) {
                        SelectorRow("Period", if (piePeriod == "all_time") "All time" else piePeriod, listOf("all_time") + months, onPiePeriodChange, onRefresh)
                        CategoryChart(breakdown)
                    }
                    InfographicCard("Daily cashflow", Modifier.weight(1f)) {
                        SelectorRow("Month", dailyMonth.ifEmpty { months.lastOrNull().orEmpty() }, months, onDailyMonthChange, onRefresh)
                        CashflowChart(daily, labelStep = 3)
                    }
                }
            }
        }
        InfographicCard("Monthly cashflow", Modifier.fillMaxWidth()) {
            SelectorRow("Year", monthlyYear.ifEmpty { years.lastOrNull().orEmpty() }, years, onMonthlyYearChange, onRefresh)
            CashflowChart(monthly, labelStep = 1)
        }
    }
}

@Composable
private fun SelectorRow(
    label: String,
    selected: String,
    options: List<String>,
    onChange: (String) -> Unit,
    onRefresh: () -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge)
        Box {
            OutlinedButton(onClick = { expanded = true }, enabled = options.isNotEmpty()) {
                Text(selected.ifEmpty { "No data" })
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                options.forEach { option ->
                    DropdownMenuItem(
                        text = { Text(if (option == "all_time") "All time" else option) },
                        onClick = {
                            expanded = false
                            onChange(option)
                            onRefresh()
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun InfographicCard(
    title: String,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Card(modifier) {
        Column(
            Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleLarge)
            content()
        }
    }
}

@Composable
private fun CategoryChart(rows: List<AnalyticsBreakdownRow>) {
    val total = rows.sumOf { it.amountBase }
    if (rows.isEmpty() || total <= 0.0) {
        Text("No category data", color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        var selected by remember(rows) { mutableStateOf<AnalyticsBreakdownRow?>(null) }
        Column(Modifier.width(220.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            InteractivePieChart(rows, Modifier.size(220.dp)) { selected = it }
            selected?.let { row ->
                Surface(color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.92f)) {
                    Column(Modifier.padding(8.dp)) {
                        Text(row.label, style = MaterialTheme.typography.labelLarge)
                        Text("%.2f (%.1f%%)".format(row.amountBase, row.amountBase / total * 100.0))
                        if (row.isOther && row.details.isNotEmpty()) {
                            row.details.forEach { detail ->
                                Text(
                                    "${detail.label}: %.2f".format(detail.amountBase),
                                    style = MaterialTheme.typography.bodySmall,
                                )
                            }
                        }
                    }
                }
            }
        }
        Column(
            Modifier.height(220.dp).weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            rows.forEachIndexed { index, row ->
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Box(
                        Modifier.size(12.dp),
                    ) {
                        androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) {
                            drawCircle(paletteColor(index))
                        }
                    }
                    Column(Modifier.weight(1f)) {
                        Text(row.label, maxLines = 1)
                        Text(
                            "%.2f (%.1f%%)".format(row.amountBase, row.amountBase / total * 100.0),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
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
private fun InteractivePieChart(
    rows: List<AnalyticsBreakdownRow>,
    modifier: Modifier,
    onSelected: (AnalyticsBreakdownRow) -> Unit,
) {
    val total = rows.sumOf { it.amountBase }
    val sweeps = rows.mapIndexed { index, row ->
        val targetSweep = (row.amountBase / total * 360.0).toFloat()
        animateFloatAsState(targetSweep, label = "pie-sweep-$index").value
    }
    Canvas(
        modifier.pointerInput(rows) {
            awaitPointerEventScope {
                while (true) {
                    val event = awaitPointerEvent()
                    val position = event.changes.firstOrNull()?.position ?: continue
                    val center = Offset(size.width / 2f, size.height / 2f)
                    val dx = position.x - center.x
                    val dy = position.y - center.y
                    if (kotlin.math.sqrt(dx * dx + dy * dy) > minOf(size.width, size.height) / 2f) continue
                    val angle = (Math.toDegrees(kotlin.math.atan2(dy.toDouble(), dx.toDouble())) + 450.0) % 360.0
                    var cursor = 0.0
                    rows.firstOrNull { row ->
                        val next = cursor + row.amountBase / total * 360.0
                        val match = angle >= cursor && angle < next
                        cursor = next
                        match
                    }?.let(onSelected)
                }
            }
        },
    ) {
        val diameter = minOf(size.width, size.height)
        var start = -90f
        rows.forEachIndexed { index, row ->
            val targetSweep = (row.amountBase / total * 360.0).toFloat()
            val sweep = sweeps[index]
            drawArc(
                parseHexColor(row.color) ?: paletteColor(index),
                start,
                sweep,
                true,
                size = Size(diameter, diameter),
                topLeft = Offset((size.width - diameter) / 2f, (size.height - diameter) / 2f),
            )
            start += targetSweep
        }
    }
}

private fun parseHexColor(value: String): Color? {
    val normalized = value.trim().removePrefix("#")
    if (normalized.length != 6 && normalized.length != 8) return null
    return normalized.toLongOrNull(16)?.let { raw ->
        if (normalized.length == 6) Color((0xFF000000L or raw).toInt()) else Color(raw.toInt())
    }
}

private fun paletteColor(index: Int): Color = Color.hsv(
    hue = (index * 53f) % 360f,
    saturation = 0.65f,
    value = 0.85f,
)

@Composable
private fun CashflowChart(
    rows: List<Pair<String, Pair<Double, Double>>>,
    labelStep: Int,
) {
    if (rows.isEmpty()) {
        Text("No cashflow data", color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    val chartWidth = max(560, rows.size * 48)
    val maxValue = rows.maxOf { max(it.second.first, it.second.second) }.coerceAtLeast(1.0)
    val axisColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.5f)
    var selectedIndex by remember(rows) { mutableStateOf<Int?>(null) }
    val incomeHeights = rows.mapIndexed { index, row ->
        animateFloatAsState(
            (row.second.first / maxValue).toFloat(),
            label = "income-bar-$index",
        ).value
    }
    val expenseHeights = rows.mapIndexed { index, row ->
        animateFloatAsState(
            (row.second.second / maxValue).toFloat(),
            label = "expense-bar-$index",
        ).value
    }
    Column(Modifier.fillMaxWidth()) {
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            LegendDot(Color(0xFF2C7A68), "Income")
            LegendDot(Color(0xFFC94C4C), "Expenses")
        }
        Box(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
            Column(Modifier.width(chartWidth.dp)) {
                Canvas(
                    Modifier.fillMaxWidth().height(190.dp).pointerInput(rows) {
                        awaitPointerEventScope {
                            while (true) {
                                val event = awaitPointerEvent()
                                val x = event.changes.firstOrNull()?.position?.x ?: continue
                                val group = size.width / rows.size
                                selectedIndex = (x / group).toInt().coerceIn(0, rows.lastIndex)
                            }
                        }
                    },
                ) {
                    val baseline = size.height / 2f
                    drawLine(
                        axisColor,
                        Offset(0f, baseline),
                        Offset(size.width, baseline),
                        strokeWidth = 2f,
                    )
                    val group = size.width / rows.size
                    rows.forEachIndexed { index, row ->
                        val x = group * index + group / 2f
                        val incomeHeight = incomeHeights[index] * (size.height * .42f)
                        val expenseHeight = expenseHeights[index] * (size.height * .42f)
                        drawRect(Color(0xFF2C7A68), Offset(x - 8f, baseline - incomeHeight), Size(7f, incomeHeight))
                        drawRect(Color(0xFFC94C4C), Offset(x + 1f, baseline), Size(7f, expenseHeight))
                    }
                }
                selectedIndex?.let { index ->
                    rows.getOrNull(index)?.let { row ->
                        Surface(color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.92f)) {
                            Text(
                                "${row.first}: income %.2f, expenses %.2f".format(row.second.first, row.second.second),
                                Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
                Row(Modifier.fillMaxWidth()) {
                    rows.forEachIndexed { index, row ->
                        Box(Modifier.width((chartWidth / rows.size).dp)) {
                            if (index % labelStep == 0 || index == rows.lastIndex) {
                                Text(
                                    row.first.takeLast(5),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun LegendDot(color: Color, label: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.size(10.dp)) {
            androidx.compose.foundation.Canvas(Modifier.fillMaxSize()) { drawCircle(color) }
        }
        Text(label, style = MaterialTheme.typography.bodySmall)
    }
}
