package app.ledgera.distribution

import androidx.compose.foundation.background
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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import app.ledgera.model.DistributionMonthlyResult

@Composable
fun DistributionScreen(viewModel: DistributionViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsState()
    var dialog by remember { mutableStateOf<DistributionDialog?>(null) }
    Column(modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
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
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val narrow = maxWidth < 860.dp
            if (narrow) {
                Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    StructurePane(state, viewModel, { dialog = it }, Modifier.weight(1f))
                    ResultsPane(state, viewModel, Modifier.weight(1f))
                }
            } else Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StructurePane(state, viewModel, { dialog = it }, Modifier.weight(0.34f).fillMaxHeight())
                ResultsPane(state, viewModel, Modifier.weight(0.66f).fillMaxHeight())
            }
        }
    }
    dialog?.let { DistributionDialogHost(it, state.items, viewModel) { dialog = null } }
}

private sealed class DistributionDialog {
    data object Item : DistributionDialog()
    data class Subitem(val itemId: Long) : DistributionDialog()
    data class EditPct(val id: Long, val subitem: Boolean, val initial: String) : DistributionDialog()
    data class Rename(val id: Long, val subitem: Boolean, val initial: String) : DistributionDialog()
}

@Composable
private fun StructurePane(state: DistributionUiState, viewModel: DistributionViewModel, openDialog: (DistributionDialog) -> Unit, modifier: Modifier) {
    Card(modifier) {
        Column(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Distribution structure", style = MaterialTheme.typography.titleLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Button(onClick = { openDialog(DistributionDialog.Item) }) { Text("+ Item") }
                Button(onClick = { state.selectedItemId?.let { openDialog(DistributionDialog.Subitem(it)) } }, enabled = state.selectedItemId != null) { Text("+ Subitem") }
            }
            val validation = state.validation
            Text(if (validation.isEmpty()) "Structure is valid" else validation.joinToString("\n") { it.message }, color = if (validation.isEmpty()) Color(0xFF18794E) else MaterialTheme.colorScheme.error)
            val groupedItems = state.items
                .groupBy { it.groupName.ifBlank { "Ungrouped" } }
                .toSortedMap()
                .values
                .flatten()
            LazyColumn(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                items(groupedItems, key = { "item-${it.id}" }) { item ->
                    val group = item.groupName.ifBlank { "Ungrouped" }
                    val firstInGroup = groupedItems.indexOfFirst { it.groupName.ifBlank { "Ungrouped" } == group } == groupedItems.indexOf(item)
                    if (firstInGroup) {
                        Text(group, Modifier.padding(top = 6.dp), color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
                    }
                    DistributionItemRow(item, state, viewModel, openDialog)
                }
            }
        }
    }
}

@Composable
private fun DistributionItemRow(item: DistributionItem, state: DistributionUiState, viewModel: DistributionViewModel, openDialog: (DistributionDialog) -> Unit) {
    val id = "item-${item.id}"
    val expanded = id in state.expandedIds
    Column {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(MaterialTheme.colorScheme.surfaceVariant).padding(horizontal = 6.dp, vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { viewModel.toggleExpanded(id) }) { Text(if (expanded) "▾" else "▸") }
            Text(item.name, Modifier.weight(1f))
            Text("${"%.2f".format(item.pct)}%")
            TextButton(onClick = { openDialog(DistributionDialog.EditPct(item.id, false, item.pct.toString())) }) { Text("%") }
            TextButton(onClick = { openDialog(DistributionDialog.Rename(item.id, false, item.name)) }) { Text("Edit") }
            TextButton(onClick = { viewModel.deleteItem(item.id) }) { Text("Delete") }
        }
        if (expanded) item.subitems.forEach { subitem ->
            Row(Modifier.fillMaxWidth().padding(start = 34.dp).clip(RoundedCornerShape(8.dp)).background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .55f)).padding(horizontal = 6.dp, vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(subitem.name, Modifier.weight(1f))
                Text("${"%.2f".format(subitem.pct)}%")
                TextButton(onClick = { openDialog(DistributionDialog.EditPct(subitem.id, true, subitem.pct.toString())) }) { Text("%") }
                TextButton(onClick = { openDialog(DistributionDialog.Rename(subitem.id, true, subitem.name)) }) { Text("Edit") }
                TextButton(onClick = { viewModel.deleteSubitem(subitem.id) }) { Text("Delete") }
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
            else Column(Modifier.fillMaxSize().horizontalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                months.forEach { month ->
                    val frozenRow = frozen[month]
                    val result = live[month]
                    val negative = frozenRow?.isNegative ?: result?.isNegative ?: false
                    val isAuto = frozenRow?.autoFixed == true
                    val rowColor = (if (negative) Color(0xFFE53935) else Color(0xFF2E8B70)).copy(alpha = .30f)
                    Row(Modifier.width(900.dp).clip(RoundedCornerShape(9.dp)).background(rowColor).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(month, Modifier.width(90.dp))
                        Text(if (isAuto) "Auto-fixed" else if (frozenRow != null) "Fixed" else "Live", Modifier.width(100.dp))
                        Text(frozenRow?.columns?.firstOrNull { it.key == "net_income" }?.value ?: result?.netIncomeBase ?: "-", Modifier.width(130.dp))
                        if (frozenRow != null) frozenRow.columns.drop(3).forEach { Text("${it.label}: ${it.value}", Modifier.width(130.dp)) }
                        else result?.items?.forEach { Text("${it.name}: ${it.amountBase}", Modifier.width(130.dp)) }
                        Spacer(Modifier.width(8.dp))
                        Button(onClick = { viewModel.selectMonth(month); viewModel.toggleFixed(month) }, enabled = !isAuto) { Text(if (frozenRow == null) "Fix" else "Unfix") }
                    }
                }
            }
        }
    }
}

@Composable
private fun DistributionDialogHost(dialog: DistributionDialog, items: List<DistributionItem>, viewModel: DistributionViewModel, close: () -> Unit) {
    var name by remember(dialog) { mutableStateOf((dialog as? DistributionDialog.Rename)?.initial ?: "") }
    var group by remember(dialog) { mutableStateOf("") }
    var pct by remember(dialog) { mutableStateOf((dialog as? DistributionDialog.EditPct)?.initial ?: "0") }
    val title = when (dialog) { DistributionDialog.Item -> "New item"; is DistributionDialog.Subitem -> "New subitem"; is DistributionDialog.EditPct -> "Edit percent"; is DistributionDialog.Rename -> "Rename" }
    AlertDialog(onDismissRequest = close, title = { Text(title) }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (dialog is DistributionDialog.Item || dialog is DistributionDialog.Subitem || dialog is DistributionDialog.Rename) OutlinedTextField(name, { name = it }, label = { Text("Name") }, singleLine = true)
            if (dialog is DistributionDialog.Item) OutlinedTextField(group, { group = it }, label = { Text("Group") }, singleLine = true)
            if (dialog is DistributionDialog.Item || dialog is DistributionDialog.Subitem || dialog is DistributionDialog.EditPct) OutlinedTextField(pct, { pct = it }, label = { Text("Percent") }, singleLine = true)
        }
    }, confirmButton = { Button(onClick = {
        when (dialog) {
            DistributionDialog.Item -> viewModel.addItem(name, group, pct.toDoubleOrNull() ?: 0.0)
            is DistributionDialog.Subitem -> viewModel.addSubitem(dialog.itemId, name, pct.toDoubleOrNull() ?: 0.0)
            is DistributionDialog.EditPct -> if (dialog.subitem) viewModel.updateSubitemPct(dialog.id, pct.toDoubleOrNull() ?: 0.0) else viewModel.updateItemPct(dialog.id, pct.toDoubleOrNull() ?: 0.0)
            is DistributionDialog.Rename -> if (dialog.subitem) viewModel.renameSubitem(dialog.id, name) else viewModel.renameItem(dialog.id, name)
        }; close()
    }) { Text("Save") } }, dismissButton = { TextButton(onClick = close) { Text("Cancel") } })
}
