package app.ledgera.ui

import androidx.compose.ui.graphics.Color

internal fun String.toComposeTagColor(): Color? {
    val value = removePrefix("#")
    if (value.length != 6) return null
    return Color(
        red = value.substring(0, 2).toIntOrNull(16)?.div(255f) ?: return null,
        green = value.substring(2, 4).toIntOrNull(16)?.div(255f) ?: return null,
        blue = value.substring(4, 6).toIntOrNull(16)?.div(255f) ?: return null,
    )
}
