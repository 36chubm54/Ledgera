package app.ledgera.settings

import app.ledgera.validation.CurrencyValidation
import app.ledgera.validation.MoneyValidation

internal object SettingsValidation {
    fun validateWalletFields(
        name: String,
        currency: String,
        initialBalance: String,
        baseCurrency: String,
    ): String? {
        val balance = initialBalance.ifBlank { "0" }
        val currencyError = CurrencyValidation.validateSupportedCurrency(currency)
        val balanceError = MoneyValidation.validateNonNegativeAmount(balance)
        val normalizedBase = baseCurrency.trim().uppercase().ifEmpty { "KZT" }
        val normalizedCurrency = currency.trim().uppercase()
        return when {
            name.isBlank() -> "Wallet name is required"
            currencyError != null -> currencyError
            balanceError != null -> "Initial balance must be zero or a positive number"
            else -> null
        }
    }
}
