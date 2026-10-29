package app.ledgera.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColors = lightColorScheme(
    primary = Color(0xFF285C52),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFB5E9DC),
    onPrimaryContainer = Color(0xFF002019),
    secondary = Color(0xFF9C6A2F),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFFFDDB5),
    onSecondaryContainer = Color(0xFF321A00),
    background = Color(0xFFF6F1E8),
    onBackground = Color(0xFF1D1B19),
    surface = Color(0xFFFFFBF4),
    onSurface = Color(0xFF1D1B19),
    surfaceVariant = Color(0xFFE5E2DA),
    onSurfaceVariant = Color(0xFF484640),
    outline = Color(0xFF797770),
    error = Color(0xFFB3261E),
    onError = Color.White,
    errorContainer = Color(0xFFFFDAD6),
    onErrorContainer = Color(0xFF410002),
    inverseSurface = Color(0xFF32302D),
    inverseOnSurface = Color(0xFFF5F0E8),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8DD8C8),
    onPrimary = Color(0xFF00382F),
    primaryContainer = Color(0xFF005047),
    onPrimaryContainer = Color(0xFFAAF2E2),
    secondary = Color(0xFFE8B776),
    onSecondary = Color(0xFF4F2B00),
    secondaryContainer = Color(0xFF704A15),
    onSecondaryContainer = Color(0xFFFFDDB5),
    background = Color(0xFF171A18),
    onBackground = Color(0xFFE6E2DB),
    surface = Color(0xFF202620),
    onSurface = Color(0xFFE6E2DB),
    surfaceVariant = Color(0xFF424844),
    onSurfaceVariant = Color(0xFFC1C8C2),
    outline = Color(0xFF8B938D),
    error = Color(0xFFFFB4AB),
    onError = Color(0xFF690005),
    errorContainer = Color(0xFF93000A),
    onErrorContainer = Color(0xFFFFDAD6),
    inverseSurface = Color(0xFFE6E2DB),
    inverseOnSurface = Color(0xFF30312D),
)

@Composable
fun LedgeraTheme(mode: ThemeMode = ThemeMode.SYSTEM, content: @Composable () -> Unit) {
    val dark = mode.resolveDark(isSystemInDarkTheme())
    MaterialTheme(
        colorScheme = if (dark) DarkColors else LightColors,
        content = content,
    )
}
