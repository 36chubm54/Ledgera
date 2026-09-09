package app.ledgera.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import app.ledgera.resources.Res
import app.ledgera.resources.ic_calendar
import app.ledgera.validation.DateValidation
import app.ledgera.validation.LedgerDate
import app.ledgera.validation.currentLedgerDate
import org.jetbrains.compose.resources.painterResource

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LedgerDateField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier.fillMaxWidth(),
    required: Boolean = true,
    allowFuture: Boolean = false,
    enabled: Boolean = true,
    externalError: String? = null,
) {
    var text by remember { mutableStateOf(displayDate(value)) }
    var pickerOpen by remember { mutableStateOf(false) }
    val today = currentLedgerDate()
    val error = externalError ?: validateDisplayDate(text, required, allowFuture, today)

    LaunchedEffect(value) {
        val nextText = displayDate(value)
        if (
            nextText != text &&
            (
                value.isBlank() ||
                    DateValidation.parseYmd(value.trim()) != null ||
                    DateValidation.parseDmyStrict(value.trim()) != null
                )
        ) {
            text = nextText
        }
    }

    OutlinedTextField(
        modifier = modifier,
        value = text,
        onValueChange = { raw ->
            val nextText = DateValidation.sanitizeDmyInput(raw)
            text = nextText
            onValueChange(nextText)
        },
        label = { Text(label) },
        singleLine = true,
        enabled = enabled,
        isError = error != null,
        supportingText = {
            if (error != null) {
                Text(error)
            }
        },
        trailingIcon = {
            IconButton(onClick = { pickerOpen = true }, enabled = enabled) {
                Icon(
                    painter = painterResource(Res.drawable.ic_calendar),
                    contentDescription = "Select date",
                )
            }
        },
    )

    if (pickerOpen) {
        val selectedDate = DateValidation.parseGuiDate(text) ?: today
        val pickerState = rememberDatePickerState(
            initialSelectedDateMillis = DateValidation.toEpochMillisUtc(selectedDate),
            selectableDates = object : SelectableDates {
                override fun isSelectableDate(utcTimeMillis: Long): Boolean {
                    return allowFuture || DateValidation.fromEpochMillisUtc(utcTimeMillis) <= today
                }
            },
        )
        DatePickerDialog(
            onDismissRequest = { pickerOpen = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        val picked = pickerState.selectedDateMillis
                            ?.let(DateValidation::fromEpochMillisUtc)
                            ?: selectedDate
                        text = DateValidation.formatDmy(picked)
                        onValueChange(DateValidation.formatDmy(picked))
                        pickerOpen = false
                    },
                ) {
                    Text("OK")
                }
            },
            dismissButton = {
                TextButton(onClick = { pickerOpen = false }) {
                    Text("Cancel")
                }
            },
        ) {
            DatePicker(state = pickerState)
        }
    }
}

private fun displayDate(value: String): String {
    val normalized = value.trim()
    return DateValidation.formatYmdToDmy(normalized).ifBlank { normalized }
}

private fun validateDisplayDate(
    value: String,
    required: Boolean,
    allowFuture: Boolean,
    today: LedgerDate,
): String? {
    val normalized = value.trim()
    if (normalized.isEmpty()) {
        return if (required) "Date is required" else null
    }
    val parsed = DateValidation.parseDmyStrict(normalized)
        ?: return "Date must use a valid DD.MM.YYYY value"
    return if (!allowFuture && parsed > today) "Date cannot be in the future" else null
}
