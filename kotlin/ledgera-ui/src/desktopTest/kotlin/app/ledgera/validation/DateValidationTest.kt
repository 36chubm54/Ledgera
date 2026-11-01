package app.ledgera.validation

import kotlin.test.Test
import kotlin.test.assertEquals

class DateValidationTest {
    @Test
    fun validateYmdNotFutureRejectsFutureDate() {
        val today = LedgerDate(year = 2026, month = 6, day = 6)

        assertEquals(
            "Date cannot be in the future",
            DateValidation.validateYmdNotFuture("2026-06-07", today),
        )
    }

    @Test
    fun validateYmdNotFutureRejectsInvalidCalendarDate() {
        val today = LedgerDate(year = 2026, month = 6, day = 6)

        assertEquals(
            "Date must use a valid YYYY-MM-DD value",
            DateValidation.validateYmdNotFuture("2026-02-30", today),
        )
    }

    @Test
    fun dateParsersRejectDatesBeforeUnixEpoch() {
        assertEquals(null, DateValidation.parseYmd("1969-12-31"))
        assertEquals(null, DateValidation.parseDmyStrict("31.12.1969"))
    }

    @Test
    fun validateYmdNotFutureAcceptsTodayAndPastDates() {
        val today = LedgerDate(year = 2026, month = 6, day = 6)

        assertEquals(null, DateValidation.validateYmdNotFuture("2026-06-06", today))
        assertEquals(null, DateValidation.validateYmdNotFuture("2026-06-05", today))
    }

    @Test
    fun parseDmyStrictAcceptsValidCalendarDates() {
        assertEquals(LedgerDate(year = 2026, month = 2, day = 1), DateValidation.parseDmyStrict("01.02.2026"))
        assertEquals(LedgerDate(year = 2024, month = 2, day = 29), DateValidation.parseDmyStrict("29.02.2024"))
    }

    @Test
    fun parseDmyStrictRejectsLooseOrInvalidValues() {
        assertEquals(null, DateValidation.parseDmyStrict("1.2.2026"))
        assertEquals(null, DateValidation.parseDmyStrict("2026-02-01"))
        assertEquals(null, DateValidation.parseDmyStrict("01/02/2026"))
        assertEquals(null, DateValidation.parseDmyStrict("30.02.2026"))
    }

    @Test
    fun dmyFormattingRoundTripsThroughStorageFormat() {
        assertEquals("01.02.2026", DateValidation.formatYmdToDmy("2026-02-01"))
        assertEquals("2026-02-01", DateValidation.formatDmyToYmd("01.02.2026"))
    }

    @Test
    fun validateDmyNotFutureRejectsFutureDatesOnlyWhenRequested() {
        val today = LedgerDate(year = 2026, month = 6, day = 6)

        assertEquals(
            "Date cannot be in the future",
            DateValidation.validateDmyNotFuture("07.06.2026", today),
        )
        assertEquals(null, DateValidation.validateOptionalDmy("07.06.2026"))
    }

    @Test
    fun validateDmyNotFutureUsesDmyErrorMessage() {
        val today = LedgerDate(year = 2026, month = 6, day = 6)

        assertEquals(
            "Date must use a valid DD.MM.YYYY value",
            DateValidation.validateDmyNotFuture("06/06/2026", today),
        )
        assertEquals(
            "Date must use a valid DD.MM.YYYY value",
            DateValidation.validateDmyNotFuture("2026-06-06", today),
        )
        assertEquals(
            "Date must use a valid DD.MM.YYYY value",
            DateValidation.validateOptionalDmy("2026-06-06"),
        )
    }
}
