package app.ledgera.mandatory

import app.ledgera.model.MandatoryAddToRecordsDraft
import app.ledgera.model.MandatoryTemplateDraft
import app.ledgera.validation.CurrencyValidation
import app.ledgera.validation.DateValidation
import app.ledgera.validation.MoneyValidation

object MandatoryValidation {
    private val periods = setOf("daily", "weekly", "monthly", "yearly")

    fun validateCreateDraft(draft: MandatoryTemplateDraft, baseCurrency: String): String? {
        if (draft.walletId <= 0) return "Wallet is required"
        if (draft.category.trim().isEmpty()) return "Category is required"
        if (draft.description.trim().isEmpty()) return "Description is required"
        MoneyValidation.validatePositiveAmount(draft.amountOriginal.trim())?.let { return it }
        CurrencyValidation.validateSupportedCurrency(draft.currency.trim())?.let { return it }
        if (draft.amountBase.trim().isEmpty() && !draft.currency.trim().equals(baseCurrency.trim(), ignoreCase = true)) {
            return "Currency rate is unavailable for the selected currency and date"
        }
        MoneyValidation.validatePositiveAmount(draft.amountBase.trim())?.let { return it }
        validatePeriod(draft.period)?.let { return it }
        validateOptionalDate(draft.date)?.let { return it }
        return null
    }

    fun validateUpdateDraft(draft: MandatoryTemplateDraft): String? {
        if (draft.walletId <= 0) return "Wallet is required"
        MoneyValidation.validatePositiveAmount(draft.amountBase.trim())?.let { return it }
        validatePeriod(draft.period)?.let { return it }
        validateOptionalDate(draft.date)?.let { return it }
        return null
    }

    fun validateAddToRecordsDraft(draft: MandatoryAddToRecordsDraft): String? {
        if (draft.templateId <= 0) return "Mandatory template is required"
        if (draft.walletId <= 0) return "Wallet is required"
        if (draft.date.trim().isEmpty()) return "Date is required"
        DateValidation.validateDmyNotFuture(draft.date.trim())?.let { return it }
        return null
    }

    fun normalizeCurrency(value: String): String =
        CurrencyValidation.normalizeCurrencyCode(value)

    private fun validatePeriod(value: String): String? =
        if (value.trim().lowercase() in periods) null else "Invalid mandatory period"

    private fun validateOptionalDate(value: String): String? {
        val normalized = value.trim()
        if (normalized.isEmpty()) return null
        return if (DateValidation.validateOptionalDmy(normalized) != null) {
            "Date must use a valid DD.MM.YYYY value"
        } else {
            null
        }
    }
}
