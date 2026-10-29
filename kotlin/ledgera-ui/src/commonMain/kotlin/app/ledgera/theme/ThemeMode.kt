package app.ledgera.theme

enum class ThemeMode(val persistedValue: String, val label: String) {
    SYSTEM("system", "System"),
    LIGHT("light", "Light"),
    DARK("dark", "Dark");

    companion object {
        fun fromPersisted(value: String?): ThemeMode =
            entries.firstOrNull { it.persistedValue.equals(value?.trim(), ignoreCase = true) } ?: SYSTEM
    }
}

internal fun ThemeMode.resolveDark(systemIsDark: Boolean): Boolean = when (this) {
    ThemeMode.SYSTEM -> systemIsDark
    ThemeMode.LIGHT -> false
    ThemeMode.DARK -> true
}
