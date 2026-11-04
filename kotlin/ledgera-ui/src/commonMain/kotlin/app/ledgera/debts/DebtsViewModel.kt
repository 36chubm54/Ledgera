package app.ledgera.debts

import app.ledgera.bridge.DebtsEngine
import app.ledgera.model.CreateDebtRequest
import app.ledgera.model.DebtActionDraft
import app.ledgera.model.DebtDraft
import app.ledgera.model.DebtItem
import app.ledgera.model.DebtPaymentItem
import app.ledgera.model.RegisterDebtPaymentRequest
import app.ledgera.model.WalletOption
import app.ledgera.validation.DateValidation
import app.ledgera.validation.currentLedgerDate
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class DebtsUiState(
    val loading: Boolean = false,
    val debts: List<DebtItem> = emptyList(),
    val selectedDebtId: Long? = null,
    val selectedHistory: List<DebtPaymentItem> = emptyList(),
    val wallets: List<WalletOption> = emptyList(),
    val baseCurrency: String = "KZT",
    val createDraft: DebtDraft? = null,
    val createInProgress: Boolean = false,
    val actionDraft: DebtActionDraft? = null,
    val actionInProgress: Boolean = false,
    val deleteDebtId: Long? = null,
    val deletePayment: DebtPaymentItem? = null,
    val deleteLinkedRecord: Boolean = false,
    val deleteInProgress: Boolean = false,
    val error: String? = null,
    val notice: String? = null,
)

class DebtsViewModel(
    private val engine: DebtsEngine,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main),
) {
    private val mutableState = MutableStateFlow(DebtsUiState(loading = true))
    val state: StateFlow<DebtsUiState> = mutableState.asStateFlow()

    fun refresh() {
        refresh(notice = null)
    }

    private fun refresh(notice: String?) {
        val previous = mutableState.value
        mutableState.value = previous.copy(loading = true, error = null, notice = notice)
        launchSafely {
            runCatching {
                val baseCurrency = engine.baseCurrency()
                val wallets = engine.listWallets()
                val debts = engine.listDebts()
                val selectedDebtId = previous.selectedDebtId?.takeIf { selectedId ->
                    debts.any { it.id == selectedId }
                } ?: debts.firstOrNull()?.id
                val history = selectedDebtId?.let { engine.listDebtPayments(it) }.orEmpty()
                mutableState.value = DebtsUiState(
                    loading = false,
                    debts = debts,
                    selectedDebtId = selectedDebtId,
                    selectedHistory = history,
                    wallets = wallets,
                    baseCurrency = baseCurrency,
                    createDraft = previous.createDraft,
                    actionDraft = previous.actionDraft,
                    actionInProgress = previous.actionInProgress,
                    deleteDebtId = previous.deleteDebtId?.takeIf { deleteId ->
                        debts.any { it.id == deleteId }
                    },
                    deletePayment = previous.deletePayment?.takeIf { payment ->
                        history.any { it.id == payment.id }
                    },
                    deleteLinkedRecord = previous.deleteLinkedRecord,
                    deleteInProgress = previous.deleteInProgress,
                    notice = notice,
                )
            }.onFailure { error ->
                mutableState.value = previous.copy(
                    loading = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun selectDebt(debtId: Long) {
        val debt = mutableState.value.debts.firstOrNull { it.id == debtId }
        if (debt == null) {
            mutableState.value = mutableState.value.copy(error = "Debt not found", notice = null)
            return
        }
        mutableState.value = mutableState.value.copy(
            selectedDebtId = debtId,
            selectedHistory = emptyList(),
            loading = true,
            error = null,
            notice = null,
        )
        launchSafely {
            runCatching {
                val history = engine.listDebtPayments(debtId)
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    selectedDebtId = debtId,
                    selectedHistory = history,
                )
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    loading = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun openCreateDialog(kind: String) {
        val state = mutableState.value
        mutableState.value = state.copy(
            createDraft = DebtDraft(
                kind = kind,
                walletId = state.wallets.firstOrNull()?.id ?: 0,
                currency = state.baseCurrency,
                createdAt = todayDisplayText(),
            ),
            error = null,
            notice = null,
        )
    }

    fun closeCreateDialog() {
        mutableState.value = mutableState.value.copy(createDraft = null, createInProgress = false, error = null)
    }

    fun updateDraft(draft: DebtDraft) {
        mutableState.value = mutableState.value.copy(createDraft = draft, error = null, notice = null)
    }

    fun createDebt() {
        val draft = mutableState.value.createDraft ?: return
        DebtsValidation.validateCreateDraft(draft, mutableState.value.baseCurrency)?.let { validationError ->
            mutableState.value = mutableState.value.copy(error = validationError, notice = null)
            return
        }
        mutableState.value = mutableState.value.copy(createInProgress = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val created = engine.createDebt(
                    CreateDebtRequest(
                        kind = draft.kind.trim().lowercase(),
                        contactName = draft.contactName.trim(),
                        walletId = draft.walletId,
                        amount = draft.amount.trim(),
                        currency = draft.currency.trim().uppercase(),
                        createdAt = draft.createdAt.toStorageDate(),
                        note = draft.note.trim(),
                    )
                )
                mutableState.value = mutableState.value.copy(
                    createDraft = null,
                    createInProgress = false,
                    selectedDebtId = created.id,
                )
                refresh(
                    notice = if (created.kind == "loan") {
                        "Loan created (id=${created.id})"
                    } else {
                        "Debt created (id=${created.id})"
                    }
                )
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    createInProgress = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun openDebtAction(action: String) {
        val state = mutableState.value
        val debt = selectedDebt(state)
        if (debt == null) {
            mutableState.value = state.copy(error = "Select a debt or loan first", notice = null)
            return
        }
        if (debt.status == "closed") {
            mutableState.value = state.copy(error = "Debt is already closed", notice = null)
            return
        }
        mutableState.value = state.copy(
            actionDraft = DebtActionDraft(
                action = action,
                debtId = debt.id,
                walletId = state.wallets.firstOrNull()?.id ?: 0,
                amount = if (action == "close") debt.remainingAmount else "",
                paymentDate = todayDisplayText(),
            ),
            error = null,
            notice = null,
        )
    }

    fun closeActionDialog() {
        mutableState.value = mutableState.value.copy(actionDraft = null, actionInProgress = false, error = null)
    }

    fun updateActionDraft(draft: DebtActionDraft) {
        mutableState.value = mutableState.value.copy(actionDraft = draft, error = null, notice = null)
    }

    fun submitDebtAction() {
        val draft = mutableState.value.actionDraft ?: return
        val requiresWallet = draft.action != "write_off"
        DebtsValidation.validateActionDraft(draft, requiresWallet)?.let { validationError ->
            mutableState.value = mutableState.value.copy(error = validationError, notice = null)
            return
        }
        mutableState.value = mutableState.value.copy(actionInProgress = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val request = RegisterDebtPaymentRequest(
                    debtId = draft.debtId,
                    walletId = if (requiresWallet) draft.walletId else null,
                    amount = draft.amount.trim(),
                    paymentDate = draft.paymentDate.toStorageDate(),
                    note = draft.note.trim(),
                )
                val notice = when (draft.action) {
                    "write_off" -> {
                        val payment = engine.registerDebtWriteOff(request)
                        "Write-off registered (id=${payment.id})"
                    }
                    "close" -> {
                        val closed = engine.closeDebt(request)
                        if (closed.kind == "loan") {
                            "Loan closed (id=${closed.id})"
                        } else {
                            "Debt closed (id=${closed.id})"
                        }
                    }
                    else -> {
                        val payment = engine.registerDebtPayment(request)
                        "Payment registered (id=${payment.id})"
                    }
                }
                mutableState.value = mutableState.value.copy(
                    actionDraft = null,
                    actionInProgress = false,
                    selectedDebtId = draft.debtId,
                )
                refresh(notice = notice)
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    actionInProgress = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun requestDeleteSelectedDebt() {
        val state = mutableState.value
        val debt = selectedDebt(state)
        if (debt == null) {
            mutableState.value = state.copy(error = "Select a debt or loan first", notice = null)
            return
        }
        mutableState.value = state.copy(
            deleteDebtId = debt.id,
            deletePayment = null,
            deleteInProgress = false,
            error = null,
            notice = null,
        )
    }

    fun closeDeleteDebtDialog() {
        mutableState.value = mutableState.value.copy(deleteDebtId = null, deleteInProgress = false, error = null)
    }

    fun deleteSelectedDebt() {
        val state = mutableState.value
        val debtId = state.deleteDebtId ?: return
        val debt = state.debts.firstOrNull { it.id == debtId }
        if (debt == null) {
            mutableState.value = state.copy(error = "Debt not found", notice = null)
            return
        }
        mutableState.value = state.copy(deleteInProgress = true, error = null, notice = null)
        launchSafely {
            runCatching {
                engine.deleteDebt(debtId)
                val notice = if (debt.kind == "loan") {
                    "Loan deleted (id=$debtId)"
                } else {
                    "Debt deleted (id=$debtId)"
                }
                mutableState.value = mutableState.value.copy(
                    deleteDebtId = null,
                    deleteInProgress = false,
                    selectedDebtId = null,
                    selectedHistory = emptyList(),
                )
                refresh(notice = notice)
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    deleteInProgress = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun requestDeletePayment(payment: DebtPaymentItem) {
        mutableState.value = mutableState.value.copy(
            deleteDebtId = null,
            deletePayment = payment,
            deleteLinkedRecord = false,
            deleteInProgress = false,
            error = null,
            notice = null,
        )
    }

    fun updateDeleteLinkedRecord(deleteLinkedRecord: Boolean) {
        mutableState.value = mutableState.value.copy(deleteLinkedRecord = deleteLinkedRecord, error = null)
    }

    fun closeDeletePaymentDialog() {
        mutableState.value = mutableState.value.copy(
            deletePayment = null,
            deleteLinkedRecord = false,
            deleteInProgress = false,
            error = null,
        )
    }

    fun deleteSelectedPayment() {
        val state = mutableState.value
        val payment = state.deletePayment ?: return
        mutableState.value = state.copy(deleteInProgress = true, error = null, notice = null)
        launchSafely {
            runCatching {
                val updated = engine.deleteDebtPayment(payment.id, state.deleteLinkedRecord && payment.recordId != null)
                mutableState.value = mutableState.value.copy(
                    deletePayment = null,
                    deleteLinkedRecord = false,
                    deleteInProgress = false,
                    selectedDebtId = updated.id,
                )
                refresh(notice = "Payment deleted (id=${payment.id})")
            }.onFailure { error ->
                mutableState.value = mutableState.value.copy(
                    deleteInProgress = false,
                    error = error.message ?: error::class.simpleName ?: "Unknown error",
                    notice = null,
                )
            }
        }
    }

    fun clearNotice() {
        mutableState.value = mutableState.value.copy(notice = null)
    }

    fun clearFeedback() {
        mutableState.value = mutableState.value.copy(error = null, notice = null)
    }

    private fun launchSafely(block: suspend () -> Unit) {
        scope.launch { block() }
    }

    private fun todayDisplayText(): String {
        val today = currentLedgerDate()
        return "${today.day.toString().padStart(2, '0')}.${today.month.toString().padStart(2, '0')}.${today.year.toString().padStart(4, '0')}"
    }

    private fun String.toStorageDate(): String =
        DateValidation.formatGuiDateToYmd(this) ?: trim()

    private fun selectedDebt(state: DebtsUiState): DebtItem? =
        state.debts.firstOrNull { it.id == state.selectedDebtId }
}
