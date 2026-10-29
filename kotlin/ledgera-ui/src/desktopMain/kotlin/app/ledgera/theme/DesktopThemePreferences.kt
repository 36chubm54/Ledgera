package app.ledgera.theme

import java.util.prefs.Preferences

object DesktopThemePreferences {
    private const val THEME_KEY = "theme_mode"
    private val preferences: Preferences by lazy {
        Preferences.userNodeForPackage(DesktopThemePreferences::class.java)
    }

    fun load(): ThemeMode = load(preferences)

    fun save(mode: ThemeMode) {
        save(mode, preferences)
    }

    internal fun load(store: Preferences): ThemeMode =
        ThemeMode.fromPersisted(runCatching { store.get(THEME_KEY, null) }.getOrNull())

    internal fun save(mode: ThemeMode, store: Preferences) {
        runCatching { store.put(THEME_KEY, mode.persistedValue) }
    }
}
