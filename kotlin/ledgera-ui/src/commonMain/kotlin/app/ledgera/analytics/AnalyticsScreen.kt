package app.ledgera.analytics

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.TextButton
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.unit.Dp
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
        Card {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
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
            if (snapshot.capital.isEmpty() && snapshot.categories.isEmpty() && snapshot.monthly.isEmpty()) {
                Card(Modifier.fillMaxWidth()) {
                    Text(
                        "No analytics data for the selected period",
                        Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun BreakdownSummaryCard(title: String, rows: List<AnalyticsBreakdownRow>) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge)
            if (rows.isEmpty()) {
                Text("No breakdown data", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                rows.chunked(4).forEach { rowGroup ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        rowGroup.forEach { row ->
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(row.label, maxLines = 1)
                                Text(
                                    "${"%.2f".format(row.amountBase)} (${row.recordCount})",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                        repeat(4 - rowGroup.size) { Spacer(Modifier.weight(1f)) }
                    }
                }
            }
        }
    }
}

@Composable
private fun SummaryCard(summary: app.ledgera.model.AnalyticsSummary) {
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
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
    Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("Monthly report", style = MaterialTheme.typography.titleLarge)
        Row(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
            Text("Month", Modifier.weight(1f), style = MaterialTheme.typography.labelLarge)
            Text("Income", Modifier.weight(1f), style = MaterialTheme.typography.labelLarge)
            Text("Expenses", Modifier.weight(1f), style = MaterialTheme.typography.labelLarge)
            Text("Cashflow", Modifier.weight(1f), style = MaterialTheme.typography.labelLarge)
            Text("Savings %", Modifier.weight(1f), style = MaterialTheme.typography.labelLarge)
        }
        rows.forEach { row ->
            Row(Modifier.fillMaxWidth().padding(vertical = 5.dp)) {
                Text(row.month, Modifier.weight(1f))
                Text("%.2f".format(row.incomeBase), Modifier.weight(1f))
                Text("%.2f".format(row.expensesBase), Modifier.weight(1f))
                Text("%.2f".format(row.cashflowBase), Modifier.weight(1f))
                Text("%.1f%%".format(row.savingsRate), Modifier.weight(1f))
            }
        }
    } }
}

@Composable
private fun ChartCard(title: String, content: @Composable () -> Unit) {
    Card { Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(title, style = MaterialTheme.typography.titleLarge)
        Box(Modifier.fillMaxWidth().height(340.dp)) { content() }
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
                        CashflowChart(daily, labelStep = 3, chartHeight = 320.dp)
                    }
                }
            } else {
                Row(
                    Modifier.fillMaxWidth().height(420.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    InfographicCard("Expenses by category", Modifier.weight(1f).fillMaxHeight()) {
                        SelectorRow("Period", if (piePeriod == "all_time") "All time" else piePeriod, listOf("all_time") + months, onPiePeriodChange, onRefresh)
                        CategoryChart(breakdown)
                    }
                    InfographicCard("Daily cashflow", Modifier.weight(1f).fillMaxHeight()) {
                        SelectorRow("Month", dailyMonth.ifEmpty { months.lastOrNull().orEmpty() }, months, onDailyMonthChange, onRefresh)
                        CashflowChart(daily, labelStep = 3, chartHeight = 320.dp)
                    }
                }
            }
        }
        InfographicCard("Monthly cashflow", Modifier.fillMaxWidth()) {
            SelectorRow("Year", monthlyYear.ifEmpty { years.lastOrNull().orEmpty() }, years, onMonthlyYearChange, onRefresh)
            CashflowChart(monthly, labelStep = 1, stretchToWidth = true)
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
    var selected by remember(rows) { mutableStateOf<AnalyticsBreakdownRow?>(null) }
    var showOtherDialog by remember(rows) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth(), horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally) {
        Box(Modifier.size(290.dp), contentAlignment = androidx.compose.ui.Alignment.Center) {
            InteractiveDonutChart(rows, selected?.label, Modifier.fillMaxSize()) { selected = it }
            selected?.let { row ->
                Column(
                    Modifier.padding(12.dp),
                    horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
                ) {
                    Text(row.label, style = MaterialTheme.typography.labelLarge, maxLines = 2)
                    Text("%.2f".format(row.amountBase))
                    Text("%.1f%%".format(row.amountBase / total * 100.0), style = MaterialTheme.typography.bodySmall)
                    if (row.isOther && row.details.isNotEmpty()) {
                        Button(onClick = { showOtherDialog = true }) { Text("More...") }
                    }
                }
            }
        }
    }
    if (showOtherDialog && selected?.isOther == true) {
        AlertDialog(
            onDismissRequest = { showOtherDialog = false },
            title = { Text("Other categories") },
            text = {
                Column(
                    Modifier.height(220.dp).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    selected?.details?.forEach { detail ->
                        Text("${detail.label}: %.2f (%d)".format(detail.amountBase, detail.recordCount))
                    }
                }
            },
            confirmButton = { TextButton(onClick = { showOtherDialog = false }) { Text("Close") } },
        )
    }
}

@Composable
private fun LineChart(points: List<Pair<String, Double>>) {
    if (points.isEmpty()) {
        Text("No data")
        return
    }
    val lineColor = MaterialTheme.colorScheme.primary
    val axisColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.35f)
    var selectedIndex by remember(points) { mutableStateOf<Int?>(null) }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val chartWidth = maxOf(maxWidth, (points.size * 96).dp)
        Column(Modifier.width(chartWidth).horizontalScroll(rememberScrollState())) {
            Box(Modifier.width(chartWidth).height(310.dp)) {
                Canvas(Modifier.fillMaxSize().pointerInput(points) {
                awaitPointerEventScope {
                    while (true) {
                        val x = awaitPointerEvent().changes.firstOrNull()?.position?.x ?: continue
                        selectedIndex = if (points.size == 1) 0 else {
                            (x / size.width * points.size).toInt().coerceIn(0, points.lastIndex)
                        }
                    }
                }
                }) {
                val values = points.map { it.second }
                val dataMin = values.minOrNull() ?: 0.0
                val dataMax = values.maxOrNull() ?: 0.0
                val dataSpan = dataMax - dataMin
                val padding = max(max(dataSpan * 0.12, kotlin.math.abs(dataMax) * 0.02), 1.0)
                val minValue = dataMin - padding
                val span = max(dataSpan + padding * 2.0, 1.0)
                val horizontalInset = 28f
                val usableWidth = (size.width - horizontalInset * 2f).coerceAtLeast(1f)
                val coordinates = values.mapIndexed { index, value ->
                    val x = if (points.size == 1) size.width / 2f
                    else horizontalInset + index.toFloat() / points.lastIndex * usableWidth
                    Offset(x, size.height - ((value - minValue) / span * size.height).toFloat())
                }
                drawLine(
                    axisColor,
                    Offset(horizontalInset, size.height / 2f),
                    Offset(size.width - horizontalInset, size.height / 2f),
                    strokeWidth = 1f,
                )
                coordinates.zipWithNext().forEach { (a, b) -> drawLine(lineColor, a, b, strokeWidth = 4f) }
                coordinates.forEach { drawCircle(lineColor, 4f, it) }
            }
                ChartLabels(
                    labels = points.map { it.first },
                    show = { index -> index == 0 || index == points.lastIndex || points.size <= 8 || index % 2 == 0 },
                    horizontalInset = 28.dp,
                    modifier = Modifier.align(Alignment.BottomStart),
                )
            }
            selectedIndex?.let { index ->
                points.getOrNull(index)?.let { point ->
                    Surface(color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.94f)) {
                        Text("${point.first}: %.2f".format(point.second), Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun InteractiveDonutChart(
    rows: List<AnalyticsBreakdownRow>,
    selectedLabel: String?,
    modifier: Modifier,
    onSelected: (AnalyticsBreakdownRow?) -> Unit,
) {
    val total = rows.sumOf { it.amountBase }
    val sweeps = rows.mapIndexed { index, row ->
        val targetSweep = (row.amountBase / total * 360.0).toFloat()
        animateFloatAsState(targetSweep, label = "pie-sweep-$index").value
    }
    val offsets = rows.mapIndexed { index, row ->
        animateFloatAsState(
            if (row.label == selectedLabel) 10f else 0f,
            label = "donut-offset-$index",
        ).value
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
                    val radius = kotlin.math.sqrt(dx * dx + dy * dy)
                    val diameter = minOf(size.width, size.height)
                    if (radius > diameter / 2f || radius < diameter * .18f) continue
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
        val strokeWidth = 16f
        var start = -90f
        rows.forEachIndexed { index, row ->
            val targetSweep = (row.amountBase / total * 360.0).toFloat()
            // Round caps extend past the arc endpoints, so leave enough angular room for a visible background gap.
            val sweep = (sweeps[index] - 8f).coerceAtLeast(0f)
            val color = if (row.isOther) Color(0xFF858585) else parseHexColor(row.color) ?: paletteColor(index)
            val midAngle = Math.toRadians((start + targetSweep / 2f).toDouble())
            val offset = Offset(
                kotlin.math.cos(midAngle).toFloat() * offsets[index],
                kotlin.math.sin(midAngle).toFloat() * offsets[index],
            )
            drawArc(
                color,
                start,
                sweep,
                false,
                style = Stroke(width = strokeWidth, cap = StrokeCap.Round),
                size = Size(diameter, diameter),
                topLeft = Offset((size.width - diameter) / 2f, (size.height - diameter) / 2f) + offset,
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
    saturation = 0.82f,
    value = 0.96f,
)

@Composable
private fun CashflowChart(
    rows: List<Pair<String, Pair<Double, Double>>>,
    labelStep: Int,
    stretchToWidth: Boolean = false,
    chartHeight: Dp = 190.dp,
) {
    if (rows.isEmpty()) {
        Text("No cashflow data", color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    val maxValue = rows.maxOf {
        max(kotlin.math.abs(it.second.first), kotlin.math.abs(it.second.second))
    }.coerceAtLeast(1.0)
    val axisColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.5f)
    var selectedIndex by remember(rows) { mutableStateOf<Int?>(null) }
    val incomeHeights = rows.mapIndexed { index, row ->
        animateFloatAsState(
            (kotlin.math.abs(row.second.first) / maxValue).toFloat(),
            label = "income-bar-$index",
        ).value
    }
    val expenseHeights = rows.mapIndexed { index, row ->
        animateFloatAsState(
            (kotlin.math.abs(row.second.second) / maxValue).toFloat(),
            label = "expense-bar-$index",
        ).value
    }
    Column(Modifier.fillMaxWidth()) {
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            LegendDot(Color(0xFF2C7A68), "Income")
            LegendDot(Color(0xFFC94C4C), "Expenses")
        }
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val chartWidth = if (stretchToWidth) {
                maxOf(560.dp, maxWidth, (rows.size * 48).dp)
            } else {
                maxOf(560.dp, (rows.size * 48).dp)
            }
            Box(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
                Column(Modifier.width(chartWidth)) {
                Canvas(
                    Modifier.fillMaxWidth().height(chartHeight).pointerInput(rows) {
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
                        drawRect(Color(0xFF2C7A68), Offset(x - 5f, baseline - incomeHeight), Size(10f, incomeHeight))
                        drawRect(Color(0xFFC94C4C), Offset(x - 5f, baseline), Size(10f, expenseHeight))
                    }
                }
                ChartLabels(
                    labels = rows.map { it.first.takeLast(5) },
                    show = { index -> index % labelStep == 0 || index == rows.lastIndex },
                    centerInGroups = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            }
            selectedIndex?.let { index ->
                rows.getOrNull(index)?.let { row ->
                    Text(
                        "${row.first}: income %.2f, expenses %.2f".format(row.second.first, row.second.second),
                        Modifier.fillMaxWidth().padding(top = 6.dp),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
    }
}

@Composable
private fun ChartLabels(
    labels: List<String>,
    show: (Int) -> Boolean,
    modifier: Modifier = Modifier,
    horizontalInset: Dp = 0.dp,
    centerInGroups: Boolean = false,
) {
    val visibleLabels = labels.mapIndexedNotNull { index, label ->
        if (show(index)) index to label else null
    }
    Layout(
        content = {
            visibleLabels.forEach { (_, label) ->
                Text(
                    label,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        modifier = modifier.height(20.dp).fillMaxWidth(),
    ) { measurables, constraints ->
        val placeables = measurables.map { it.measure(constraints.copy(minWidth = 0, minHeight = 0)) }
        val width = constraints.maxWidth
        val height = placeables.maxOfOrNull { it.height } ?: 0
        val inset = horizontalInset.roundToPx()
        val usableWidth = (width - inset * 2).coerceAtLeast(1)
        layout(width, height) {
            placeables.forEachIndexed { childIndex, placeable ->
                val dataIndex = visibleLabels[childIndex].first
                val targetX = if (labels.size == 1) {
                    width / 2
                } else if (centerInGroups) {
                    ((dataIndex + 0.5f) / labels.size * width).toInt()
                } else {
                    inset + (dataIndex.toFloat() / labels.lastIndex * usableWidth).toInt()
                }
                val x = (targetX - placeable.width / 2).coerceIn(0, width - placeable.width)
                placeable.place(x, 0)
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
