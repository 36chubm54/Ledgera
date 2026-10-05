package app.ledgera.dashboard

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import app.ledgera.model.DashboardAsset
import app.ledgera.model.DashboardAssetBreakdown
import app.ledgera.model.DashboardCapitalPoint
import app.ledgera.model.DashboardGoal
import app.ledgera.model.DashboardAssetSnapshotUpdate
import app.ledgera.ui.LedgerDateField
import app.ledgera.validation.DateValidation
import app.ledgera.validation.currentLedgerDate
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.math.roundToInt

private sealed class DashboardDialog {
    data object CreateAsset : DashboardDialog()
    data object ManageAssets : DashboardDialog()
    data object RefreshAssets : DashboardDialog()
    data class EditAsset(val asset: DashboardAsset) : DashboardDialog()
    data object CreateGoal : DashboardDialog()
}

private data class AssetRefreshRow(
    val asset: DashboardAsset,
    val value: String,
    val note: String,
)

@Composable
fun DashboardScreen(viewModel: DashboardViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsState()
    var dialog by remember { mutableStateOf<DashboardDialog?>(null) }
    BoxWithConstraints(modifier.fillMaxSize()) {
        val isWideLayout = maxWidth >= 900.dp
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("Dashboard", Modifier.weight(1f), style = MaterialTheme.typography.headlineLarge)
                if (state.loading) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
            }
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            state.notice?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
            state.snapshot?.let { snapshot ->
                SummaryCard(snapshot)
                if (!isWideLayout) {
                    CapitalCard(snapshot.capital)
                    AssetStructureCard(snapshot.assetBreakdown, state.selectedCategory, viewModel::selectCategory)
                } else {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Box(Modifier.weight(1.25f)) { CapitalCard(snapshot.capital) }
                        Box(Modifier.weight(.75f)) { AssetStructureCard(snapshot.assetBreakdown, state.selectedCategory, viewModel::selectCategory) }
                    }
                }
                GoalsCard(snapshot.goals, state.selectedGoalId, viewModel, { dialog = DashboardDialog.CreateGoal }, Modifier.fillMaxWidth())
                AssetsCard(
                    snapshot.assets,
                    state.selectedAssetId,
                    state.selectedCategory,
                    viewModel,
                    onCreate = { dialog = DashboardDialog.CreateAsset },
                    onEdit = { asset -> dialog = DashboardDialog.EditAsset(asset) },
                    onRefresh = { dialog = DashboardDialog.RefreshAssets },
                )
            }
        }
    }
    dialog?.let {
        DashboardDialogHost(
            dialog = it,
            viewModel = viewModel,
            close = { dialog = null },
            createAsset = { dialog = DashboardDialog.CreateAsset },
        )
    }
}

@Composable
private fun SummaryCard(snapshot: app.ledgera.model.DashboardSnapshot) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Overview", style = MaterialTheme.typography.titleLarge)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Metric("Net worth", "${snapshot.netWorth} ${snapshot.baseCurrency}", Modifier.weight(1f))
                Metric("Total assets", "${snapshot.totalAssets} ${snapshot.baseCurrency}", Modifier.weight(1f))
                Metric("Goals", "${snapshot.completedGoalCount} / ${snapshot.totalGoalCount} completed", Modifier.weight(1f))
            }
            Text("Assets: ${snapshot.activeAssetCount} active / ${snapshot.totalAssetCount} total", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun Metric(label: String, value: String, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleMedium)
    }
}

@Composable
private fun CapitalCard(points: List<DashboardCapitalPoint>) {
    var hoveredIndex by remember(points) { mutableStateOf<Int?>(null) }
    Card(Modifier.fillMaxWidth().height(300.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Capital dynamics", style = MaterialTheme.typography.titleLarge)
            Text("Current capital based on wallets and tracked assets", color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (points.isEmpty()) Text("No capital data", color = MaterialTheme.colorScheme.onSurfaceVariant)
            else {
                CapitalChart(points, { hoveredIndex = it }, Modifier.fillMaxWidth().weight(1f))
                Box(Modifier.fillMaxWidth().height(28.dp)) {
                    hoveredIndex?.let { index -> points.getOrNull(index)?.let { point ->
                        Surface(color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .94f)) {
                            Text("${point.month}: ${point.balanceBase}", Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
                        }
                    } }
                }
            }
        }
    }
}

@Composable
private fun CapitalChart(points: List<DashboardCapitalPoint>, onHover: (Int?) -> Unit, modifier: Modifier) {
    val values = points.map { it.balanceBase.toDoubleOrNull() ?: 0.0 }
    val dataMin = values.minOrNull() ?: 0.0
    val dataMax = values.maxOrNull() ?: 0.0
    val padding = maxOf((dataMax - dataMin) * .12, kotlin.math.abs(dataMin) * .02, kotlin.math.abs(dataMax) * .02, 1.0)
    val chartMin = dataMin - padding
    val chartSpan = (dataMax + padding - chartMin).coerceAtLeast(1.0)
    BoxWithConstraints(modifier) {
        val scrollState = rememberScrollState()
        val contentWidth = maxOf(maxWidth, (points.size * 96).dp)
        Column(Modifier.width(contentWidth).horizontalScroll(scrollState)) {
            Box(Modifier.width(contentWidth).height(170.dp)) {
                Canvas(
                    Modifier.fillMaxSize().pointerInput(points) {
                        awaitPointerEventScope {
                            while (true) {
                                val event = awaitPointerEvent()
                                val position = event.changes.firstOrNull()?.position
                                if (event.type == PointerEventType.Exit) onHover(null)
                                else onHover(position?.let {
                                    val inset = 28f
                                    val usableWidth = (size.width - inset * 2f).coerceAtLeast(1f)
                                    (((it.x - inset) / usableWidth) * points.lastIndex.coerceAtLeast(0)).roundToInt().coerceIn(0, points.lastIndex.coerceAtLeast(0))
                                })
                            }
                        }
                    },
                ) {
                    val horizontalInset = 28f
                    val usableWidth = (size.width - horizontalInset * 2f).coerceAtLeast(1f)
                    val coords = values.mapIndexed { index, value ->
                        val x = if (values.size == 1) size.width / 2f
                        else horizontalInset + index.toFloat() / values.lastIndex * usableWidth
                        Offset(x, size.height - 24f - (size.height - 42f) * ((value - chartMin) / chartSpan).toFloat())
                    }
                    drawLine(Color.Gray.copy(alpha = .45f), Offset(horizontalInset, size.height - 24f), Offset(size.width - horizontalInset, size.height - 24f), 1f)
                    coords.zipWithNext().forEach { (a, b) -> drawLine(Color(0xFF2E8B70), a, b, 4f, StrokeCap.Round) }
                    coords.forEach { drawCircle(Color(0xFF2E8B70), 4f, it) }
                }
                DashboardChartLabels(
                    labels = points.map { it.month },
                    show = { true },
                    horizontalInset = 28.dp,
                    modifier = Modifier.align(Alignment.BottomStart),
                )
            }
        }
    }
}

@Composable
private fun DashboardChartLabels(
    labels: List<String>,
    show: (Int) -> Boolean,
    modifier: Modifier = Modifier,
    horizontalInset: Dp = 0.dp,
) {
    val visibleLabels = labels.mapIndexedNotNull { index, label ->
        if (show(index)) index to label else null
    }
    Layout(
        content = {
            visibleLabels.forEach { (_, label) ->
                Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
private fun AssetStructureCard(rows: List<DashboardAssetBreakdown>, selected: String?, onSelected: (String?) -> Unit) {
    Card(Modifier.fillMaxWidth().height(300.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Asset structure", style = MaterialTheme.typography.titleLarge)
            Text("Active assets by category", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Row(Modifier.fillMaxWidth().weight(1f), verticalAlignment = Alignment.CenterVertically) {
                AssetDonut(rows, selected, onSelected, Modifier.size(190.dp))
                Column(Modifier.padding(start = 12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    rows.forEach { row ->
                        Row(Modifier.clickable { onSelected(if (selected == row.label) null else row.label) }, verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(11.dp).background(parseColor(row.color), RoundedCornerShape(3.dp)))
                            Text("  ${row.label.replaceFirstChar { it.uppercase() }}  ${row.amountBase}")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AssetDonut(rows: List<DashboardAssetBreakdown>, selected: String?, onSelected: (String?) -> Unit, modifier: Modifier) {
    val total = rows.sumOf { it.amountBase.toDoubleOrNull() ?: 0.0 }.coerceAtLeast(1.0)
    Canvas(modifier.pointerInput(rows, selected) {
        detectTapGestures { position ->
            val center = Offset(size.width / 2f, size.height / 2f)
            val dx = position.x - center.x
            val dy = position.y - center.y
            val radius = sqrt(dx * dx + dy * dy)
            val minDimension = minOf(size.width, size.height).toFloat()
            if (radius < minDimension * .20f || radius > minDimension * .5f) return@detectTapGestures
            val angle = (Math.toDegrees(atan2(dy.toDouble(), dx.toDouble())) + 450.0) % 360.0
            var cursor = 0.0
            rows.firstOrNull { row ->
                val sweep = (row.amountBase.toDoubleOrNull() ?: 0.0) / total * 360.0
                val match = angle >= cursor && angle < cursor + sweep
                cursor += sweep
                match
            }?.let { row -> onSelected(if (selected == row.label) null else row.label) }
        }
    }) {
        var start = -90f
        rows.forEach { row ->
            val sweep = ((row.amountBase.toDoubleOrNull() ?: 0.0) / total * 360.0).toFloat()
            val offset = if (selected == row.label) 7f else 0f
            val radians = Math.toRadians((start + sweep / 2f).toDouble())
            val shift = Offset(cos(radians).toFloat() * offset, sin(radians).toFloat() * offset)
            drawArc(
                color = parseColor(row.color),
                startAngle = start,
                sweepAngle = (sweep - 7f).coerceAtLeast(0f),
                useCenter = false,
                style = Stroke(18f, cap = StrokeCap.Round),
                size = Size(size.minDimension, size.minDimension),
                topLeft = Offset((size.width - size.minDimension) / 2f, (size.height - size.minDimension) / 2f) + shift,
            )
            start += sweep
        }
    }
}

@Composable
private fun GoalsCard(goals: List<DashboardGoal>, selectedId: Long?, viewModel: DashboardViewModel, onCreate: () -> Unit, modifier: Modifier) {
    Card(modifier) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Goals", style = MaterialTheme.typography.titleLarge)
            if (goals.isEmpty()) Text("Goals have not been added", color = MaterialTheme.colorScheme.onSurfaceVariant)
            goals.forEach { goal ->
                val target = goal.targetAmountMinor.toDouble().coerceAtLeast(1.0)
                val progress = (goal.currentAmountMinor / target).toFloat().coerceIn(0f, 1f)
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(if (selectedId == goal.id) MaterialTheme.colorScheme.primaryContainer else Color.Transparent).clickable { viewModel.selectGoal(goal.id) }.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(goal.title)
                        LinearProgressIndicator({ progress }, Modifier.fillMaxWidth().padding(vertical = 4.dp))
                        Text("${goal.currentAmount} / ${goal.targetAmount} ${goal.currency} (${(progress * 100).toInt()}%)", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Text(if (goal.isCompleted) "Completed" else goal.targetDate ?: "No date")
                    if (!goal.isCompleted) TextButton(onClick = { viewModel.setGoalCompleted(goal.id, true) }) { Text("Complete") }
                    TextButton(onClick = { viewModel.deleteGoal(goal.id) }) { Text("Delete") }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                Button(onClick = onCreate) { Text("Create goal") }
            }
        }
    }
}

@Composable
private fun AssetsCard(
    assets: List<DashboardAsset>,
    selectedId: Long?,
    category: String?,
    viewModel: DashboardViewModel,
    onCreate: () -> Unit,
    onEdit: (DashboardAsset) -> Unit,
    onRefresh: () -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("Assets", style = MaterialTheme.typography.titleLarge)
            Text("Review current values, status, and snapshot details for tracked assets.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            val visibleAssets = assets.filter { category == null || it.category == category }
            visibleAssets.forEach { asset ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(if (selectedId == asset.id) MaterialTheme.colorScheme.primaryContainer else Color.Transparent).clickable { viewModel.selectAsset(asset) }.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(asset.name, Modifier.weight(1f)); Text("${asset.currentValue} ${asset.currency}"); Text(if (asset.isActive) "Active" else "Inactive", Modifier.padding(start = 12.dp))
                }
                if (selectedId == asset.id) {
                    Column(Modifier.padding(start = 8.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(asset.description.ifBlank { "No description" }, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("Latest snapshot: ${asset.currentSnapshotDate ?: "No snapshot"}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            val selected = assets.firstOrNull { it.id == selectedId }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onCreate) { Text("Create") }
                OutlinedButton(onClick = { selected?.let(onEdit) }, enabled = selected != null) { Text("Edit") }
                OutlinedButton(onClick = { selected?.let { viewModel.setAssetActive(it.id, !it.isActive) } }, enabled = selected != null) {
                    Text(if (selected?.isActive == true) "Deactivate" else "Activate")
                }
                Spacer(Modifier.weight(1f))
                OutlinedButton(onClick = onRefresh) { Text("Refresh assets") }
            }
        }
    }
}

@Composable
private fun DashboardDialogHost(
    dialog: DashboardDialog,
    viewModel: DashboardViewModel,
    close: () -> Unit,
    createAsset: () -> Unit,
) {
    when (dialog) {
        DashboardDialog.CreateAsset -> AssetDialog(null, viewModel, close)
        DashboardDialog.ManageAssets -> AssetManagementDialog(viewModel, close, createAsset)
        DashboardDialog.RefreshAssets -> AssetRefreshDialog(viewModel, close)
        is DashboardDialog.EditAsset -> AssetDialog(dialog.asset, viewModel, close)
        DashboardDialog.CreateGoal -> GoalDialog(viewModel, close)
    }
}

@Composable
private fun AssetDialog(asset: DashboardAsset?, viewModel: DashboardViewModel, close: () -> Unit) {
    var name by remember(asset) { mutableStateOf(asset?.name ?: "") }
    var category by remember(asset) { mutableStateOf(asset?.category ?: "bank") }
    var currency by remember(asset) { mutableStateOf(asset?.currency ?: "KZT") }
    var value by remember(asset) { mutableStateOf(asset?.currentValue ?: "0") }
    var date by remember(asset) { mutableStateOf(asset?.currentSnapshotDate ?: "") }
    var description by remember(asset) { mutableStateOf(asset?.description ?: "") }
    val validValue = value.toDoubleOrNull()?.let { it.isFinite() && it >= 0 } == true
    val validDate = DateValidation.formatGuiDateToYmd(date) != null
    val invalid = name.isBlank() || currency.trim().length != 3 || !validValue || !validDate
    val validationMessages = buildList {
        if (name.isBlank()) add("Name is required")
        if (currency.trim().length != 3) add("Currency must contain 3 letters")
        if (!validValue) add("Value must be zero or greater")
        if (!validDate) add("Date must be a valid DD.MM.YYYY value")
    }
    AlertDialog(
        onDismissRequest = close,
        title = { Text(if (asset == null) "Create asset" else "Edit asset") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text("Name") }, singleLine = true)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { listOf("bank", "crypto", "cash", "other").forEach { FilterChip(category == it, { category = it }, label = { Text(it) }) } }
                OutlinedTextField(currency, { currency = it.uppercase() }, label = { Text("Currency") }, singleLine = true)
                OutlinedTextField(value, { value = it }, label = { Text("Value") }, singleLine = true)
                LedgerDateField(
                    value = date,
                    onValueChange = { date = it },
                    label = "Snapshot date",
                    modifier = Modifier.fillMaxWidth(.55f),
                    required = true,
                    allowFuture = false,
                    externalError = if (!validDate) "Date must be a valid DD.MM.YYYY value" else null,
                    showErrorOutline = false,
                    showErrorText = false,
                )
                OutlinedTextField(description, { description = it }, label = { Text("Description") }, singleLine = true)
                validationMessages.forEach { message ->
                    Text(message, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    DateValidation.formatGuiDateToYmd(date)?.let { snapshotDate ->
                        if (asset == null) viewModel.createAsset(name, category, currency, value, snapshotDate, description)
                        else viewModel.updateAsset(asset.id, name, category, currency, value, snapshotDate, description)
                        close()
                    }
                },
                enabled = !invalid,
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = close) { Text("Cancel") } },
    )
}

@Composable
private fun AssetManagementDialog(viewModel: DashboardViewModel, close: () -> Unit, createAsset: () -> Unit) {
    val state by viewModel.state.collectAsState()
    var editing by remember { mutableStateOf<DashboardAsset?>(null) }
    var selectedId by remember { mutableStateOf<Long?>(null) }
    val assets = state.snapshot?.assets.orEmpty()
    val selected = assets.firstOrNull { it.id == selectedId }
    AlertDialog(
        onDismissRequest = close,
        title = { Text("Manage assets") },
        text = {
            Column(Modifier.height(390.dp)) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp)) {
                    Text("Name", Modifier.weight(1.2f), color = MaterialTheme.colorScheme.primary)
                    Text("Category", Modifier.weight(.8f), color = MaterialTheme.colorScheme.primary)
                    Text("Currency", Modifier.weight(.7f), color = MaterialTheme.colorScheme.primary)
                    Text("Created", Modifier.weight(1f), color = MaterialTheme.colorScheme.primary)
                    Text("Status", Modifier.weight(.8f), color = MaterialTheme.colorScheme.primary)
                }
                Column(Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState())) {
                    assets.forEach { asset ->
                        val isSelected = asset.id == selectedId
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(4.dp))
                                .background(if (isSelected) MaterialTheme.colorScheme.primaryContainer else Color.Transparent)
                                .clickable { selectedId = asset.id }
                                .padding(horizontal = 8.dp, vertical = 7.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(asset.name, Modifier.weight(1.2f))
                            Text(asset.category, Modifier.weight(.8f))
                            Text(asset.currency, Modifier.weight(.7f))
                            Text(asset.createdAt, Modifier.weight(1f))
                            Text(if (asset.isActive) "Active" else "Inactive", Modifier.weight(.8f))
                        }
                    }
                }
            }
        },
        confirmButton = {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = createAsset) { Text("Create") }
                OutlinedButton(onClick = { selected?.let { editing = it } }, enabled = selected != null) { Text("Edit") }
                OutlinedButton(
                    onClick = { selected?.let { viewModel.setAssetActive(it.id, !it.isActive) } },
                    enabled = selected != null,
                ) { Text(if (selected?.isActive == true) "Deactivate" else "Activate") }
                Spacer(Modifier.weight(1f))
                TextButton(onClick = close) { Text("Close") }
            }
        },
        dismissButton = {},
    )
    editing?.let { asset -> AssetDialog(asset, viewModel) { editing = null } }
}

@Composable
private fun AssetRefreshDialog(viewModel: DashboardViewModel, close: () -> Unit) {
    val state by viewModel.state.collectAsState()
    val assets = state.snapshot?.assets.orEmpty().filter { it.isActive }
    var date by remember { mutableStateOf(DateValidation.formatYmd(currentLedgerDate())) }
    var rows by remember(assets) {
        mutableStateOf(assets.map { asset -> AssetRefreshRow(asset, asset.currentValue, "") })
    }
    val validDate = DateValidation.formatGuiDateToYmd(date) != null
    val hasInvalidValue = rows.any { row ->
        row.value.isNotBlank() && (row.value.toDoubleOrNull()?.let { it.isFinite() && it >= 0 } != true)
    }
    val canSave = validDate && !hasInvalidValue
    AlertDialog(
        onDismissRequest = close,
        title = { Text("Refresh assets") },
        text = {
            Column(
                Modifier.height(480.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("Fill only assets that need updating. Empty rows will be skipped.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                LedgerDateField(
                    value = date,
                    onValueChange = { date = it },
                    label = "Snapshot date",
                    required = true,
                    allowFuture = false,
                    externalError = if (!validDate) "Date must be a valid DD.MM.YYYY value" else null,
                    showErrorOutline = false,
                    showErrorText = false,
                )
                Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Asset", Modifier.weight(1.1f), color = MaterialTheme.colorScheme.primary)
                    Text("Current", Modifier.weight(.9f), color = MaterialTheme.colorScheme.primary)
                    Text("Currency", Modifier.weight(.55f), color = MaterialTheme.colorScheme.primary)
                    Text("New value", Modifier.weight(1f), color = MaterialTheme.colorScheme.primary)
                    Text("Note", Modifier.weight(1f), color = MaterialTheme.colorScheme.primary)
                }
                rows.forEachIndexed { index, row ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(row.asset.name, Modifier.weight(1.1f))
                        Text(row.asset.currentValue, Modifier.weight(.9f), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(row.asset.currency, Modifier.weight(.55f))
                        OutlinedTextField(
                            value = row.value,
                            onValueChange = { value -> rows = rows.updated(index, row.copy(value = value)) },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                        )
                        OutlinedTextField(
                            value = row.note,
                            onValueChange = { note -> rows = rows.updated(index, row.copy(note = note)) },
                            modifier = Modifier.weight(1f),
                            singleLine = true,
                        )
                    }
                }
                if (!validDate) {
                    Text("Date must be a valid DD.MM.YYYY value", color = MaterialTheme.colorScheme.error)
                }
                if (hasInvalidValue) {
                    Text("Every new value must be zero or greater", color = MaterialTheme.colorScheme.error)
                }
                Text("Invalid values block saving. Empty values are ignored.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    DateValidation.formatGuiDateToYmd(date)?.let { snapshotDate ->
                        viewModel.saveAssetSnapshots(
                            rows.map { row -> DashboardAssetSnapshotUpdate(row.asset.id, row.value, row.note) },
                            snapshotDate,
                        )
                        close()
                    }
                },
                enabled = canSave,
            ) { Text("Save snapshots") }
        },
        dismissButton = { TextButton(onClick = close) { Text("Cancel") } },
    )
}

private fun <T> List<T>.updated(index: Int, value: T): List<T> =
    toMutableList().also { it[index] = value }

@Composable
private fun GoalDialog(viewModel: DashboardViewModel, close: () -> Unit) {
    var title by remember { mutableStateOf("") }; var target by remember { mutableStateOf("") }; var currency by remember { mutableStateOf("KZT") }; var date by remember { mutableStateOf("") }
    val validTarget = target.toDoubleOrNull()?.let { it.isFinite() && it > 0 } == true
    val validDate = date.isBlank() || DateValidation.formatGuiDateToYmd(date) != null
    val invalid = title.isBlank() || !validTarget || currency.length != 3 || !validDate
    AlertDialog(onDismissRequest = close, title = { Text("Create goal") }, text = { Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        OutlinedTextField(title, { title = it }, label = { Text("Title") }, singleLine = true)
        OutlinedTextField(target, { target = it }, label = { Text("Target amount") }, singleLine = true)
        OutlinedTextField(currency, { currency = it.uppercase() }, label = { Text("Currency") }, singleLine = true)
        LedgerDateField(
            value = date,
            onValueChange = { date = it },
            label = "Target date",
            modifier = Modifier.fillMaxWidth(.55f),
            required = false,
            allowFuture = true,
            externalError = if (!validDate) "Date must be a valid DD.MM.YYYY value" else null,
            showErrorOutline = false,
            showErrorText = false,
        )
        if (title.isBlank()) Text("Title is required", color = MaterialTheme.colorScheme.error)
        if (!validTarget) Text("Target amount must be greater than zero", color = MaterialTheme.colorScheme.error)
        if (currency.length != 3) Text("Currency must contain 3 letters", color = MaterialTheme.colorScheme.error)
        if (!validDate) Text("Date must be a valid DD.MM.YYYY value", color = MaterialTheme.colorScheme.error)
    } }, confirmButton = { Button(onClick = { viewModel.createGoal(title, target, currency, DateValidation.formatGuiDateToYmd(date), ""); close() }, enabled = !invalid) { Text("Save") } }, dismissButton = { TextButton(onClick = close) { Text("Cancel") } })
}

private fun parseColor(value: String): Color = value.removePrefix("#").toLongOrNull(16)?.let { Color((0xFF000000L or it).toInt()) } ?: Color.Gray
