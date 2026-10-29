package app.ledgera.theme

import java.util.UUID
import java.util.prefs.Preferences
import kotlin.test.Test
import kotlin.test.assertEquals

class ThemeModeTest {
    @Test
    fun unknownPersistedValueFallsBackToSystem() {
        assertEquals(ThemeMode.SYSTEM, ThemeMode.fromPersisted("unsupported"))
        assertEquals(ThemeMode.SYSTEM, ThemeMode.fromPersisted(null))
    }

    @Test
    fun systemModeFollowsPlatformWhileExplicitModesWin() {
        assertEquals(true, ThemeMode.SYSTEM.resolveDark(systemIsDark = true))
        assertEquals(false, ThemeMode.SYSTEM.resolveDark(systemIsDark = false))
        assertEquals(false, ThemeMode.LIGHT.resolveDark(systemIsDark = true))
        assertEquals(true, ThemeMode.DARK.resolveDark(systemIsDark = false))
    }

    @Test
    fun preferenceRoundTripKeepsSelectedMode() {
        val node = Preferences.userRoot().node("ledgera-theme-test-${UUID.randomUUID()}")
        try {
            DesktopThemePreferences.save(ThemeMode.DARK, node)
            assertEquals(ThemeMode.DARK, DesktopThemePreferences.load(node))

            DesktopThemePreferences.save(ThemeMode.LIGHT, node)
            assertEquals(ThemeMode.LIGHT, DesktopThemePreferences.load(node))
        } finally {
            node.removeNode()
        }
    }
}
