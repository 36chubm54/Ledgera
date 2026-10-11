package app.ledgera.ui

import kotlin.test.Test
import kotlin.test.assertEquals

class AutocompleteTextFieldTest {
    @Test
    fun autocompleteCanHideSuggestionsForBlankDescriptionInput() {
        val suggestions = listOf("Lunch", "Salary")

        assertEquals(
            emptyList(),
            autocompleteSuggestions(
                value = "",
                suggestions = suggestions,
                maxSuggestions = 6,
                showSuggestionsOnBlank = false,
            ),
        )
        assertEquals(
            listOf("Lunch"),
            autocompleteSuggestions(
                value = "lun",
                suggestions = suggestions,
                maxSuggestions = 6,
                showSuggestionsOnBlank = false,
            ),
        )
    }

    @Test
    fun filtersCaseInsensitivelyAndRemovesDuplicateLabels() {
        assertEquals(
            listOf("Food", "Food delivery"),
            autocompleteSuggestions(
                value = "food",
                suggestions = listOf("Food", "food", "Food delivery", "Transport"),
                maxSuggestions = 6,
                showSuggestionsOnBlank = true,
            ),
        )
    }

    @Test
    fun autocompleteTrimsDeduplicatesAndCapsSuggestions() {
        assertEquals(
            listOf("Food", "Fuel"),
            autocompleteSuggestions(
                value = "f",
                suggestions = listOf(" Food ", "food", "", "Fuel", "Fees"),
                maxSuggestions = 2,
                showSuggestionsOnBlank = true,
            ),
        )
    }

    @Test
    fun excludesExactMatchAndRespectsLimit() {
        assertEquals(
            listOf("Food delivery", "Food market"),
            autocompleteSuggestions(
                value = "Food",
                suggestions = listOf("Food", "Food delivery", "Food market", "Food court"),
                maxSuggestions = 2,
                showSuggestionsOnBlank = true,
            ),
        )
    }

    @Test
    fun blankInputCanDisableSuggestions() {
        assertEquals(
            emptyList(),
            autocompleteSuggestions(
                value = "   ",
                suggestions = listOf("Food"),
                maxSuggestions = 6,
                showSuggestionsOnBlank = false,
            ),
        )
    }

    @Test
    fun tagAutocompleteReplacesOnlyCurrentToken() {
        assertEquals("home, grocery", replaceCurrentTagTokenForAutocomplete("home, gro", "grocery"))
        assertEquals("grocery", replaceCurrentTagTokenForAutocomplete("gro", "grocery"))
    }
}
