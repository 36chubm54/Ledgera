package app.ledgera.operations

import app.ledgera.model.OperationRecord
import kotlin.test.Test
import kotlin.test.assertEquals

class OperationJournalTest {
    @Test
    fun transferLinkedMirrorRowsRenderAsSingleJournalItemWithDirection() {
        val rows = listOf(
            operationRecord(id = 10, type = "income", walletId = 2, transferId = 7),
            operationRecord(id = 9, type = "expense", walletId = 1, transferId = 7),
        )

        val items = operationJournalItems(rows, selectedRecordId = null)

        assertEquals(1, items.size)
        assertEquals("transfer:7", items.single().key)
        assertEquals("Transfer · transfer #7", items.single().title)
        assertEquals("2026-01-01 · transfer · wallet #1 -> wallet #2", items.single().meta)
        assertEquals(7, items.single().transferId)
        assertEquals(null, items.single().selectableRecordId)
    }

    @Test
    fun standaloneRowsRemainIndividualEditableJournalItems() {
        val rows = listOf(operationRecord(id = 3, category = "Food"))

        val items = operationJournalItems(rows, selectedRecordId = 3)

        assertEquals(1, items.size)
        assertEquals("record:3", items.single().key)
        assertEquals("Food", items.single().title)
        assertEquals(3, items.single().selectableRecordId)
        assertEquals(null, items.single().transferId)
    }

    @Test
    fun debtLinkedRowsRemainVisibleAndBulkSelectable() {
        val rows = listOf(operationRecord(id = 4, category = "Debt", relatedDebtId = 9))

        val items = operationJournalItems(rows, selectedRecordId = null)

        assertEquals(1, items.size)
        assertEquals("record:4", items.single().key)
        assertEquals("Debt-linked", items.single().linkedLabel)
        assertEquals(4, items.single().selectableRecordId)
        assertEquals(true, items.single().bulkSelectable)
    }

    @Test
    fun standaloneRowsKeepTagColorAssignmentsForJournalRendering() {
        val rows = listOf(operationRecord(id = 5, tags = listOf("food", "new")))

        val items = operationJournalItems(
            rows,
            selectedRecordId = null,
            tagColors = mapOf("food" to "#fc5c66"),
        )

        assertEquals("#fc5c66", items.single().tagColors["food"])
        assertEquals(null, items.single().tagColors["new"])
    }
}

private fun operationRecord(
    id: Long,
    type: String = "expense",
    walletId: Long = 1,
    category: String = "Transfer",
    transferId: Long? = null,
    relatedDebtId: Long? = null,
    tags: List<String> = emptyList(),
) = OperationRecord(
    id = id,
    type = type,
    date = "2026-01-01",
    walletId = walletId,
    transferId = transferId,
    relatedDebtId = relatedDebtId,
    amountOriginal = "10.00",
    currency = "KZT",
    rateAtOperation = "1.000000",
    amountBase = "10.00",
    category = category,
    description = "",
    tags = tags,
)
