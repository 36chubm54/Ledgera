package app.ledgera.validation

import kotlin.test.Test
import kotlin.test.assertEquals

class MoneyValidationTest {
    @Test
    fun validatePositiveAmountRejectsInvalidAndRoundedZeroValues() {
        assertEquals("Amount must be a positive number", MoneyValidation.validatePositiveAmount("ten"))
        assertEquals("Amount must be a positive number", MoneyValidation.validatePositiveAmount("-1"))
        assertEquals("Amount must be a positive number", MoneyValidation.validatePositiveAmount("0.004"))
    }

    @Test
    fun validatePositiveAmountAllowsValuesThatRoundToPositiveMoney() {
        assertEquals(null, MoneyValidation.validatePositiveAmount("0.005"))
        assertEquals(null, MoneyValidation.validatePositiveAmount(".005"))
        assertEquals(null, MoneyValidation.validatePositiveAmount("+.005"))
        assertEquals(null, MoneyValidation.validatePositiveAmount("1."))
        assertEquals(null, MoneyValidation.validatePositiveAmount("10.005"))
    }

    @Test
    fun validateNonNegativeAmountAllowsZeroAndPositiveValues() {
        assertEquals(null, MoneyValidation.validateNonNegativeAmount("0"))
        assertEquals(null, MoneyValidation.validateNonNegativeAmount("0.004"))
        assertEquals(null, MoneyValidation.validateNonNegativeAmount("+1.25"))
    }

    @Test
    fun validateNonNegativeAmountRejectsInvalidAndNegativeValues() {
        assertEquals("Amount must be zero or a positive number", MoneyValidation.validateNonNegativeAmount("ten"))
        assertEquals("Amount must be zero or a positive number", MoneyValidation.validateNonNegativeAmount("-0.01"))
    }

    @Test
    fun amountValidatorRejectsValuesThatDoNotFitMinorUnits() {
        assertEquals(
            "Amount must be a positive number",
            MoneyValidation.validatePositiveAmount("92233720368547758.08"),
        )
        assertEquals(
            "Amount must be zero or a positive number",
            MoneyValidation.validateNonNegativeAmount("92233720368547758.08"),
        )
    }
}
