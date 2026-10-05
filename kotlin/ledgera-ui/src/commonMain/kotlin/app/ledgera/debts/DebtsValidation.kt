package app.ledgera.debts

import app.ledgera.model.DebtDraft
import app.ledgera.model.DebtActionDraft
import app.ledgera.validation.CurrencyValidation
import app.ledgera.validation.DateValidation
import app.ledgera.validation.MoneyValidation

object DebtsValidation {
    fun validateCreateDraft(draft: DebtDraft, baseCurrency: String): String? {
        val kind = draft.kind.trim().lowercase()
        if (kind != "debt" && kind != "loan") {
            return "Debt kind must be debt or loan"
        }
        if (draft.contactName.trim().isEmpty()) {
            return "Contact name is required"
        }
        if (draft.walletId <= 0) {
            return "Wallet is required"
        }
        DateValidation.validateDmyNotFuture(draft.createdAt.trim())?.let { return it }
        MoneyValidation.validatePositiveAmount(draft.amount.trim())?.let { return it }
        CurrencyValidation.validateSupportedCurrency(draft.currency.trim())?.let { return it }
        return null
    }

    fun validateActionDraft(draft: DebtActionDraft, requireWallet: Boolean): String? {
        val action = draft.action.trim().lowercase()
        if (action != "payment" && action != "write_off" && action != "close") {
            return "Debt action must be payment, write_off, or close"
        }
        if (draft.debtId <= 0) {
            return "Debt is required"
        }
        if (requireWallet && draft.walletId <= 0) {
            return "Wallet is required"
        }
        DateValidation.validateDmyNotFuture(draft.paymentDate.trim())?.let { return it }
        MoneyValidation.validatePositiveAmount(draft.amount.trim())?.let { return it }
        return null
    }
}
