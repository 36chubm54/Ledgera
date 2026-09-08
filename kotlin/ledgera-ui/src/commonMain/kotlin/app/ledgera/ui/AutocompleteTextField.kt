package app.ledgera.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.clickable
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.PopupProperties

@Composable
fun AutocompleteTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    suggestions: List<String>,
    modifier: Modifier = Modifier,
    menuWidth: Dp? = null,
    maxSuggestions: Int = 6,
    showSuggestionsOnBlank: Boolean = true,
) {
    var expanded by remember { mutableStateOf(false) }
    val filteredSuggestions = remember(value, suggestions, showSuggestionsOnBlank) {
        autocompleteSuggestions(value, suggestions, maxSuggestions, showSuggestionsOnBlank)
    }
    Box(modifier = modifier) {
        OutlinedTextField(
            modifier = Modifier
                .fillMaxWidth()
                .onFocusChanged { state ->
                    expanded = state.isFocused && filteredSuggestions.isNotEmpty()
                }
                .onPreviewKeyEvent { event ->
                    if (event.type != KeyEventType.KeyDown) {
                        false
                    } else {
                        when (event.key) {
                            Key.Escape -> {
                                expanded = false
                                true
                            }
                            else -> false
                        }
                    }
                },
            value = value,
            onValueChange = {
                onValueChange(it.lineSafe())
                expanded = true
            },
            label = { Text(label) },
            singleLine = true,
        )
        SuggestionMenu(
            expanded = expanded && filteredSuggestions.isNotEmpty(),
            suggestions = filteredSuggestions,
            menuWidth = menuWidth,
            onDismiss = { expanded = false },
            onSuggestionSelected = { suggestion ->
                onValueChange(suggestion)
                expanded = false
            },
        )
    }
}

@Composable
fun TagAutocompleteField(
    value: String,
    onValueChange: (String) -> Unit,
    suggestions: List<String>,
    modifier: Modifier = Modifier,
    menuWidth: Dp? = null,
    maxSuggestions: Int = 6,
    tagColors: Map<String, String> = emptyMap(),
    palette: List<String> = emptyList(),
    onTagColorChanged: (String, String) -> Unit = { _, _ -> },
) {
    var expanded by remember { mutableStateOf(false) }
    val token = currentTagToken(value)
    val filteredSuggestions = remember(token, suggestions) {
        autocompleteSuggestions(token, suggestions, maxSuggestions, showSuggestionsOnBlank = true)
    }
    var showColorPicker by remember { mutableStateOf(false) }
    val currentTag = token.normalizedTagForColor()
    val currentColor = tagColors[currentTag]
        ?: palette.firstOrNull { color -> color !in tagColors.values && color.isNotEmpty() }
        ?: ""
    Box(modifier = modifier) {
        OutlinedTextField(
            modifier = Modifier
                .fillMaxWidth()
                .onFocusChanged { state ->
                    expanded = state.isFocused && filteredSuggestions.isNotEmpty()
                }
                .onPreviewKeyEvent { event ->
                    if (event.type != KeyEventType.KeyDown) {
                        false
                    } else {
                        when (event.key) {
                            Key.Escape -> {
                                expanded = false
                                true
                            }
                            else -> false
                        }
                    }
                },
            value = value,
            onValueChange = {
                onValueChange(it.lineSafe())
                expanded = true
            },
            label = { Text("Tags, comma-separated") },
            singleLine = true,
            trailingIcon = { Box(Modifier.size(40.dp)) },
        )
        Button(
            modifier = Modifier
                .align(androidx.compose.ui.Alignment.CenterEnd)
                .padding(end = 8.dp)
                .size(32.dp),
            onClick = { showColorPicker = true },
            enabled = currentTag.isNotEmpty() && palette.isNotEmpty(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
            shape = CircleShape,
        ) {
            Box(
                Modifier
                    .size(22.dp)
                    .background(currentColor.toComposeTagColor() ?: Color.Transparent, CircleShape)
                    .border(1.dp, MaterialTheme.colorScheme.outline, CircleShape),
            )
        }
        SuggestionMenu(
            expanded = expanded && filteredSuggestions.isNotEmpty(),
            suggestions = filteredSuggestions,
            menuWidth = menuWidth,
            onDismiss = { expanded = false },
            onSuggestionSelected = { suggestion ->
                onValueChange(replaceCurrentTagTokenForAutocomplete(value, suggestion))
                expanded = false
            },
        )
    }
    if (showColorPicker) {
        TagColorPickerDialog(
            currentColor = currentColor,
            palette = palette,
            usedColors = tagColors
                .filterKeys { it != currentTag }
                .values
                .filter(String::isNotEmpty)
                .toSet(),
            onColorSelected = { color ->
                onTagColorChanged(currentTag, color)
                showColorPicker = false
            },
            onDismiss = { showColorPicker = false },
        )
    }
}

@Composable
private fun TagColorPickerDialog(
    currentColor: String,
    palette: List<String>,
    usedColors: Set<String>,
    onColorSelected: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Tag color") },
        text = {
            LazyVerticalGrid(
                columns = GridCells.Fixed(3),
                modifier = Modifier.heightIn(max = 360.dp).fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(18.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                items(palette + "") { color ->
                    val occupied = color.isNotEmpty() && color in usedColors
                    Box(
                        modifier = Modifier
                            .size(58.dp)
                            .background(
                                if (color.isEmpty()) MaterialTheme.colorScheme.surfaceVariant
                                else color.toComposeTagColor() ?: MaterialTheme.colorScheme.surfaceVariant,
                                CircleShape,
                            )
                            .border(
                                width = if (color == currentColor) 3.dp else 1.dp,
                                color = if (color == currentColor) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                                shape = CircleShape,
                            )
                            .clickable(enabled = !occupied, onClick = { onColorSelected(color) }),
                        contentAlignment = androidx.compose.ui.Alignment.Center,
                    ) {
                        if (color.isEmpty()) {
                            Text("×", style = MaterialTheme.typography.headlineMedium)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun SuggestionMenu(
    expanded: Boolean,
    suggestions: List<String>,
    menuWidth: Dp?,
    onDismiss: () -> Unit,
    onSuggestionSelected: (String) -> Unit,
) {
    DropdownMenu(
        expanded = expanded,
        onDismissRequest = onDismiss,
        modifier = if (menuWidth == null) Modifier else Modifier.width(menuWidth),
        properties = PopupProperties(focusable = false),
    ) {
        suggestions.forEach { suggestion ->
            DropdownMenuItem(
                text = { Text(suggestion) },
                onClick = { onSuggestionSelected(suggestion) },
            )
        }
    }
}

internal fun autocompleteSuggestions(
    value: String,
    suggestions: List<String>,
    maxSuggestions: Int,
    showSuggestionsOnBlank: Boolean,
): List<String> {
    val query = value.trim()
    if (query.isEmpty() && !showSuggestionsOnBlank) {
        return emptyList()
    }
    return suggestions
        .asSequence()
        .map(String::trim)
        .filter(String::isNotEmpty)
        .distinctBy(String::lowercase)
        .filter { suggestion ->
            (query.isEmpty() || suggestion.contains(query, ignoreCase = true)) &&
                !suggestion.equals(query, ignoreCase = true)
        }
        .take(maxSuggestions.coerceAtLeast(1))
        .toList()
}

private fun currentTagToken(value: String): String =
    value.substringAfterLast(',').trim()

private fun String.normalizedTagForColor(): String =
    trim().removePrefix("#").lowercase()

internal fun replaceCurrentTagTokenForAutocomplete(value: String, suggestion: String): String {
    val separatorIndex = value.lastIndexOf(',')
    return if (separatorIndex < 0) {
        suggestion
    } else {
        "${value.substring(0, separatorIndex).trimEnd()}, $suggestion"
    }
}

private fun String.lineSafe(): String = replace("\r", " ").replace("\n", " ")
