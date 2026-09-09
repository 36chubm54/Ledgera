package app.ledgera.reports

import app.ledgera.bridge.ReportsEngine
import app.ledgera.model.ReportCategoryRow
import app.ledgera.model.ReportDebtRow
import app.ledgera.model.ReportExportResult
import app.ledgera.model.ReportFilters
import app.ledgera.model.ReportMonthlyRow
import app.ledgera.model.ReportOperationRow
import app.ledgera.model.ReportResult
import app.ledgera.model.ReportSummary
import app.ledgera.model.ReportTagRow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers

class ReportsViewModelTest {
    @Test
    fun endDateWithoutStartShowsInlineFieldError() {
        val viewModel = ReportsViewModel(FakeReportsEngine(), CoroutineScope(Dispatchers.Unconfined))

        viewModel.updatePeriodEnd("01.01.2026")
        viewModel.generate()

        assertEquals("Start date is required when an end date is set", viewModel.state.value.periodStartError)
        assertNull(viewModel.state.value.periodEndError)
        assertNull(viewModel.state.value.error)
    }

    @Test
    fun exportUsesFiltersFromLastGeneratedReport() {
        val engine = FakeReportsEngine()
        val viewModel = ReportsViewModel(engine, CoroutineScope(Dispatchers.Unconfined))
        viewModel.updatePeriodStart("01.01.2026")
        viewModel.updatePeriodEnd("02.01.2026")
        viewModel.generate()
        viewModel.updatePeriodStart("03.01.2026")

        viewModel.export("csv", object : ReportsFileActions {
            override fun saveReportPath(extension: String): String = "report.$extension"
        })

        assertEquals("2026-01-01", engine.exportedFilters?.periodStart)
        assertEquals("2026-01-02", engine.exportedFilters?.periodEnd)
    }
}

private class FakeReportsEngine : ReportsEngine {
    var exportedFilters: ReportFilters? = null

    override suspend fun generateReport(filters: ReportFilters): ReportResult = reportResult(filters)

    override suspend fun exportReportCsv(filters: ReportFilters, path: String): ReportExportResult {
        exportedFilters = filters
        return ReportExportResult(0, path)
    }
}

private fun reportResult(filters: ReportFilters) = ReportResult(
    title = "Transaction statement",
    baseCurrency = "KZT",
    displayCurrency = "KZT",
    filters = filters,
    summary = ReportSummary(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, "Initial balance", ""),
    operations = emptyList<ReportOperationRow>(),
    monthly = emptyList<ReportMonthlyRow>(),
    categories = emptyList<ReportCategoryRow>(),
    tags = emptyList<ReportTagRow>(),
    debts = emptyList<ReportDebtRow>(),
)
