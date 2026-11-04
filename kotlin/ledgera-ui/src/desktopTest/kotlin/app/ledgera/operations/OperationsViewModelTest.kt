package app.ledgera.operations

import app.ledgera.bridge.EngineAdapter
import app.ledgera.model.AddMandatoryToRecordsRequest
import app.ledgera.model.AuditFinding
import app.ledgera.model.CreateDebtRequest
import app.ledgera.model.CreateMandatoryTemplateRequest
import app.ledgera.model.CreateOperationRequest
import app.ledgera.model.CreateTransferRequest
import app.ledgera.model.CreateTransferResult
import app.ledgera.model.CreateWalletRequest
import app.ledgera.model.CurrencyTransferRequest
import app.ledgera.model.CurrencyTransferResult
import app.ledgera.model.DebtItem
import app.ledgera.model.DebtPaymentItem
import app.ledgera.model.EngineStatus
import app.ledgera.model.OperationFilter
import app.ledgera.model.OperationDeleteResult
import app.ledgera.model.OperationExportResult
import app.ledgera.model.OperationImportResult
import app.ledgera.model.OperationRecord
import app.ledgera.model.OperationSuggestions
import app.ledgera.model.TagColor
import app.ledgera.model.MandatoryAutoPayResult
import app.ledgera.model.MandatoryExportResult
import app.ledgera.model.MandatoryImportResult
import app.ledgera.model.MandatoryTemplateItem
import app.ledgera.model.RegisterDebtPaymentRequest
import app.ledgera.model.TransferDetails
import app.ledgera.model.UpdateMandatoryTemplateRequest
import app.ledgera.model.UpdateOperationRequest
import app.ledgera.model.UpdateTransferRequest
import app.ledgera.model.UpdateTransferResult
import app.ledgera.model.WalletDeleteResult
import app.ledgera.model.WalletOption
import app.ledgera.model.WalletSettingsItem
import java.util.Locale
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers

class OperationsViewModelTest {
    @Test
    fun createRejectsEmptyCategoryBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "10",
                currency = "KZT",
                rateAtOperation = "1",
                amountBase = "10",
                category = "",
                note = "",
            )
        )

        assertEquals("Category is required", viewModel.state.value.error)
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createRejectsInvalidDateBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "32.13.2026",
                walletId = 1,
                amountOriginal = "10",
                currency = "KZT",
                rateAtOperation = "1",
                amountBase = "10",
                category = "Salary",
                note = "",
            )
        )

        assertEquals("Date must use a valid DD.MM.YYYY value", viewModel.state.value.error)
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createRejectsFutureDateBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2999",
                walletId = 1,
                amountOriginal = "10",
                currency = "KZT",
                rateAtOperation = "1",
                amountBase = "10",
                category = "Salary",
                note = "",
            )
        )

        assertEquals("Date cannot be in the future", viewModel.state.value.error)
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createRejectsInvalidCurrencyBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "10",
                currency = "K1T",
                rateAtOperation = "1",
                amountBase = "10",
                category = "Salary",
                note = "",
            )
        )

        assertEquals("Currency code must contain 3 letters", viewModel.state.value.error)
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createRejectsInvalidAmountBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "ten",
                currency = "KZT",
                rateAtOperation = "1",
                amountBase = "ten",
                category = "Salary",
                note = "",
            )
        )

        assertEquals("Amount must be a positive number", viewModel.state.value.error)
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createRejectsZeroAmountBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "0.004",
                currency = "KZT",
                rateAtOperation = "1",
                amountBase = "0.004",
                category = "Salary",
                note = "",
            )
        )

        assertEquals("Amount must be a positive number", viewModel.state.value.error)
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createRejectsUnsupportedCurrencyBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "10",
                currency = "AAA",
                rateAtOperation = "1",
                amountBase = "10",
                category = "Salary",
                note = "",
            )
        )

        assertEquals("Unsupported currency", viewModel.state.value.error)
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createRejectsNonBaseCurrencyBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "10",
                currency = "USD",
                rateAtOperation = "1",
                amountBase = "10",
                category = "Salary",
                note = "",
            )
        )

        assertEquals(
            "Standalone Operations currently supports base-currency records only (KZT)",
            viewModel.state.value.error,
        )
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createRejectsNumericOnlyTagsBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "10",
                currency = "KZT",
                rateAtOperation = "1",
                amountBase = "10",
                category = "Salary",
                note = "",
                tags = listOf("123", "work"),
            )
        )

        assertEquals(
            "Invalid tag: tags must not contain numbers only (\"123\")",
            viewModel.state.value.error,
        )
        assertEquals(0, adapter.createCalls)
    }

    @Test
    fun createSuccessShowsNotice() {
        val adapter = FakeEngineAdapter(records = mutableListOf())
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "10",
                currency = "KZT",
                rateAtOperation = "1",
                amountBase = "10",
                category = "Salary",
                note = "",
            )
        )

        assertEquals(1, adapter.createCalls)
        assertEquals("2026-01-01", adapter.lastCreateRequest?.date)
        assertEquals("Operation added", viewModel.state.value.notice)
    }

    @Test
    fun successfulCurrencyTransferInvokesCloseCallback() {
        val adapter = FakeEngineAdapter(records = mutableListOf())
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))
        var closed = false

        viewModel.createCurrencyTransfer(
            CurrencyTransferRequest(
                fromWalletId = 1,
                toWalletId = 2,
                date = "01.01.2026",
                amount = "10",
                amountCurrency = "KZT",
                note = "Move",
            ),
        ) { closed = true }

        assertEquals(true, closed)
        assertEquals(1, adapter.createCurrencyTransferCalls)
        assertEquals("Currency transfer created (id=42)", viewModel.state.value.notice)
    }

    @Test
    fun importExportNullPathsDoNotCallEngine() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportRecords(null)
        viewModel.exportRecords(null)

        assertEquals(0, adapter.previewImportCalls)
        assertEquals(0, adapter.previewImportXlsxCalls)
        assertEquals(0, adapter.importCalls)
        assertEquals(0, adapter.importXlsxCalls)
        assertEquals(0, adapter.exportCalls)
        assertEquals(0, adapter.exportXlsxCalls)
        assertEquals(null, viewModel.state.value.notice)
        assertEquals(null, viewModel.state.value.error)
    }

    @Test
    fun importPreviewThenCommitRefreshesAndShowsNoticeForCsv() {
        val adapter = FakeEngineAdapter(records = mutableListOf(operationRecord(id = 1)))
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportRecords("C:\\Temp\\ops.csv")
        assertEquals(1, adapter.previewImportCalls)
        assertEquals(2L, viewModel.state.value.importPreview?.imported)

        viewModel.confirmImportRecords()

        assertEquals(1, adapter.importCalls)
        assertEquals("Imported 2 rows", viewModel.state.value.notice)
        assertEquals(listOf(10L, 11L), viewModel.state.value.records.map { it.id })
        assertEquals(null, viewModel.state.value.importPreview)
    }

    @Test
    fun importCommitRejectsChangedFileAfterPreview() {
        val adapter = FakeEngineAdapter(records = mutableListOf(operationRecord(id = 1)))
        val snapshotProvider = MutableSnapshotProvider("100:1")
        val viewModel = OperationsViewModel(
            adapter,
            CoroutineScope(Dispatchers.Unconfined),
            snapshotProvider,
        )

        viewModel.previewImportRecords("C:\\Temp\\ops.csv")
        snapshotProvider.snapshot = "101:2"
        viewModel.confirmImportRecords()

        assertEquals(1, adapter.previewImportCalls)
        assertEquals(0, adapter.importCalls)
        assertEquals("Import file changed after preview. Run preview again.", viewModel.state.value.error)
        assertEquals(2L, viewModel.state.value.importPreview?.imported)
        assertEquals("C:\\Temp\\ops.csv", viewModel.state.value.importPath)
    }

    @Test
    fun importCommitRejectsBlockingPreviewBeforeEngineCall() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1)),
            importPreview = OperationImportResult(
                imported = 1,
                skipped = 1,
                errors = listOf("row 2: debt not found (99)"),
                dryRun = true,
                blockingErrors = true,
            ),
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportRecords("C:\\Temp\\ops.csv")
        viewModel.confirmImportRecords()

        assertEquals(1, adapter.previewImportCalls)
        assertEquals(0, adapter.importCalls)
        assertEquals("Import preview has blocking errors. Fix the file and run preview again.", viewModel.state.value.error)
        assertEquals(1L, viewModel.state.value.importPreview?.imported)
    }

    @Test
    fun importPreviewThenCommitDispatchesXlsxByExtension() {
        val adapter = FakeEngineAdapter(records = mutableListOf(operationRecord(id = 1)))
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportRecords("C:\\Temp\\ops.xlsx")
        assertEquals(0, adapter.previewImportCalls)
        assertEquals(1, adapter.previewImportXlsxCalls)
        assertEquals(2L, viewModel.state.value.importPreview?.imported)

        viewModel.confirmImportRecords()

        assertEquals(0, adapter.importCalls)
        assertEquals(1, adapter.importXlsxCalls)
        assertEquals("Imported 2 rows", viewModel.state.value.notice)
        assertEquals(listOf(10L, 11L), viewModel.state.value.records.map { it.id })
    }

    @Test
    fun importNoticeIncludesFirstSkippedRowError() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1)),
            importResult = OperationImportResult(
                imported = 1,
                skipped = 1,
                errors = listOf("row 3: unsupported type 'note'"),
                dryRun = false,
            ),
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportRecords("C:\\Temp\\ops.csv")
        viewModel.confirmImportRecords()

        assertEquals(
            "Imported 1 rows. Skipped 1 rows. First error: row 3: unsupported type 'note'",
            viewModel.state.value.notice,
        )
    }

    @Test
    fun importExportRejectUnknownExtensionBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportRecords("C:\\Temp\\ops.xls")
        assertEquals("Unsupported operations file format. Use .csv or .xlsx", viewModel.state.value.error)
        viewModel.exportRecords("C:\\Temp\\ops.json")
        assertEquals("Unsupported operations file format. Use .csv or .xlsx", viewModel.state.value.error)

        assertEquals(0, adapter.previewImportCalls)
        assertEquals(0, adapter.previewImportXlsxCalls)
        assertEquals(0, adapter.exportCalls)
        assertEquals(0, adapter.exportXlsxCalls)
    }

    @Test
    fun exportSuccessShowsToastNoticeForCsvAndXlsx() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.exportRecords("C:\\Temp\\ops.csv")

        assertEquals(1, adapter.exportCalls)
        assertEquals("Exported 3 rows to C:\\Temp\\ops.csv", viewModel.state.value.notice)
        assertEquals(null, viewModel.state.value.error)

        viewModel.exportRecords("C:\\Temp\\ops.xlsx")

        assertEquals(1, adapter.exportXlsxCalls)
        assertEquals("Exported 3 rows to C:\\Temp\\ops.xlsx", viewModel.state.value.notice)
        assertEquals(null, viewModel.state.value.error)
    }

    @Test
    fun deleteAllOperationsRefreshesStateAndShowsNotice() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(
                operationRecord(id = 1),
                operationRecord(id = 2, type = "expense", transferId = 42, category = "Transfer"),
                operationRecord(id = 3, type = "income", transferId = 42, category = "Transfer"),
                operationRecord(id = 4, type = "mandatory_expense", category = "Mandatory"),
                operationRecord(id = 5, type = "expense", relatedDebtId = 1, category = "Debt"),
            )
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.deleteAllOperations()

        assertEquals(1, adapter.deleteAllOperationsCalls)
        assertEquals(
            "Deleted 2 records, 1 transfers, and 1 debt-linked records",
            viewModel.state.value.notice,
        )
        assertEquals(emptyList<Long>(), viewModel.state.value.records.map { it.id })
        assertEquals(false, viewModel.state.value.selectiveDeleteMode)
    }

    @Test
    fun deleteAllOperationsWithoutCandidatesDoesNotCallEngine() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(
                operationRecord(id = 4, type = "unsupported", category = "Unsupported"),
            )
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        assertEquals(false, viewModel.state.value.hasBulkDeleteCandidates)

        viewModel.deleteAllOperations()

        assertEquals(0, adapter.deleteAllOperationsCalls)
        assertEquals("No operations, transfers, mandatory, or debt-linked rows to delete", viewModel.state.value.notice)
        assertEquals(null, viewModel.state.value.error)
    }

    @Test
    fun selectiveDeleteTogglesRowsAndDeletesSelection() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(
                operationRecord(id = 1),
                operationRecord(id = 2, type = "expense", transferId = 42, category = "Transfer"),
                operationRecord(id = 3, type = "income", transferId = 42, category = "Transfer"),
            )
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.startSelectiveDelete()
        viewModel.toggleBulkRecord(1)
        viewModel.toggleBulkTransfer(42)
        viewModel.deleteSelectedOperations()

        assertEquals(1, adapter.deleteSelectionCalls)
        assertEquals(listOf(1L), adapter.lastDeletedRecordIds)
        assertEquals(listOf(42L), adapter.lastDeletedTransferIds)
        assertEquals("Deleted 1 records, 1 transfers, and 0 debt-linked records", viewModel.state.value.notice)
        assertEquals(emptyList(), viewModel.state.value.records)
        assertEquals(false, viewModel.state.value.selectiveDeleteMode)
        assertEquals(emptySet(), viewModel.state.value.selectedBulkRecordIds)
        assertEquals(emptySet(), viewModel.state.value.selectedBulkTransferIds)
    }

    @Test
    fun selectiveDeleteCanSelectDebtLinkedRecords() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 5, type = "expense", relatedDebtId = 1, category = "Debt"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.startSelectiveDelete()
        viewModel.toggleBulkRecord(5)
        viewModel.deleteSelectedOperations()

        assertEquals(1, adapter.deleteSelectionCalls)
        assertEquals(listOf(5L), adapter.lastDeletedRecordIds)
        assertEquals("Deleted 0 records, 0 transfers, and 1 debt-linked records", viewModel.state.value.notice)
        assertEquals(emptyList(), viewModel.state.value.records)
    }

    @Test
    fun selectiveDeleteCanSelectMandatoryExpenseRecords() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 6, type = "mandatory_expense", category = "Rent"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.startSelectiveDelete()
        viewModel.toggleBulkRecord(6)
        viewModel.deleteSelectedOperations()

        assertEquals(1, adapter.deleteSelectionCalls)
        assertEquals(listOf(6L), adapter.lastDeletedRecordIds)
        assertEquals("Deleted 1 records, 0 transfers, and 0 debt-linked records", viewModel.state.value.notice)
        assertEquals(emptyList(), viewModel.state.value.records)
    }

    @Test
    fun selectiveDeleteRejectsEmptySelectionBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.startSelectiveDelete()
        viewModel.deleteSelectedOperations()

        assertEquals("Select at least one operation or transfer", viewModel.state.value.error)
        assertEquals(0, adapter.deleteSelectionCalls)
    }

    @Test
    fun createRuntimeFailureSurfacesInState() {
        val adapter = FakeEngineAdapter(createError = NoClassDefFoundError("missing create lambda"))
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.create(
            CreateOperationRequest(
                type = "income",
                date = "01.01.2026",
                walletId = 1,
                amountOriginal = "10",
                currency = "KZT",
                rateAtOperation = "1",
                amountBase = "10",
                category = "Salary",
                note = "",
            )
        )

        assertEquals("missing create lambda", viewModel.state.value.error)
        assertEquals(null, viewModel.state.value.notice)
    }

    @Test
    fun createTransferRejectsSameWalletBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.createTransfer(validTransferRequest(toWalletId = 1))

        assertEquals("Transfer wallets must be different", viewModel.state.value.error)
        assertEquals(0, adapter.createTransferCalls)
    }

    @Test
    fun createTransferRejectsInvalidAmountBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.createTransfer(validTransferRequest(amount = "0"))

        assertEquals("Amount must be a positive number", viewModel.state.value.error)
        assertEquals(0, adapter.createTransferCalls)
    }

    @Test
    fun createTransferRejectsNegativeCommissionBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.createTransfer(validTransferRequest(commissionAmount = "-1"))

        assertEquals("Amount must be zero or a positive number", viewModel.state.value.error)
        assertEquals(0, adapter.createTransferCalls)
    }

    @Test
    fun createTransferRejectsNonBaseCurrencyBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.createTransfer(validTransferRequest(currency = "USD"))

        assertEquals(
            "Transfer flow currently supports base-currency transfers only (KZT)",
            viewModel.state.value.error,
        )
        assertEquals(0, adapter.createTransferCalls)
    }

    @Test
    fun createTransferSuccessRefreshesStateAndShowsNotice() {
        val adapter = FakeEngineAdapter(records = mutableListOf())
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.createTransfer(validTransferRequest())

        assertEquals(1, adapter.createTransferCalls)
        assertEquals("2026-01-01", adapter.lastCreateTransferRequest?.date)
        assertEquals("Transfer created (id=42): Cash -> Card, 10 KZT", viewModel.state.value.notice)
        assertEquals(
            listOf("90.00", "10.00"),
            viewModel.state.value.wallets.map { it.balance },
        )
        assertEquals(
            listOf("expense:42", "income:42"),
            viewModel.state.value.records.map { "${it.type}:${it.transferId}" },
        )
        assertEquals(2, adapter.refreshCalls)
    }

    @Test
    fun selectTransferLinkedRecordShowsReadOnlyNotice() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 7, transferId = 42, category = "Transfer"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(7)

        assertEquals("Transfer-linked rows are read-only in this beta.1 slice", viewModel.state.value.notice)
        assertEquals(null, viewModel.state.value.editDraft)
        assertEquals(null, viewModel.state.value.selectedRecordId)
    }

    @Test
    fun selectDebtLinkedRecordShowsSelectiveDeleteNotice() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 8, relatedDebtId = 1, category = "Debt"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(8)

        assertEquals(
            "Debt-linked rows are read-only. Use Selective delete to remove them from Operations and debt history.",
            viewModel.state.value.notice,
        )
        assertEquals(null, viewModel.state.value.editDraft)
        assertEquals(null, viewModel.state.value.selectedRecordId)
    }

    @Test
    fun selectTransferLoadsTransferDraft() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.selectTransfer(42)

        assertEquals(1, adapter.getTransferCalls)
        assertEquals(42, viewModel.state.value.transferDraft?.id)
        assertEquals(1, viewModel.state.value.transferDraft?.fromWalletId)
        assertEquals(2, viewModel.state.value.transferDraft?.toWalletId)
        assertEquals("10.00", viewModel.state.value.transferDraft?.amount)
        assertEquals(null, viewModel.state.value.editDraft)
    }

    @Test
    fun updateTransferRejectsInvalidDraftBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.selectTransfer(42)
        viewModel.updateTransferDraft(viewModel.state.value.transferDraft!!.copy(toWalletId = 1))
        viewModel.updateSelectedTransfer()

        assertEquals("Transfer wallets must be different", viewModel.state.value.error)
        assertEquals(0, adapter.updateTransferCalls)
    }

    @Test
    fun updateTransferSuccessRefreshesStateAndClosesDialog() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(
                operationRecord(id = 1, type = "income", walletId = 2, transferId = 42),
                operationRecord(id = 2, type = "expense", walletId = 1, transferId = 42),
            )
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.selectTransfer(42)
        viewModel.updateTransferDraft(
            viewModel.state.value.transferDraft!!.copy(
                fromWalletId = 2,
                toWalletId = 1,
                amount = "5.25",
                note = "Return",
            )
        )
        viewModel.updateSelectedTransfer()

        assertEquals(1, adapter.updateTransferCalls)
        assertEquals(null, viewModel.state.value.transferDraft)
        assertEquals("Transfer updated (id=42)", viewModel.state.value.notice)
        assertEquals(
            listOf("income:42:1:5.25", "expense:42:2:5.25"),
            viewModel.state.value.records.map { "${it.type}:${it.transferId}:${it.walletId}:${it.amountOriginal}" },
        )
        assertEquals(2, adapter.refreshCalls)
    }

    @Test
    fun updateTransferEngineErrorStaysVisible() {
        val adapter = FakeEngineAdapter(updateTransferError = IllegalStateException("insufficient funds"))
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.selectTransfer(42)
        viewModel.updateSelectedTransfer()

        assertEquals("insufficient funds", viewModel.state.value.error)
        assertEquals(42, viewModel.state.value.transferDraft?.id)
    }

    @Test
    fun deleteTransferWithoutDraftSurfacesErrorBeforeEngineCall() {
        val adapter = FakeEngineAdapter()
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.deleteSelectedTransfer()

        assertEquals("Select a transfer first", viewModel.state.value.error)
        assertEquals(0, adapter.deleteTransferCalls)
    }

    @Test
    fun deleteTransferSuccessRefreshesStateAndClosesDialog() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(
                operationRecord(id = 1, type = "income", walletId = 2, transferId = 42),
                operationRecord(id = 2, type = "expense", walletId = 1, transferId = 42),
                operationRecord(id = 3, type = "expense", walletId = 1, category = "Commission", note = "[transfer:42]"),
            )
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.selectTransfer(42)
        viewModel.deleteSelectedTransfer()

        assertEquals(1, adapter.deleteTransferCalls)
        assertEquals(null, viewModel.state.value.transferDraft)
        assertEquals("Transfer deleted (id=42)", viewModel.state.value.notice)
        assertEquals(emptyList(), viewModel.state.value.records.mapNotNull { it.transferId })
        assertEquals(emptyList(), viewModel.state.value.records.filter { it.note == "[transfer:42]" })
        assertEquals(2, adapter.refreshCalls)
    }

    @Test
    fun deleteTransferEngineErrorStaysVisibleAndKeepsDraft() {
        val adapter = FakeEngineAdapter(deleteTransferError = IllegalStateException("integrity failed"))
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.selectTransfer(42)
        viewModel.deleteSelectedTransfer()

        assertEquals("integrity failed", viewModel.state.value.error)
        assertEquals(42, viewModel.state.value.transferDraft?.id)
    }

    @Test
    fun createTransferEngineErrorSurfacesInState() {
        val adapter = FakeEngineAdapter(transferError = IllegalStateException("insufficient funds"))
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.createTransfer(validTransferRequest())

        assertEquals("insufficient funds", viewModel.state.value.error)
        assertEquals(null, viewModel.state.value.notice)
    }

    @Test
    fun selectPopulatesEditDraft() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(
                operationRecord(id = 7, category = "Food", tags = listOf("home")),
            )
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(7)

        assertEquals(7, viewModel.state.value.editDraft?.id)
        assertEquals("Food", viewModel.state.value.editDraft?.category)
        assertEquals("home", viewModel.state.value.editDraft?.tagsText)
    }

    @Test
    fun updateSelectedRefreshesRecords() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1, category = "Food"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(category = "Updated"))
        viewModel.updateSelected()

        assertEquals(1, adapter.updateCalls)
        assertEquals("Updated", viewModel.state.value.records.single().category)
        assertEquals(null, viewModel.state.value.selectedRecordId)
        assertEquals(null, viewModel.state.value.editDraft)
        assertEquals("Operation updated", viewModel.state.value.notice)
    }

    @Test
    fun updateSelectedRejectsInvalidDateBeforeEngineCall() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1, category = "Food"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(date = "01.13.2026"))
        viewModel.updateSelected()

        assertEquals("Date must use a valid DD.MM.YYYY value", viewModel.state.value.error)
        assertEquals(0, adapter.updateCalls)
    }

    @Test
    fun updateSelectedRejectsFutureDateBeforeEngineCall() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1, category = "Food"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(date = "01.01.2999"))
        viewModel.updateSelected()

        assertEquals("Date cannot be in the future", viewModel.state.value.error)
        assertEquals(0, adapter.updateCalls)
    }

    @Test
    fun updateSelectedRejectsInvalidCurrencyBeforeEngineCall() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1, category = "Food"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(currency = "US1"))
        viewModel.updateSelected()

        assertEquals("Currency code must contain 3 letters", viewModel.state.value.error)
        assertEquals(0, adapter.updateCalls)
    }

    @Test
    fun updateSelectedRejectsInvalidAmountBeforeEngineCall() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1, category = "Food"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(amountOriginal = "-1"))
        viewModel.updateSelected()

        assertEquals("Amount must be a positive number", viewModel.state.value.error)
        assertEquals(0, adapter.updateCalls)
    }

    @Test
    fun updateSelectedRejectsUnsupportedCurrencyBeforeEngineCall() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1, category = "Food"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(currency = "AAA"))
        viewModel.updateSelected()

        assertEquals("Unsupported currency", viewModel.state.value.error)
        assertEquals(0, adapter.updateCalls)
    }

    @Test
    fun updateSelectedRejectsNonBaseCurrencyBeforeEngineCall() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1, category = "Food"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(currency = "USD"))
        viewModel.updateSelected()

        assertEquals(
            "Standalone Operations currently supports base-currency records only (KZT)",
            viewModel.state.value.error,
        )
        assertEquals(0, adapter.updateCalls)
    }

    @Test
    fun updateSelectedRejectsNumericOnlyTagsBeforeEngineCall() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1, category = "Food"))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(tagsText = "#777, food"))
        viewModel.updateSelected()

        assertEquals(
            "Invalid tag: tags must not contain numbers only (\"777\")",
            viewModel.state.value.error,
        )
        assertEquals(0, adapter.updateCalls)
    }

    @Test
    fun deleteSelectedRefreshesRecords() {
        val adapter = FakeEngineAdapter(
            records = mutableListOf(operationRecord(id = 1), operationRecord(id = 2))
        )
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.deleteSelected()

        assertEquals(1, adapter.deleteCalls)
        assertEquals(listOf(2L), viewModel.state.value.records.map { it.id })
        assertEquals(null, viewModel.state.value.selectedRecordId)
        assertEquals("Operation deleted", viewModel.state.value.notice)
    }

    @Test
    fun engineErrorSurfacesInState() {
        val adapter = FakeEngineAdapter(updateError = IllegalStateException("update failed"))
        val viewModel = OperationsViewModel(adapter, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.select(1)
        viewModel.updateSelected()

        assertEquals("update failed", viewModel.state.value.error)
    }

    @Test
    fun refreshLoadsAutocompleteSuggestions() {
        val viewModel = OperationsViewModel(FakeEngineAdapter(), CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()

        assertEquals(listOf("home"), viewModel.state.value.tags)
        assertEquals(listOf("Food"), viewModel.state.value.categories)
        assertEquals(listOf("Lunch", "Salary"), viewModel.state.value.noteSuggestions)
    }

    @Test
    fun refreshKeepsRecordsWhenAutocompleteLookupFails() {
        val viewModel = OperationsViewModel(
            FakeEngineAdapter(suggestionError = IllegalStateException("lookup failed")),
            CoroutineScope(Dispatchers.Unconfined),
        )

        viewModel.refresh()

        assertEquals(listOf(1L), viewModel.state.value.records.map { it.id })
        assertEquals(null, viewModel.state.value.error)
        assertEquals(emptyList(), viewModel.state.value.noteSuggestions)
    }
}

private class FakeEngineAdapter(
    private val records: MutableList<OperationRecord> = mutableListOf(operationRecord(id = 1)),
    private val createError: Throwable? = null,
    private val updateError: Throwable? = null,
    private val transferError: Throwable? = null,
    private val updateTransferError: Throwable? = null,
    private val deleteTransferError: Throwable? = null,
    private val deleteAllOperationsError: Throwable? = null,
    private val deleteSelectionError: Throwable? = null,
    private val suggestionError: Throwable? = null,
    private val importPreview: OperationImportResult = OperationImportResult(
        imported = 2,
        skipped = 0,
        errors = emptyList(),
        dryRun = true,
    ),
    private val importResult: OperationImportResult = OperationImportResult(
        imported = 2,
        skipped = 0,
        errors = emptyList(),
        dryRun = false,
    ),
    private val wallets: MutableList<WalletOption> = mutableListOf(
        WalletOption(id = 1, name = "Cash", currency = "KZT", balance = "100.00"),
        WalletOption(id = 2, name = "Card", currency = "KZT", balance = "0.00"),
    ),
) : EngineAdapter {
    var createCalls = 0
    var createTransferCalls = 0
    var createCurrencyTransferCalls = 0
    var getTransferCalls = 0
    var updateTransferCalls = 0
    var deleteTransferCalls = 0
    var deleteAllOperationsCalls = 0
    var deleteSelectionCalls = 0
    var updateCalls = 0
    var deleteCalls = 0
    var previewImportCalls = 0
    var previewImportXlsxCalls = 0
    var importCalls = 0
    var importXlsxCalls = 0
    var exportCalls = 0
    var exportXlsxCalls = 0
    var refreshCalls = 0
    var lastDeletedRecordIds: List<Long> = emptyList()
    var lastDeletedTransferIds: List<Long> = emptyList()
    var lastCreateRequest: CreateOperationRequest? = null
    var lastCreateTransferRequest: CreateTransferRequest? = null

    override suspend fun status() = EngineStatus(true, "test.db", "ready")

    override suspend fun baseCurrency(): String = "KZT"

    override suspend fun listRecords(filter: OperationFilter): List<OperationRecord> {
        refreshCalls += 1
        return records.toList()
    }

    override suspend fun getRecord(recordId: Long): OperationRecord? =
        records.firstOrNull { it.id == recordId }

    override suspend fun createRecord(request: CreateOperationRequest): OperationRecord {
        createError?.let { throw it }
        createCalls += 1
        lastCreateRequest = request
        val record = OperationRecord(
            id = (records.maxOfOrNull { it.id } ?: 0) + 1,
            type = request.type,
            date = request.date,
            walletId = request.walletId,
            amountOriginal = request.amountOriginal,
            currency = request.currency,
            rateAtOperation = request.rateAtOperation,
            amountBase = request.amountBase,
            category = request.category,
            note = request.note,
            tags = request.tags,
        )
        records += record
        return record
    }

    override suspend fun updateRecord(recordId: Long, request: UpdateOperationRequest): OperationRecord {
        updateError?.let { throw it }
        updateCalls += 1
        val updated = operationRecord(
            id = recordId,
            type = request.type,
            date = request.date,
            walletId = request.walletId,
            amountOriginal = request.amountOriginal,
            currency = request.currency,
            rateAtOperation = request.rateAtOperation,
            amountBase = request.amountBase,
            category = request.category,
            note = request.note,
            tags = request.tags,
        )
        val index = records.indexOfFirst { it.id == recordId }
        if (index >= 0) {
            records[index] = updated
        }
        return updated
    }

    override suspend fun createRecordWithTagColors(request: CreateOperationRequest): OperationRecord =
        createRecord(request)

    override suspend fun updateRecordWithTagColors(
        recordId: Long,
        request: UpdateOperationRequest,
    ): OperationRecord = updateRecord(recordId, request)

    override suspend fun deleteRecord(recordId: Long): Boolean {
        deleteCalls += 1
        return records.removeIf { it.id == recordId }
    }

    override suspend fun createTransfer(request: CreateTransferRequest): CreateTransferResult {
        transferError?.let { throw it }
        createTransferCalls += 1
        lastCreateTransferRequest = request
        val transferId = 42L
        val amount = request.amount.toDouble()
        replaceWalletBalance(request.fromWalletId) { balance -> balance - amount }
        replaceWalletBalance(request.toWalletId) { balance -> balance + amount }
        records += operationRecord(
            id = (records.maxOfOrNull { it.id } ?: 0) + 1,
            type = "expense",
            walletId = request.fromWalletId,
            amountOriginal = request.amount,
            amountBase = request.amount,
            category = "Transfer",
            note = request.note,
            transferId = transferId,
        )
        records += operationRecord(
            id = (records.maxOfOrNull { it.id } ?: 0) + 1,
            type = "income",
            walletId = request.toWalletId,
            amountOriginal = request.amount,
            amountBase = request.amount,
            category = "Transfer",
            note = request.note,
            transferId = transferId,
        )
        return CreateTransferResult(transferId = transferId)
    }

    override suspend fun createCurrencyTransfer(request: CurrencyTransferRequest): CurrencyTransferResult {
        createCurrencyTransferCalls += 1
        return CurrencyTransferResult(
            id = 42L,
            fromWalletId = request.fromWalletId,
            toWalletId = request.toWalletId,
            date = request.date,
            sourceAmount = request.amount,
            sourceCurrency = request.amountCurrency,
            targetAmount = request.amount,
            targetCurrency = request.amountCurrency,
            conversionRate = "1",
            note = request.note,
        )
    }

    override suspend fun getTransfer(transferId: Long): TransferDetails? {
        getTransferCalls += 1
        return TransferDetails(
            id = transferId,
            fromWalletId = 1,
            toWalletId = 2,
            date = "2026-01-01",
            amountOriginal = "10.00",
            currency = "KZT",
            rateAtOperation = "1.000000",
            amountBase = "10.00",
            note = "Move",
        )
    }

    override suspend fun updateTransfer(
        transferId: Long,
        request: UpdateTransferRequest,
    ): UpdateTransferResult {
        updateTransferError?.let { throw it }
        updateTransferCalls += 1
        records.replaceAll { record ->
            if (record.transferId != transferId) {
                record
            } else if (record.type == "expense") {
                record.copy(
                    walletId = request.fromWalletId,
                    date = request.date,
                    amountOriginal = request.amount,
                    amountBase = request.amount,
                    currency = request.currency,
                    note = request.note,
                )
            } else {
                record.copy(
                    walletId = request.toWalletId,
                    date = request.date,
                    amountOriginal = request.amount,
                    amountBase = request.amount,
                    currency = request.currency,
                    note = request.note,
                )
            }
        }
        return UpdateTransferResult(transferId = transferId)
    }

    override suspend fun deleteTransfer(transferId: Long): Boolean {
        deleteTransferError?.let { throw it }
        deleteTransferCalls += 1
        records.removeIf { it.transferId == transferId || it.note == "[transfer:$transferId]" }
        return true
    }

    override suspend fun deleteAllOperations(): OperationDeleteResult {
        deleteAllOperationsError?.let { throw it }
        deleteAllOperationsCalls += 1
        val transferIds = records.mapNotNull { it.transferId }.toSet()
        val deletedRecords = records.count {
            it.transferId == null &&
                it.relatedDebtId == null &&
                (it.type == "income" || it.type == "expense" || it.type == "mandatory_expense") &&
                !it.note.matches(Regex("""^\[transfer:\d+]$"""))
        }.toLong()
        val deletedDebtLinkedRecords = records.count {
            it.transferId == null &&
                it.relatedDebtId != null &&
                (it.type == "income" || it.type == "expense")
        }.toLong()
        val skippedRecords = records.count {
            it.transferId == null &&
                it.type != "income" &&
                it.type != "expense" &&
                it.type != "mandatory_expense"
        }.toLong()
        records.removeIf {
            it.transferId in transferIds ||
                (
                    it.transferId == null &&
                        (it.type == "income" || it.type == "expense" || it.type == "mandatory_expense") &&
                        !it.note.matches(Regex("""^\[transfer:\d+]$"""))
                    )
        }
        return OperationDeleteResult(
            deletedRecords = deletedRecords,
            deletedTransfers = transferIds.size.toLong(),
            deletedDebtLinkedRecords = deletedDebtLinkedRecords,
            skippedRecords = skippedRecords,
        )
    }

    override suspend fun deleteOperationsSelection(
        recordIds: List<Long>,
        transferIds: List<Long>,
    ): OperationDeleteResult {
        deleteSelectionError?.let { throw it }
        deleteSelectionCalls += 1
        lastDeletedRecordIds = recordIds
        lastDeletedTransferIds = transferIds
        val deletedDebtLinkedRecords = records.count { record ->
            record.id in recordIds && record.relatedDebtId != null
        }.toLong()
        val deletedRecords = recordIds.size.toLong() - deletedDebtLinkedRecords
        records.removeIf { record ->
            record.id in recordIds || record.transferId in transferIds || transferIds.any { record.note == "[transfer:$it]" }
        }
        return OperationDeleteResult(
            deletedRecords = deletedRecords,
            deletedTransfers = transferIds.size.toLong(),
            deletedDebtLinkedRecords = deletedDebtLinkedRecords,
            skippedRecords = 0,
        )
    }

    override suspend fun previewImportRecordsCsv(path: String): OperationImportResult {
        previewImportCalls += 1
        return importPreview
    }

    override suspend fun importRecordsCsv(path: String): OperationImportResult {
        importCalls += 1
        records.clear()
        records += operationRecord(id = 10, type = "income", category = "Imported")
        records += operationRecord(id = 11, type = "expense", category = "Imported")
        return importResult
    }

    override suspend fun exportRecordsCsv(path: String): OperationExportResult {
        exportCalls += 1
        return OperationExportResult(exportedRows = 3, path = path)
    }

    override suspend fun previewImportRecordsXlsx(path: String): OperationImportResult {
        previewImportXlsxCalls += 1
        return importPreview
    }

    override suspend fun importRecordsXlsx(path: String): OperationImportResult {
        importXlsxCalls += 1
        records.clear()
        records += operationRecord(id = 10, type = "income", category = "Imported")
        records += operationRecord(id = 11, type = "expense", category = "Imported")
        return importResult
    }

    override suspend fun exportRecordsXlsx(path: String): OperationExportResult {
        exportXlsxCalls += 1
        return OperationExportResult(exportedRows = 3, path = path)
    }

    override suspend fun listTags(): List<String> = listOf("home")

    override suspend fun listCategories(recordType: String): List<String> = listOf("Food")

    override suspend fun listRecordNotes(recordType: String?): List<String> = listOf("Lunch", "Salary")

    override suspend fun operationSuggestions(): OperationSuggestions {
        suggestionError?.let { throw it }
        return OperationSuggestions(
            tags = listOf("home"),
            incomeCategories = listOf("Salary"),
            expenseCategories = listOf("Food"),
            notes = listOf("Lunch", "Salary"),
            incomeNotes = listOf("Salary"),
            expenseNotes = listOf("Lunch"),
        )
    }

    override suspend fun listTagColors(): List<TagColor> = listOf(TagColor("home", "#fc5c66"))

    override suspend fun tagColorPalette(): List<String> = listOf("#fc5c66", "#ea3b5a")

    override suspend fun listWallets(): List<WalletOption> = emptyList()

    override suspend fun walletBalances(): List<WalletOption> = wallets.toList()

    override suspend fun listWalletsForSettings(): List<WalletSettingsItem> = emptyList()

    override suspend fun createWallet(request: CreateWalletRequest): WalletSettingsItem =
        WalletSettingsItem(
            id = 1,
            name = request.name,
            currency = request.currency,
            initialBalance = request.initialBalance,
            balance = request.initialBalance,
            system = false,
            allowNegative = request.allowNegative,
            active = true,
        )

    override suspend fun deleteWallet(walletId: Long): WalletDeleteResult =
        WalletDeleteResult(walletId, "hard_deleted")

    override suspend fun listDebts(): List<DebtItem> = emptyList()

    override suspend fun listDebtPayments(debtId: Long): List<DebtPaymentItem> = emptyList()

    override suspend fun createDebt(request: CreateDebtRequest): DebtItem =
        DebtItem(
            id = 1,
            contactName = request.contactName,
            kind = request.kind,
            totalAmount = request.amount,
            remainingAmount = request.amount,
            currency = request.currency,
            interestRate = "0.000000",
            status = "open",
            createdAt = request.createdAt,
        )

    override suspend fun registerDebtPayment(request: RegisterDebtPaymentRequest): DebtPaymentItem =
        debtPaymentItem(request.debtId)

    override suspend fun registerDebtWriteOff(request: RegisterDebtPaymentRequest): DebtPaymentItem =
        debtPaymentItem(request.debtId).copy(operationType = "debt_forgive", isWriteOff = true)

    override suspend fun closeDebt(request: RegisterDebtPaymentRequest): DebtItem =
        DebtItem(
            id = request.debtId,
            contactName = "Alice",
            kind = "debt",
            totalAmount = request.amount,
            remainingAmount = "0.00",
            currency = "KZT",
            interestRate = "0.000000",
            status = "closed",
            createdAt = request.paymentDate,
            closedAt = request.paymentDate,
        )

    override suspend fun deleteDebt(debtId: Long): Boolean = true

    override suspend fun deleteDebtPayment(paymentId: Long, deleteLinkedRecord: Boolean): DebtItem =
        DebtItem(
            id = 1,
            contactName = "Alice",
            kind = "debt",
            totalAmount = "10.00",
            remainingAmount = "10.00",
            currency = "KZT",
            interestRate = "0.000000",
            status = "open",
            createdAt = "2026-01-01",
        )

    override suspend fun runAudit(): List<AuditFinding> = emptyList()

    override suspend fun listMandatoryTemplates(): List<MandatoryTemplateItem> = emptyList()

    override suspend fun getMandatoryTemplate(templateId: Long): MandatoryTemplateItem? = null

    override suspend fun createMandatoryTemplate(request: CreateMandatoryTemplateRequest): MandatoryTemplateItem =
        mandatoryTemplateItem(
            id = 1,
            walletId = request.walletId,
            amountOriginal = request.amountOriginal,
            amountBase = request.amountBase,
            category = request.category,
            note = request.note,
            period = request.period,
            date = request.date,
        )

    override suspend fun updateMandatoryTemplate(
        templateId: Long,
        request: UpdateMandatoryTemplateRequest,
    ): MandatoryTemplateItem =
        mandatoryTemplateItem(
            id = templateId,
            walletId = request.walletId,
            amountBase = request.amountBase,
            period = request.period,
            date = request.date,
        )

    override suspend fun deleteMandatoryTemplate(templateId: Long): Boolean = true

    override suspend fun deleteAllMandatoryTemplates(): Long = 0

    override suspend fun addMandatoryToRecords(request: AddMandatoryToRecordsRequest): OperationRecord =
        operationRecord(id = 1, type = "mandatory_expense", walletId = request.walletId, date = request.date)

    override suspend fun applyMandatoryAutoPayments(today: String): MandatoryAutoPayResult =
        MandatoryAutoPayResult(createdRecords = emptyList())

    override suspend fun previewImportMandatoryCsv(path: String): MandatoryImportResult =
        MandatoryImportResult(imported = 0, skipped = 0, errors = emptyList(), dryRun = true)

    override suspend fun importMandatoryCsv(path: String): MandatoryImportResult =
        MandatoryImportResult(imported = 0, skipped = 0, errors = emptyList(), dryRun = false)

    override suspend fun exportMandatoryCsv(path: String): MandatoryExportResult =
        MandatoryExportResult(exportedRows = 0, path = path)

    override suspend fun previewImportMandatoryXlsx(path: String): MandatoryImportResult =
        MandatoryImportResult(imported = 0, skipped = 0, errors = emptyList(), dryRun = true)

    override suspend fun importMandatoryXlsx(path: String): MandatoryImportResult =
        MandatoryImportResult(imported = 0, skipped = 0, errors = emptyList(), dryRun = false)

    override suspend fun exportMandatoryXlsx(path: String): MandatoryExportResult =
        MandatoryExportResult(exportedRows = 0, path = path)

    private fun replaceWalletBalance(walletId: Long, update: (Double) -> Double) {
        val index = wallets.indexOfFirst { it.id == walletId }
        if (index < 0) {
            return
        }
        val wallet = wallets[index]
        wallets[index] = wallet.copy(balance = String.format(Locale.US, "%.2f", update(wallet.balance.toDouble())))
    }
}

private class MutableSnapshotProvider(var snapshot: String?) : ImportFileSnapshotProvider {
    override fun snapshot(path: String): String? = snapshot
}

private fun validTransferRequest(
    fromWalletId: Long = 1,
    toWalletId: Long = 2,
    date: String = "01.01.2026",
    amount: String = "10",
    currency: String = "KZT",
    commissionAmount: String = "0",
    commissionCurrency: String = "KZT",
) = CreateTransferRequest(
    fromWalletId = fromWalletId,
    toWalletId = toWalletId,
    date = date,
    amount = amount,
    currency = currency,
    note = "Move",
    commissionAmount = commissionAmount,
    commissionCurrency = commissionCurrency,
)

private fun operationRecord(
    id: Long,
    type: String = "expense",
    date: String = "2026-01-01",
    walletId: Long = 1,
    amountOriginal: String = "10.00",
    currency: String = "KZT",
    rateAtOperation: String = "1.000000",
    amountBase: String = "10.00",
    category: String = "General",
    note: String = "",
    tags: List<String> = emptyList(),
    transferId: Long? = null,
    relatedDebtId: Long? = null,
) = OperationRecord(
    id = id,
    type = type,
    date = date,
    walletId = walletId,
    transferId = transferId,
    relatedDebtId = relatedDebtId,
    amountOriginal = amountOriginal,
    currency = currency,
    rateAtOperation = rateAtOperation,
    amountBase = amountBase,
    category = category,
    note = note,
    tags = tags,
)

private fun debtPaymentItem(debtId: Long): DebtPaymentItem =
    DebtPaymentItem(
        id = 1,
        debtId = debtId,
        recordId = 1,
        operationType = "debt_repay",
        principalPaid = "10.00",
        isWriteOff = false,
        paymentDate = "2026-01-01",
    )

private fun mandatoryTemplateItem(
    id: Long,
    walletId: Long = 1,
    amountOriginal: String = "10.00",
    amountBase: String = "10.00",
    category: String = "Mandatory",
    note: String = "Template",
    period: String = "monthly",
    date: String = "",
) = MandatoryTemplateItem(
    id = id,
    walletId = walletId,
    amountOriginal = amountOriginal,
    currency = "KZT",
    rateAtOperation = "1.000000",
    amountBase = amountBase,
    category = category,
    note = note,
    period = period,
    date = date,
    autoPay = date.isNotBlank(),
)
