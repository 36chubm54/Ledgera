package app.ledgera.validation

import kotlin.test.Test
import kotlin.test.assertEquals

class RateValidationTest {
    @Test
    fun acceptsPositiveRatesAfterSixDecimalPlaces() {
        assertEquals(null, RateValidation.validatePositiveRate("512.41"))
        assertEquals(null, RateValidation.validatePositiveRate("0.0000005"))
        assertEquals(null, RateValidation.validatePositiveRate("+.5"))
    }

    @Test
    fun rejectsMalformedAndRoundedZeroRates() {
        assertEquals("Rate must be a positive number", RateValidation.validatePositiveRate("-1"))
        assertEquals("Rate must be greater than zero", RateValidation.validatePositiveRate("0"))
        assertEquals("Rate must be greater than zero", RateValidation.validatePositiveRate("0.0000004"))
        assertEquals("Rate must be a positive number", RateValidation.validatePositiveRate("1" + "0".repeat(400)))
    }
}
