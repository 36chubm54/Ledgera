package app.ledgera.mandatory

import app.ledgera.bridge.MandatoryEngine
import app.ledgera.model.AddMandatoryToRecordsRequest
import app.ledgera.model.CreateMandatoryTemplateRequest
import app.ledgera.model.MandatoryAutoPayResult
import app.ledgera.model.MandatoryExportResult
import app.ledgera.model.MandatoryImportResult
import app.ledgera.model.MandatoryTemplateItem
import app.ledgera.model.OperationRecord
import app.ledgera.model.UpdateMandatoryTemplateRequest
import app.ledgera.model.WalletOption
import app.ledgera.operations.ImportFileSnapshotProvider
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers

class MandatoryViewModelTest {
    @Test
    fun refreshLoadsWalletsTemplatesAndSelection() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()

        assertEquals("KZT", viewModel.state.value.baseCurrency)
        assertEquals(listOf("Cash"), viewModel.state.value.wallets.map { it.name })
        assertEquals(listOf("Rent"), viewModel.state.value.templates.map { it.category })
        assertEquals(1, viewModel.state.value.selectedTemplateId)
    }

    @Test
    fun createRejectsInvalidDraftBeforeEngineCall() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.openCreateDialog()
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(note = "", amountOriginal = "10", amountBase = "10"))
        viewModel.saveTemplate()

        assertEquals("Note is required", viewModel.state.value.error)
        assertEquals(0, engine.createCalls)
    }

    @Test
    fun createSuccessRefreshesAndShowsNotice() {
        val engine = FakeMandatoryEngine(templates = mutableListOf())
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.openCreateDialog()
        viewModel.updateDraft(
            viewModel.state.value.editDraft!!.copy(
                amountOriginal = "25",
                amountBase = "25",
                note = "Internet",
            )
        )
        viewModel.saveTemplate()

        assertEquals(1, engine.createCalls)
        assertNull(viewModel.state.value.editDraft)
        assertEquals("Mandatory template created (id=1)", viewModel.state.value.notice)
        assertEquals(listOf("Internet"), viewModel.state.value.templates.map { it.note })
    }

    @Test
    fun createAllowsFutureAutoPayAnchorDate() {
        val engine = FakeMandatoryEngine(templates = mutableListOf())
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.openCreateDialog()
        viewModel.updateDraft(
            viewModel.state.value.editDraft!!.copy(
                amountOriginal = "25",
                amountBase = "25",
                note = "Internet",
                date = "01.01.2099",
            )
        )
        viewModel.saveTemplate()

        assertEquals(1, engine.createCalls)
        assertEquals("2099-01-01", engine.lastCreateRequest?.date)
        assertNull(viewModel.state.value.error)
        assertEquals("2099-01-01", viewModel.state.value.templates.single().date)
    }

    @Test
    fun updateSuccessClosesDialogAndShowsNotice() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.selectTemplate(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(amountBase = "35", period = "weekly"))
        viewModel.saveTemplate()

        assertEquals(1, engine.updateCalls)
        assertNull(viewModel.state.value.editDraft)
        assertEquals("Mandatory template updated (id=1)", viewModel.state.value.notice)
        assertEquals("weekly", viewModel.state.value.templates.first().period)
    }

    @Test
    fun updateAllowsFutureAutoPayAnchorDate() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.selectTemplate(1)
        viewModel.updateDraft(viewModel.state.value.editDraft!!.copy(date = "01.01.2099"))
        viewModel.saveTemplate()

        assertEquals(1, engine.updateCalls)
        assertEquals("2099-01-01", engine.lastUpdateRequest?.date)
        assertNull(viewModel.state.value.error)
        assertEquals("2099-01-01", viewModel.state.value.templates.first().date)
    }

    @Test
    fun addToRecordsSuccessRefreshesAndShowsNotice() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.openAddToRecordsDialog()
        viewModel.updateAddToRecordsDraft(viewModel.state.value.addToRecordsDraft!!.copy(date = "05.03.2026"))
        viewModel.addToRecords()

        assertEquals(1, engine.addToRecordsCalls)
        assertEquals("2026-03-05", engine.lastAddToRecordsRequest?.date)
        assertNull(viewModel.state.value.addToRecordsDraft)
        assertEquals("Mandatory record added (id=7)", viewModel.state.value.notice)
    }

    @Test
    fun addToRecordsRejectsFutureRecordDate() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.openAddToRecordsDialog()
        viewModel.updateAddToRecordsDraft(viewModel.state.value.addToRecordsDraft!!.copy(date = "01.01.2099"))
        viewModel.addToRecords()

        assertEquals(0, engine.addToRecordsCalls)
        assertEquals("Date cannot be in the future", viewModel.state.value.error)
    }

    @Test
    fun autoPaySuccessShowsCreatedCount() {
        val engine = FakeMandatoryEngine(autoPayRecords = listOf(operationRecord(id = 8), operationRecord(id = 9)))
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.applyAutoPayments()

        assertEquals(1, engine.autoPayCalls)
        assertNull(viewModel.state.value.notice)
        assertEquals("Auto-pay applied", viewModel.state.value.autoPayPopup?.title)
        assertEquals("Created 2 mandatory operation records.", viewModel.state.value.autoPayPopup?.message)
    }

    @Test
    fun autoPayIgnoresFutureTemplateAnchorValidation() {
        val engine = FakeMandatoryEngine(
            templates = mutableListOf(mandatoryTemplate(date = "2099-01-01")),
            autoPayRecords = emptyList(),
        )
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.selectTemplate(1)
        viewModel.applyAutoPayments()

        assertEquals(1, engine.autoPayCalls)
        assertNull(viewModel.state.value.editDraft)
        assertNull(viewModel.state.value.error)
        assertNull(viewModel.state.value.notice)
        assertEquals("Auto-pay applied", viewModel.state.value.autoPayPopup?.title)
        assertEquals("Created 0 mandatory operation records.", viewModel.state.value.autoPayPopup?.message)
    }

    @Test
    fun startupAutoPaySkipsPopupWhenNoRecordsWereCreated() {
        val engine = FakeMandatoryEngine(autoPayRecords = emptyList())
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.applyAutoPaymentsOnStartup()

        assertEquals(1, engine.autoPayCalls)
        assertNull(viewModel.state.value.notice)
        assertNull(viewModel.state.value.error)
        assertNull(viewModel.state.value.autoPayPopup)
    }

    @Test
    fun startupAutoPayShowsPopupWhenRecordsWereCreated() {
        val engine = FakeMandatoryEngine(autoPayRecords = listOf(operationRecord(id = 8)))
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.applyAutoPaymentsOnStartup()

        assertEquals(1, engine.autoPayCalls)
        assertNull(viewModel.state.value.notice)
        assertEquals("Auto-pay applied", viewModel.state.value.autoPayPopup?.title)
        assertEquals("Created 1 mandatory operation record.", viewModel.state.value.autoPayPopup?.message)
    }

    @Test
    fun closeAutoPayPopupClearsPopup() {
        val engine = FakeMandatoryEngine(autoPayRecords = listOf(operationRecord(id = 8)))
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.applyAutoPayments()
        viewModel.closeAutoPayPopup()

        assertNull(viewModel.state.value.autoPayPopup)
    }

    @Test
    fun deleteSelectedSuccessRefreshesAndShowsNotice() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.requestDeleteSelectedTemplate()
        viewModel.deleteSelectedTemplate()

        assertEquals(1, engine.deleteCalls)
        assertEquals("Mandatory template deleted (id=1)", viewModel.state.value.notice)
        assertEquals(emptyList(), viewModel.state.value.templates)
    }

    @Test
    fun deleteAllSuccessRefreshesAndShowsNotice() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.requestDeleteAllTemplates()
        viewModel.deleteAllTemplates()

        assertEquals(1, engine.deleteAllCalls)
        assertEquals("All mandatory templates deleted (1)", viewModel.state.value.notice)
        assertEquals(emptyList(), viewModel.state.value.templates)
    }

    @Test
    fun engineErrorKeepsDialogOpen() {
        val engine = FakeMandatoryEngine(createError = IllegalStateException("boom"))
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.refresh()
        viewModel.openCreateDialog()
        viewModel.updateDraft(
            viewModel.state.value.editDraft!!.copy(
                amountOriginal = "25",
                amountBase = "25",
                note = "Internet",
            )
        )
        viewModel.saveTemplate()

        assertEquals("boom", viewModel.state.value.error)
        assertEquals(1, engine.createCalls)
        assertEquals("Internet", viewModel.state.value.editDraft?.note)
    }

    @Test
    fun importPreviewSuccessStoresPreviewAndPath() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportMandatory("C:\\Temp\\mandatory.xlsx")

        assertEquals(1, engine.previewXlsxCalls)
        assertEquals(2, viewModel.state.value.importPreview?.imported)
        assertEquals("C:\\Temp\\mandatory.xlsx", viewModel.state.value.importPath)
    }

    @Test
    fun importRejectsUnsupportedExtensionBeforeEngineCall() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportMandatory("C:\\Temp\\mandatory.json")
        viewModel.exportMandatory("C:\\Temp\\mandatory.json")

        assertEquals(0, engine.previewCsvCalls + engine.previewXlsxCalls + engine.exportCsvCalls + engine.exportXlsxCalls)
        assertEquals("Unsupported mandatory file format. Use .csv or .xlsx", viewModel.state.value.error)
    }

    @Test
    fun confirmImportSuccessRefreshesAndShowsNotice() {
        val engine = FakeMandatoryEngine(templates = mutableListOf(mandatoryTemplate(note = "Old")))
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.previewImportMandatory("C:\\Temp\\mandatory.csv")
        viewModel.confirmImportMandatory()

        assertEquals(1, engine.importCsvCalls)
        assertNull(viewModel.state.value.importPreview)
        assertEquals("Mandatory templates imported: 2", viewModel.state.value.notice)
        assertEquals(listOf("Imported"), viewModel.state.value.templates.map { it.note })
    }

    @Test
    fun confirmImportRejectsChangedFileSnapshot() {
        val snapshotProvider = MutableSnapshotProvider("a")
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(
            engine,
            importFileSnapshotProvider = snapshotProvider,
            scope = CoroutineScope(Dispatchers.Unconfined),
        )

        viewModel.previewImportMandatory("C:\\Temp\\mandatory.csv")
        snapshotProvider.value = "b"
        viewModel.confirmImportMandatory()

        assertEquals(0, engine.importCsvCalls)
        assertEquals("Import file changed after preview. Run preview again.", viewModel.state.value.error)
    }

    @Test
    fun exportSuccessShowsToastNotice() {
        val engine = FakeMandatoryEngine()
        val viewModel = MandatoryViewModel(engine, CoroutineScope(Dispatchers.Unconfined))

        viewModel.exportMandatory("C:\\Temp\\mandatory.xlsx")

        assertEquals(1, engine.exportXlsxCalls)
        assertEquals("Mandatory templates exported: 3", viewModel.state.value.notice)
    }
}

private class FakeMandatoryEngine(
    private val templates: MutableList<MandatoryTemplateItem> = mutableListOf(mandatoryTemplate()),
    private val createError: Throwable? = null,
    private val autoPayRecords: List<OperationRecord> = emptyList(),
) : MandatoryEngine {
    var createCalls = 0
    var updateCalls = 0
    var addToRecordsCalls = 0
    var autoPayCalls = 0
    var deleteCalls = 0
    var deleteAllCalls = 0
    var previewCsvCalls = 0
    var previewXlsxCalls = 0
    var importCsvCalls = 0
    var importXlsxCalls = 0
    var exportCsvCalls = 0
    var exportXlsxCalls = 0
    var lastCreateRequest: CreateMandatoryTemplateRequest? = null
    var lastUpdateRequest: UpdateMandatoryTemplateRequest? = null
    var lastAddToRecordsRequest: AddMandatoryToRecordsRequest? = null

    override suspend fun baseCurrency(): String = "KZT"

    override suspend fun listWallets(): List<WalletOption> =
        listOf(WalletOption(id = 1, name = "Cash", currency = "KZT", balance = "100.00"))

    override suspend fun listMandatoryTemplates(): List<MandatoryTemplateItem> = templates.toList()

    override suspend fun getMandatoryTemplate(templateId: Long): MandatoryTemplateItem? =
        templates.firstOrNull { it.id == templateId }

    override suspend fun createMandatoryTemplate(request: CreateMandatoryTemplateRequest): MandatoryTemplateItem {
        createCalls += 1
        createError?.let { throw it }
        lastCreateRequest = request
        val template = mandatoryTemplate(
            id = (templates.maxOfOrNull { it.id } ?: 0) + 1,
            walletId = request.walletId,
            amountOriginal = request.amountOriginal,
            amountBase = request.amountBase,
            category = request.category,
            note = request.note,
            period = request.period,
            date = request.date,
        )
        templates += template
        return template
    }

    override suspend fun updateMandatoryTemplate(
        templateId: Long,
        request: UpdateMandatoryTemplateRequest,
    ): MandatoryTemplateItem {
        updateCalls += 1
        lastUpdateRequest = request
        val updated = templates.first { it.id == templateId }.copy(
            walletId = request.walletId,
            amountBase = request.amountBase,
            period = request.period,
            date = request.date,
            autoPay = request.date.isNotBlank(),
        )
        templates[templates.indexOfFirst { it.id == templateId }] = updated
        return updated
    }

    override suspend fun deleteMandatoryTemplate(templateId: Long): Boolean {
        deleteCalls += 1
        templates.removeIf { it.id == templateId }
        return true
    }

    override suspend fun deleteAllMandatoryTemplates(): Long {
        deleteAllCalls += 1
        val deleted = templates.size.toLong()
        templates.clear()
        return deleted
    }

    override suspend fun addMandatoryToRecords(request: AddMandatoryToRecordsRequest): OperationRecord {
        addToRecordsCalls += 1
        lastAddToRecordsRequest = request
        return operationRecord(id = 7, date = request.date, walletId = request.walletId)
    }

    override suspend fun applyMandatoryAutoPayments(today: String): MandatoryAutoPayResult {
        autoPayCalls += 1
        return MandatoryAutoPayResult(createdRecords = autoPayRecords)
    }

    override suspend fun previewImportMandatoryCsv(path: String): MandatoryImportResult {
        previewCsvCalls += 1
        return MandatoryImportResult(imported = 2, skipped = 0, errors = emptyList(), dryRun = true)
    }

    override suspend fun importMandatoryCsv(path: String): MandatoryImportResult {
        importCsvCalls += 1
        templates.clear()
        templates += mandatoryTemplate(note = "Imported")
        return MandatoryImportResult(imported = 2, skipped = 0, errors = emptyList(), dryRun = false)
    }

    override suspend fun exportMandatoryCsv(path: String): MandatoryExportResult {
        exportCsvCalls += 1
        return MandatoryExportResult(exportedRows = 3, path = path)
    }

    override suspend fun previewImportMandatoryXlsx(path: String): MandatoryImportResult {
        previewXlsxCalls += 1
        return MandatoryImportResult(imported = 2, skipped = 0, errors = emptyList(), dryRun = true)
    }

    override suspend fun importMandatoryXlsx(path: String): MandatoryImportResult {
        importXlsxCalls += 1
        templates.clear()
        templates += mandatoryTemplate(note = "Imported")
        return MandatoryImportResult(imported = 2, skipped = 0, errors = emptyList(), dryRun = false)
    }

    override suspend fun exportMandatoryXlsx(path: String): MandatoryExportResult {
        exportXlsxCalls += 1
        return MandatoryExportResult(exportedRows = 3, path = path)
    }
}

private class MutableSnapshotProvider(var value: String?) : ImportFileSnapshotProvider {
    override fun snapshot(path: String): String? = value
}

private fun mandatoryTemplate(
    id: Long = 1,
    walletId: Long = 1,
    amountOriginal: String = "30.00",
    amountBase: String = "30.00",
    category: String = "Rent",
    note: String = "Monthly rent",
    period: String = "monthly",
    date: String = "2026-01-01",
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

private fun operationRecord(
    id: Long,
    date: String = "2026-01-01",
    walletId: Long = 1,
) = OperationRecord(
    id = id,
    type = "mandatory_expense",
    date = date,
    walletId = walletId,
    amountOriginal = "10.00",
    currency = "KZT",
    rateAtOperation = "1.000000",
    amountBase = "10.00",
    category = "Rent",
    note = "Monthly rent",
    tags = emptyList(),
)
