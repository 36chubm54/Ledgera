package app.ledgera.validation

object CurrencyValidation {
    fun validateSupportedCurrency(value: String, supportedCurrencies: Collection<String>? = null): String? =
        when {
            !isValidCurrencyCode(value) -> "Currency code must contain 3 letters"
            supportedCurrencies != null && normalizeCurrencyCode(value) !in supportedCurrencies.map { normalizeCurrencyCode(it) } ->
                "Unsupported currency"
            else -> null
        }

    fun normalizeCurrencyCode(value: String): String =
        value.trim().uppercase()

    fun isValidCurrencyCode(value: String): Boolean =
        Regex("[A-Za-z]{3}").matches(value.trim())

    fun isSupportedCurrency(value: String, supportedCurrencies: Collection<String>? = null): Boolean =
        validateSupportedCurrency(value, supportedCurrencies) == null
}
