package app.ledgera.reports

interface ReportsFileActions {
    fun saveReportPath(extension: String): String?
}

object NoReportsFileActions : ReportsFileActions {
    override fun saveReportPath(extension: String): String? = null
}
