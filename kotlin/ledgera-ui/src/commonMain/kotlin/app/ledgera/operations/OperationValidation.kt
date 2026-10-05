package app.ledgera.operations

import app.ledgera.validation.CurrencyValidation
import app.ledgera.validation.DateValidation
import app.ledgera.validation.MoneyValidation
import app.ledgera.validation.TagValidation

internal object OperationValidation {
    fun validateFields(
        type: String,
        date: String,
        walletId: Long,
        amountOriginal: String,
        currency: String,
        category: String,
        tagsText: String,
        baseCurrency: String? = null,
    ): String? {
        val normalizedType = type.trim().lowercase()
        val dateError = if (date.isBlank()) null else DateValidation.validateDmyNotFuture(date)
        val amountError = if (amountOriginal.isBlank()) null else MoneyValidation.validatePositiveAmount(amountOriginal)
        val currencyError = CurrencyValidation.validateSupportedCurrency(currency)
        val baseCurrencyError = validateBaseCurrencyOnly(currency, baseCurrency)
        val tagError = TagValidation.validateTagText(tagsText)
        return when {
            normalizedType != "income" && normalizedType != "expense" -> "Only income and expense are supported"
            date.isBlank() -> "Date is required"
            dateError != null -> dateError
            walletId <= 0 -> "Wallet is required"
            amountOriginal.isBlank() -> "Amount is required"
            amountError != null -> amountError
            currencyError != null -> currencyError
            baseCurrencyError != null -> baseCurrencyError
            category.isBlank() -> "Category is required"
            tagError != null -> tagError
            else -> null
        }
    }

    fun normalizeCurrency(value: String): String =
        CurrencyValidation.normalizeCurrencyCode(value)

    fun parseTags(value: String): List<String> =
        TagValidation.parseTagText(value)

    fun validateTransferFields(
        fromWalletId: Long,
        toWalletId: Long,
        date: String,
        amount: String,
        currency: String,
        commissionAmount: String,
        commissionCurrency: String,
        baseCurrency: String,
    ): String? {
        val normalizedCommission = commissionAmount.ifBlank { "0" }
        val normalizedCommissionCurrency = commissionCurrency.ifBlank { baseCurrency }
        val dateError = if (date.isBlank()) null else DateValidation.validateDmyNotFuture(date)
        val amountError = if (amount.isBlank()) null else MoneyValidation.validatePositiveAmount(amount)
        val commissionError = MoneyValidation.validateNonNegativeAmount(normalizedCommission)
        val currencyError = CurrencyValidation.validateSupportedCurrency(currency)
        val commissionCurrencyError =
            CurrencyValidation.validateSupportedCurrency(normalizedCommissionCurrency)
        val baseCurrencyError = validateTransferBaseCurrencyOnly(currency, baseCurrency)
        val commissionBaseCurrencyError =
            validateTransferBaseCurrencyOnly(normalizedCommissionCurrency, baseCurrency)
        return when {
            fromWalletId <= 0 -> "Source wallet is required"
            toWalletId <= 0 -> "Target wallet is required"
            fromWalletId == toWalletId -> "Transfer wallets must be different"
            date.isBlank() -> "Date is required"
            dateError != null -> dateError
            amount.isBlank() -> "Amount is required"
            amountError != null -> amountError
            currencyError != null -> currencyError
            baseCurrencyError != null -> baseCurrencyError
            commissionError != null -> commissionError
            commissionCurrencyError != null -> commissionCurrencyError
            commissionBaseCurrencyError != null -> commissionBaseCurrencyError
            else -> null
        }
    }

    private fun validateBaseCurrencyOnly(currency: String, baseCurrency: String?): String? {
        val normalizedBase = baseCurrency?.trim()?.uppercase()?.takeIf { it.isNotEmpty() } ?: return null
        val normalizedCurrency = currency.trim().uppercase()
        return null
    }

    private fun validateTransferBaseCurrencyOnly(currency: String, baseCurrency: String): String? {
        val normalizedBase = baseCurrency.trim().uppercase().ifEmpty { "KZT" }
        val normalizedCurrency = currency.trim().uppercase()
        return if (normalizedCurrency == normalizedBase) {
            null
        } else {
            "Transfer flow currently supports base-currency transfers only ($normalizedBase)"
        }
    }
}
