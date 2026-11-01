package app.ledgera.validation

import kotlin.test.Test
import kotlin.test.assertEquals

class CurrencyValidationTest {
    @Test
    fun validateSupportedCurrencyRejectsMalformedCodes() {
        assertEquals(
            "Currency code must contain 3 letters",
            CurrencyValidation.validateSupportedCurrency("K1T"),
        )
        assertEquals(null, CurrencyValidation.validateSupportedCurrency("AAA"))
    }

    @Test
    fun validateSupportedCurrencyAcceptsSupportedCodes() {
        assertEquals(null, CurrencyValidation.validateSupportedCurrency("kzt"))
        assertEquals(null, CurrencyValidation.validateSupportedCurrency("USD"))
    }

    @Test
    fun normalizeCurrencyCodeDoesNotHideMalformedInput() {
        assertEquals("K1Z_T", CurrencyValidation.normalizeCurrencyCode("k1z_t"))
    }

    @Test
    fun optionalSupportedCurrencySetRejectsUnknownCode() {
        assertEquals(
            "Unsupported currency",
            CurrencyValidation.validateSupportedCurrency("EUR", listOf("KZT", "USD")),
        )
        assertEquals(
            null,
            CurrencyValidation.validateSupportedCurrency("usd", listOf("KZT", "USD")),
        )
    }
}
