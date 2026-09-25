package app.ledgera.distribution

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.shape.RoundedCornerShape
import app.ledgera.model.DistributionItem
import app.ledgera.model.DistributionColumn
import app.ledgera.model.DistributionMonthlyResult

@Composable
fun DistributionScreen(viewModel: DistributionViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsState()
    var dialog by remember { mutableStateOf<DistributionDialog?>(null) }
    BoxWithConstraints(modifier.fillMaxSize()) {
        val narrow = maxWidth < 860.dp
        val contentModifier = if (narrow) {
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp)
        } else {
            Modifier.fillMaxSize().padding(16.dp)
        }
        Column(contentModifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Distribution", style = MaterialTheme.typography.headlineLarge)
            Card(Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(state.startMonth, viewModel::updateStartMonth, label = { Text("From") }, singleLine = true, modifier = Modifier.weight(1f))
                    OutlinedTextField(state.endMonth, viewModel::updateEndMonth, label = { Text("To") }, singleLine = true, modifier = Modifier.weight(1f))
                    Button(onClick = viewModel::refresh) { Text("Refresh") }
                }
            }
            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            state.notice?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
            if (state.loading && state.items.isEmpty() && state.history.isEmpty()) CircularProgressIndicator()
            if (narrow) {
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    StructurePane(state, viewModel, { dialog = it }, Modifier.fillMaxWidth().height(520.dp))
                    ResultsPane(state, viewModel, Modifier.fillMaxWidth().height(650.dp))
                }
            } else Row(Modifier.fillMaxWidth().height(650.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StructurePane(state, viewModel, { dialog = it }, Modifier.weight(0.34f).fillMaxHeight())
                ResultsPane(state, viewModel, Modifier.weight(0.66f).fillMaxHeight())
            }
        }
    }
    dialog?.let { DistributionDialogHost(it, viewModel) { dialog = null } }
}

private sealed class DistributionDialog {
    data object NewItem : DistributionDialog()
    data class NewSubitem(val parentItemId: Long) : DistributionDialog()
    data class EditNode(val id: Long, val subitem: Boolean, val initialName: String, val initialPct: String) : DistributionDialog()
    data class Rename(val id: Long, val subitem: Boolean, val initial: String) : DistributionDialog()
}

private sealed class DistributionTreeRow {
    data class Group(val name: String) : DistributionTreeRow()
    data class Item(val value: DistributionItem) : DistributionTreeRow()
}

@Composable
private fun StructurePane(state: DistributionUiState, viewModel: DistributionViewModel, openDialog: (DistributionDialog) -> Unit, modifier: Modifier) {
    Card(modifier) {
        Column(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Distribution structure", style = MaterialTheme.typography.titleLarge)
            val validation = state.validation
            Text(if (validation.isEmpty()) "Structure is valid" else validation.joinToString("\n") { it.message }, color = if (validation.isEmpty()) Color(0xFF18794E) else MaterialTheme.colorScheme.error)
            val groupedItems = state.items
                .groupBy { it.groupName.ifBlank { "Ungrouped" } }
                .toSortedMap()
            val treeRows = buildList {
                groupedItems.forEach { (group, groupItems) ->
                    add(DistributionTreeRow.Group(group))
                    if (group !in state.collapsedGroups) {
                        groupItems.forEach { add(DistributionTreeRow.Item(it)) }
                    }
                }
            }
            LazyColumn(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                items(treeRows, key = {
                    when (it) {
                        is DistributionTreeRow.Group -> "group-${it.name}"
                        is DistributionTreeRow.Item -> "item-${it.value.id}"
                    }
                }) { row ->
                    when (row) {
                        is DistributionTreeRow.Group -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            TextButton(onClick = { viewModel.toggleGroup(row.name) }) {
                                Text(if (row.name in state.collapsedGroups) "▸ ${row.name}" else "▾ ${row.name}")
                            }
                        }
                        is DistributionTreeRow.Item -> DistributionItemRow(row.value, state, viewModel, openDialog)
                    }
                }
            }
            val selectedItem = state.items.firstOrNull { it.id == state.selectedItemId }
            val selectedSubitem = selectedItem?.subitems?.firstOrNull { it.id == state.selectedSubitemId }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Button(onClick = { openDialog(DistributionDialog.NewItem) }, modifier = Modifier.weight(0.88f)) { Text("+ Item") }
                Button(
                    onClick = { state.selectedItemId?.let { openDialog(DistributionDialog.NewSubitem(it)) } },
                    enabled = state.selectedItemId != null,
                    modifier = Modifier.weight(1.35f),
                ) { Text("+ Subitem") }
                OutlinedButton(
                    onClick = {
                        selectedSubitem?.let { openDialog(DistributionDialog.EditNode(it.id, true, it.name, it.pct.toString())) }
                            ?: selectedItem?.let { openDialog(DistributionDialog.EditNode(it.id, false, it.name, it.pct.toString())) }
                    },
                    enabled = selectedItem != null,
                    modifier = Modifier.weight(0.88f),
                ) { Text("Edit") }
                OutlinedButton(
                    onClick = {
                        if (selectedSubitem != null) {
                            viewModel.deleteSubitem(selectedSubitem.id)
                        } else if (selectedItem != null) {
                            viewModel.deleteItem(selectedItem.id)
                        }
                    },
                    enabled = selectedItem != null,
                    modifier = Modifier.weight(0.88f),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error),
                ) { Text("Delete") }
            }
        }
    }
}

@Composable
private fun DistributionItemRow(item: DistributionItem, state: DistributionUiState, viewModel: DistributionViewModel, openDialog: (DistributionDialog) -> Unit) {
    val id = "item-${item.id}"
    val expanded = id in state.expandedIds
    Column {
        val itemSelected = state.selectedItemId == item.id && state.selectedSubitemId == null
        Row(
            Modifier.fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(if (itemSelected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant)
                .then(if (itemSelected) Modifier.border(2.dp, MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp)) else Modifier)
                .clickable { viewModel.selectItem(item.id) }
                .padding(horizontal = 6.dp, vertical = 3.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (item.subitems.isNotEmpty()) {
                Box(
                    Modifier.width(34.dp).clickable { viewModel.toggleExpanded(id) },
                    contentAlignment = Alignment.Center,
                ) { Text(if (expanded) "▾" else "▸") }
            } else {
                Spacer(Modifier.width(34.dp))
            }
            Text(item.name, Modifier.weight(1f))
            Text("${"%.2f".format(item.pct)}%")
        }
        if (expanded) item.subitems.forEach { subitem ->
            val subitemSelected = state.selectedSubitemId == subitem.id
            Row(
                Modifier.fillMaxWidth().padding(start = 34.dp).clip(RoundedCornerShape(8.dp))
                    .background(if (subitemSelected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .55f))
                    .then(if (subitemSelected) Modifier.border(2.dp, MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp)) else Modifier)
                    .clickable { viewModel.selectSubitem(item.id, subitem.id) }
                    .padding(horizontal = 6.dp, vertical = 3.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(subitem.name, Modifier.weight(1f))
                Text("${"%.2f".format(subitem.pct)}%")
            }
        }
    }
}

@Composable
private fun ResultsPane(state: DistributionUiState, viewModel: DistributionViewModel, modifier: Modifier) {
    val frozen = state.frozenRows.associateBy { it.month }
    val live = state.history.associateBy { it.month }
    val months = (frozen.keys + live.keys).sorted()
    Card(modifier) {
        Column(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Distribution table", style = MaterialTheme.typography.titleLarge)
            if (months.isEmpty()) Text("No distribution data for the selected period", color = MaterialTheme.colorScheme.onSurfaceVariant)
            else {
                val columns = buildList {
                    val columnKeys = mutableSetOf<String>()
                    fun addColumn(column: DistributionColumn) {
                        if (columnKeys.add(column.key)) add(column)
                    }
                    addColumn(DistributionColumn("net_income", "Net income", ""))
                    state.items.forEach { item ->
                        addColumn(DistributionColumn("item_${item.id}", item.name, ""))
                        item.subitems.forEach { addColumn(DistributionColumn("sub_${it.id}", "  ${it.name}", "")) }
                    }
                    months.flatMap { frozen[it]?.columns.orEmpty() }
                        .filter { it.key != "month" && it.key != "fixed" && it.key != "net_income" }
                        .forEach(::addColumn)
                }
                val cellWidth = 145.dp
                val tableWidth = 190.dp + cellWidth * columns.size.toFloat()
                val tableScrollState = rememberScrollState()
                Row(Modifier.fillMaxWidth().horizontalScroll(tableScrollState).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Row(Modifier.width(tableWidth), verticalAlignment = Alignment.CenterVertically) {
                        Text("Month", Modifier.width(90.dp))
                        Text("Status", Modifier.width(100.dp))
                        columns.forEach { Text(it.label, Modifier.width(cellWidth)) }
                    }
                }
                Column(Modifier.weight(1f).fillMaxWidth().horizontalScroll(tableScrollState).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    months.forEach { month ->
                        val frozenRow = frozen[month]
                        val result = live[month]
                        val negative = frozenRow?.isNegative ?: result?.isNegative ?: false
                        val isAuto = frozenRow?.autoFixed == true
                        val rowColor = (if (negative) Color(0xFFE53935) else Color(0xFF2E8B70)).copy(alpha = .30f)
                        val frozenValues = frozenRow?.columns?.associateBy { it.key }.orEmpty()
                        val liveValues = buildMap {
                            result?.items?.forEach { item ->
                                put("item_${item.id}", item.amountBase)
                                item.subitems.forEach { put("sub_${it.id}", it.amountBase) }
                            }
                            put("net_income", result?.netIncomeBase ?: "-")
                        }
                        val rowShape = RoundedCornerShape(9.dp)
                        Row(
                            Modifier.width(tableWidth).clip(rowShape)
                                .background(rowColor)
                                .then(if (month == state.selectedMonth) Modifier.border(2.dp, MaterialTheme.colorScheme.primary, rowShape) else Modifier)
                                .clickable { viewModel.selectMonth(month) }
                                .padding(8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(month, Modifier.width(90.dp))
                            Text(if (isAuto) "Auto-fixed" else if (frozenRow != null) "Fixed" else "Live", Modifier.width(100.dp))
                            columns.forEach { column -> Text(frozenValues[column.key]?.value ?: liveValues[column.key] ?: "-", Modifier.width(cellWidth)) }
                        }
                    }
                }
                val selectedMonth = state.selectedMonth ?: months.lastOrNull()
                val selectedFrozen = selectedMonth?.let { frozen[it] }
                val selectedAuto = selectedFrozen?.autoFixed == true
                Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
                    Text(selectedMonth?.let { "Selected month: $it" } ?: "Select a month", Modifier.weight(1f))
                    Button(
                        onClick = { selectedMonth?.let(viewModel::toggleFixed) },
                        enabled = selectedMonth != null && !selectedAuto,
                    ) { Text(if (selectedFrozen == null) "Fix row" else "Unfix row") }
                }
            }
        }
    }
}

@Composable
private fun DistributionDialogHost(dialog: DistributionDialog, viewModel: DistributionViewModel, close: () -> Unit) {
    var name by remember(dialog) { mutableStateOf((dialog as? DistributionDialog.EditNode)?.initialName ?: "") }
    var group by remember(dialog) { mutableStateOf("") }
    var pct by remember(dialog) { mutableStateOf((dialog as? DistributionDialog.EditNode)?.initialPct ?: "0") }
    val parsedPct = pct.replace(',', '.').toDoubleOrNull()
    val percentageOverLimit = parsedPct != null && parsedPct > 100.0
    val title = when (dialog) { DistributionDialog.NewItem -> "New item"; is DistributionDialog.NewSubitem -> "New subitem"; is DistributionDialog.EditNode -> "Edit distribution item"; is DistributionDialog.Rename -> "Rename" }
    AlertDialog(onDismissRequest = close, title = { Text(title) }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (dialog is DistributionDialog.NewItem || dialog is DistributionDialog.NewSubitem || dialog is DistributionDialog.EditNode || dialog is DistributionDialog.Rename) OutlinedTextField(name, { name = it }, label = { Text("Name") }, singleLine = true)
            if (dialog is DistributionDialog.NewItem) OutlinedTextField(group, { group = it }, label = { Text("Group") }, singleLine = true)
            if (dialog is DistributionDialog.NewItem || dialog is DistributionDialog.NewSubitem || dialog is DistributionDialog.EditNode) {
                OutlinedTextField(
                    value = pct,
                    onValueChange = { pct = it },
                    label = { Text("Percent") },
                    singleLine = true,
                    isError = percentageOverLimit,
                    supportingText = if (percentageOverLimit) {
                        { Text("Percent cannot be greater than 100") }
                    } else null,
                )
            }
        }
    }, confirmButton = { Button(onClick = {
        when (dialog) {
            DistributionDialog.NewItem -> viewModel.addItem(name, group, parsedPct ?: 0.0)
            is DistributionDialog.NewSubitem -> viewModel.addSubitem(dialog.parentItemId, name, parsedPct ?: 0.0)
            is DistributionDialog.EditNode -> {
                if (dialog.subitem) {
                    viewModel.renameSubitem(dialog.id, name)
                    viewModel.updateSubitemPct(dialog.id, parsedPct ?: 0.0)
                } else {
                    viewModel.renameItem(dialog.id, name)
                    viewModel.updateItemPct(dialog.id, parsedPct ?: 0.0)
                }
            }
            is DistributionDialog.Rename -> if (dialog.subitem) viewModel.renameSubitem(dialog.id, name) else viewModel.renameItem(dialog.id, name)
        }; close()
    }, enabled = !percentageOverLimit) { Text("Save") } }, dismissButton = { TextButton(onClick = close) { Text("Cancel") } })
}
