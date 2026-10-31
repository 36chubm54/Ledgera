package app.ledgera.operations

import app.ledgera.model.OperationRecord
import app.ledgera.model.WalletOption

internal data class OperationJournalItem(
    val key: String,
    val title: String,
    val amount: String,
    val meta: String,
    val description: String,
    val tags: List<String>,
    val tagColors: Map<String, String> = emptyMap(),
    val selectableRecordId: Long?,
    val transferId: Long?,
    val linkedLabel: String?,
    val selected: Boolean,
    val bulkSelectable: Boolean,
    val wallet: WalletOption? = null,
    val targetWallet: WalletOption? = null,
)

internal fun operationJournalItems(
    records: List<OperationRecord>,
    wallets: List<WalletOption> = emptyList(),
    selectedRecordId: Long?,
    selectedBulkRecordIds: Set<Long> = emptySet(),
    selectedBulkTransferIds: Set<Long> = emptySet(),
    tagColors: Map<String, String> = emptyMap(),
): List<OperationJournalItem> {
    val consumedTransferIds = mutableSetOf<Long>()
    val result = mutableListOf<OperationJournalItem>()
    records.forEach { record ->
        val transferId = record.transferId
        if (transferId == null) {
            result += standaloneJournalItem(record, wallets, selectedRecordId, selectedBulkRecordIds, tagColors)
            return@forEach
        }
        if (!consumedTransferIds.add(transferId)) {
            return@forEach
        }
        result += transferJournalItem(
            records = records.filter { it.transferId == transferId },
            transferId = transferId,
            wallets = wallets,
            selectedBulkTransferIds = selectedBulkTransferIds,
        )
    }
    return result
}

private fun standaloneJournalItem(
    record: OperationRecord,
    wallets: List<WalletOption>,
    selectedRecordId: Long?,
    selectedBulkRecordIds: Set<Long>,
    tagColors: Map<String, String>,
): OperationJournalItem {
    val bulkSelectable =
        (record.type == "income" || record.type == "expense" || record.type == "mandatory_expense") &&
            !isTransferCommissionMarker(record.description)
    val selected = selectedBulkRecordIds.contains(record.id)
    return OperationJournalItem(
        key = "record:${record.id}",
        title = record.category,
        amount = "${record.amountOriginal} ${record.currency}",
        meta = "${record.date} · ${record.type} · ${walletLabel(record.walletId, wallets)}",
        description = record.description,
        tags = record.tags,
        tagColors = tagColors,
        selectableRecordId = record.id,
        transferId = null,
        linkedLabel = if (record.relatedDebtId != null) "Debt-linked" else null,
        selected = selectedRecordId == record.id || selected,
        bulkSelectable = bulkSelectable,
        wallet = wallets.firstOrNull { it.id == record.walletId },
    )
}

private fun transferJournalItem(
    records: List<OperationRecord>,
    transferId: Long,
    wallets: List<WalletOption>,
    selectedBulkTransferIds: Set<Long>,
): OperationJournalItem {
    val expense = records.firstOrNull { it.type == "expense" }
    val income = records.firstOrNull { it.type == "income" }
    val primary = expense ?: income ?: records.first()
    val direction = if (expense != null && income != null) {
        "${walletLabel(expense.walletId, wallets)} -> ${walletLabel(income.walletId, wallets)}"
    } else {
        walletLabel(primary.walletId, wallets)
    }
    return OperationJournalItem(
        key = "transfer:$transferId",
        title = "Transfer · transfer #$transferId",
        amount = "${primary.amountOriginal} ${primary.currency}",
        meta = "${primary.date} · transfer · $direction",
        description = primary.description,
        tags = emptyList(),
        selectableRecordId = null,
        transferId = transferId,
        linkedLabel = "Transfer-linked",
        selected = selectedBulkTransferIds.contains(transferId),
        bulkSelectable = true,
        wallet = wallets.firstOrNull { it.id == primary.walletId },
        targetWallet = if (expense != null && income != null) {
            wallets.firstOrNull { it.id == income.walletId }
        } else {
            null
        },
    )
}

private fun isTransferCommissionMarker(description: String): Boolean =
    Regex("""^\[transfer:\d+]$""").matches(description.trim())

private fun walletLabel(walletId: Long, wallets: List<WalletOption>): String =
    wallets.firstOrNull { it.id == walletId }?.name?.takeIf(String::isNotBlank)
        ?: "wallet #$walletId"
