package app.ledgera.bridge

import app.ledgera.engine.AddMandatoryToRecordsRequest as NativeAddMandatoryToRecordsRequest
import app.ledgera.engine.CreateMandatoryTemplateRequest as NativeCreateMandatoryTemplateRequest
import app.ledgera.engine.CreateRecordRequest as NativeCreateRecordRequest
import app.ledgera.engine.CreateDebtRequest as NativeCreateDebtRequest
import app.ledgera.engine.CreateTransferRequest as NativeCreateTransferRequest
import app.ledgera.engine.CreateWalletRequest as NativeCreateWalletRequest
import app.ledgera.engine.LedgeraEngine
import app.ledgera.engine.MandatoryExportResultDto
import app.ledgera.engine.MandatoryImportResultDto
import app.ledgera.engine.OperationExportResultDto
import app.ledgera.engine.OperationImportResultDto
import app.ledgera.engine.RecordFilterDto
import app.ledgera.engine.ReportFiltersDto as NativeReportFiltersDto
import app.ledgera.engine.ReportExportResultDto
import app.ledgera.engine.RegisterDebtPaymentRequest as NativeRegisterDebtPaymentRequest
import app.ledgera.engine.UpdateMandatoryTemplateRequest as NativeUpdateMandatoryTemplateRequest
import app.ledgera.engine.UpdateRecordRequest as NativeUpdateRecordRequest
import app.ledgera.engine.UpdateTransferRequest as NativeUpdateTransferRequest
import app.ledgera.engine.TagColorAssignment as NativeTagColorAssignment
import app.ledgera.model.AddMandatoryToRecordsRequest
import app.ledgera.model.AuditFinding
import app.ledgera.model.CreateDebtRequest
import app.ledgera.model.CreateMandatoryTemplateRequest
import app.ledgera.model.CreateOperationRequest
import app.ledgera.model.CreateTransferRequest
import app.ledgera.model.CreateTransferResult
import app.ledgera.model.CreateWalletRequest
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
import app.ledgera.model.ReportCategoryRow
import app.ledgera.model.ReportDebtRow
import app.ledgera.model.ReportMonthlyRow
import app.ledgera.model.ReportOperationRow
import app.ledgera.model.ReportResult
import app.ledgera.model.ReportExportResult
import app.ledgera.model.ReportSummary
import app.ledgera.model.ReportTagRow
import app.ledgera.model.ReportFilters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class RustEngineAdapter(dbPath: String) : EngineAdapter {
    init {
        NativeLibraryLoader.ensureAvailable()
    }

    private val engine = LedgeraEngine(dbPath)

    init {
        engine.normalizeTagColors()
    }

    override suspend fun status(): EngineStatus = withContext(Dispatchers.IO) {
        engine.engineStatus().let { EngineStatus(it.ok, it.dbPath, it.message) }
    }

    override suspend fun generateReport(filters: ReportFilters): ReportResult = withContext(Dispatchers.IO) {
        engine.generateReport(
            NativeReportFiltersDto(
                walletId = filters.walletId,
                periodStart = filters.periodStart,
                periodEnd = filters.periodEnd,
                category = filters.category,
                tag = filters.tag,
                tagMode = filters.tagMode,
                totalsMode = filters.totalsMode,
                groupByCategory = filters.groupByCategory,
            )
        ).let { dto ->
            ReportResult(
                title = dto.title,
                baseCurrency = dto.baseCurrency,
                displayCurrency = dto.displayCurrency,
                filters = dto.filters.let { value ->
                    ReportFilters(
                        value.walletId,
                        value.periodStart,
                        value.periodEnd,
                        value.category,
                        value.tag,
                        value.tagMode,
                        value.totalsMode,
                        value.groupByCategory,
                    )
                },
                summary = dto.summary.let { value ->
                    ReportSummary(
                        netWorthFixed = value.netWorthFixed,
                        netWorthCurrent = value.netWorthCurrent,
                        initialBalance = value.initialBalance,
                        recordsTotalFixed = value.recordsTotalFixed,
                        recordsTotalCurrent = value.recordsTotalCurrent,
                        finalBalanceFixed = value.finalBalanceFixed,
                        finalBalanceCurrent = value.finalBalanceCurrent,
                        fxDifference = value.fxDifference,
                        recordsCount = value.recordsCount,
                        balanceLabel = value.balanceLabel,
                        activeTag = value.activeTag,
                    )
                },
                operations = dto.operations.map { value -> ReportOperationRow(value.date, value.typeLabel, value.kind, value.category, value.tagsText, value.amountBase, value.amountCurrent, value.description) },
                monthly = dto.monthly.map { value -> ReportMonthlyRow(value.month, value.income, value.expenses) },
                categories = dto.categories.map { value -> ReportCategoryRow(value.category, value.operationsCount, value.totalBase) },
                tags = dto.tags.map { value -> ReportTagRow(value.tag, value.operationsCount, value.totalBase) },
                debts = dto.debts.map { value -> ReportDebtRow(value.contactName, value.kind, value.status, value.createdAt, value.closedAt, value.currency, value.totalAmount, value.remainingAmount, value.settledAmount, value.progressPercent) },
            )
        }
    }

    override suspend fun reportWallets(): List<WalletOption> = listWallets()
    override suspend fun reportCategories(): List<String> =
        (listCategories("income") + listCategories("expense")).distinct().sorted()
    override suspend fun reportTags(): List<String> = listTags()

    override suspend fun exportReportCsv(filters: ReportFilters, path: String): ReportExportResult =
        withContext(Dispatchers.IO) { engine.exportReportCsv(filters.toNative(), path).toModel() }
    override suspend fun exportReportXlsx(filters: ReportFilters, path: String): ReportExportResult =
        withContext(Dispatchers.IO) { engine.exportReportXlsx(filters.toNative(), path).toModel() }
    override suspend fun exportReportPdf(filters: ReportFilters, path: String): ReportExportResult =
        withContext(Dispatchers.IO) { engine.exportReportPdf(filters.toNative(), path).toModel() }

    override suspend fun baseCurrency(): String = withContext(Dispatchers.IO) {
        engine.baseCurrency()
    }

    override suspend fun listRecords(filter: OperationFilter): List<OperationRecord> =
        withContext(Dispatchers.IO) {
            engine.listRecords(
                RecordFilterDto(
                    startDate = filter.startDate,
                    endDate = filter.endDate,
                    walletId = filter.walletId,
                    recordType = filter.recordType,
                )
            ).map(::toOperationRecord)
        }

    override suspend fun getRecord(recordId: Long): OperationRecord? = withContext(Dispatchers.IO) {
        engine.getRecord(recordId)?.let(::toOperationRecord)
    }

    override suspend fun createRecord(request: CreateOperationRequest): OperationRecord =
        withContext(Dispatchers.IO) {
            engine.createRecord(
                NativeCreateRecordRequest(
                    recordType = request.type,
                    date = request.date,
                    walletId = request.walletId,
                    amountOriginal = request.amountOriginal,
                    currency = request.currency,
                    rateAtOperation = request.rateAtOperation,
                    amountBase = request.amountBase,
                    category = request.category,
                    description = request.description,
                    tags = request.tags,
                )
            ).let(::toOperationRecord)
        }

    override suspend fun createRecordWithTagColors(request: CreateOperationRequest): OperationRecord =
        withContext(Dispatchers.IO) {
            engine.createRecordWithTagColors(
                NativeCreateRecordRequest(
                    recordType = request.type,
                    date = request.date,
                    walletId = request.walletId,
                    amountOriginal = request.amountOriginal,
                    currency = request.currency,
                    rateAtOperation = request.rateAtOperation,
                    amountBase = request.amountBase,
                    category = request.category,
                    description = request.description,
                    tags = request.tags,
                ),
                request.tagColors.map { (name, color) ->
                    NativeTagColorAssignment(name = name, color = color)
                },
            ).let(::toOperationRecord)
        }

    override suspend fun updateRecord(recordId: Long, request: UpdateOperationRequest): OperationRecord =
        withContext(Dispatchers.IO) {
            engine.updateRecord(
                recordId,
                NativeUpdateRecordRequest(
                    recordType = request.type,
                    date = request.date,
                    walletId = request.walletId,
                    amountOriginal = request.amountOriginal,
                    currency = request.currency,
                    rateAtOperation = request.rateAtOperation,
                    amountBase = request.amountBase,
                    category = request.category,
                    description = request.description,
                    tags = request.tags,
                )
            ).let(::toOperationRecord)
        }

    override suspend fun updateRecordWithTagColors(
        recordId: Long,
        request: UpdateOperationRequest,
    ): OperationRecord = withContext(Dispatchers.IO) {
        engine.updateRecordWithTagColors(
            recordId,
            NativeUpdateRecordRequest(
                recordType = request.type,
                date = request.date,
                walletId = request.walletId,
                amountOriginal = request.amountOriginal,
                currency = request.currency,
                rateAtOperation = request.rateAtOperation,
                amountBase = request.amountBase,
                category = request.category,
                description = request.description,
                tags = request.tags,
            ),
            request.tagColors.map { (name, color) ->
                NativeTagColorAssignment(name = name, color = color)
            },
        ).let(::toOperationRecord)
    }

    override suspend fun deleteRecord(recordId: Long): Boolean = withContext(Dispatchers.IO) {
        engine.deleteRecord(recordId)
    }

    override suspend fun createTransfer(request: CreateTransferRequest): CreateTransferResult =
        withContext(Dispatchers.IO) {
            engine.createTransfer(
                NativeCreateTransferRequest(
                    fromWalletId = request.fromWalletId,
                    toWalletId = request.toWalletId,
                    date = request.date,
                    amount = request.amount,
                    currency = request.currency,
                    description = request.description,
                    commissionAmount = request.commissionAmount,
                    commissionCurrency = request.commissionCurrency,
                )
            ).let { CreateTransferResult(transferId = it.transferId) }
        }

    override suspend fun getTransfer(transferId: Long): TransferDetails? = withContext(Dispatchers.IO) {
        engine.getTransfer(transferId)?.let(::toTransferDetails)
    }

    override suspend fun updateTransfer(
        transferId: Long,
        request: UpdateTransferRequest,
    ): UpdateTransferResult = withContext(Dispatchers.IO) {
        engine.updateTransfer(
            transferId,
            NativeUpdateTransferRequest(
                fromWalletId = request.fromWalletId,
                toWalletId = request.toWalletId,
                date = request.date,
                amount = request.amount,
                currency = request.currency,
                description = request.description,
            )
        ).let { UpdateTransferResult(transferId = it.transferId) }
    }

    override suspend fun deleteTransfer(transferId: Long): Boolean = withContext(Dispatchers.IO) {
        engine.deleteTransfer(transferId)
    }

    override suspend fun deleteAllOperations(): OperationDeleteResult = withContext(Dispatchers.IO) {
        engine.deleteAllOperations().let {
            OperationDeleteResult(
                deletedRecords = it.deletedRecords,
                deletedTransfers = it.deletedTransfers,
                deletedDebtLinkedRecords = it.deletedDebtLinkedRecords,
                skippedRecords = it.skippedRecords,
            )
        }
    }

    override suspend fun deleteOperationsSelection(
        recordIds: List<Long>,
        transferIds: List<Long>,
    ): OperationDeleteResult = withContext(Dispatchers.IO) {
        engine.deleteOperationsSelection(recordIds, transferIds).let {
            OperationDeleteResult(
                deletedRecords = it.deletedRecords,
                deletedTransfers = it.deletedTransfers,
                deletedDebtLinkedRecords = it.deletedDebtLinkedRecords,
                skippedRecords = it.skippedRecords,
            )
        }
    }

    override suspend fun previewImportRecordsCsv(path: String): OperationImportResult =
        withContext(Dispatchers.IO) {
            engine.previewImportRecordsCsv(path).toModel()
        }

    override suspend fun importRecordsCsv(path: String): OperationImportResult =
        withContext(Dispatchers.IO) {
            engine.importRecordsCsv(path).toModel()
        }

    override suspend fun exportRecordsCsv(path: String): OperationExportResult =
        withContext(Dispatchers.IO) {
            engine.exportRecordsCsv(path).toModel()
        }

    override suspend fun previewImportRecordsXlsx(path: String): OperationImportResult =
        withContext(Dispatchers.IO) {
            engine.previewImportRecordsXlsx(path).toModel()
        }

    override suspend fun importRecordsXlsx(path: String): OperationImportResult =
        withContext(Dispatchers.IO) {
            engine.importRecordsXlsx(path).toModel()
        }

    override suspend fun exportRecordsXlsx(path: String): OperationExportResult =
        withContext(Dispatchers.IO) {
            engine.exportRecordsXlsx(path).toModel()
        }

    override suspend fun listTags(): List<String> = withContext(Dispatchers.IO) {
        engine.listTags()
    }

    override suspend fun listCategories(recordType: String): List<String> = withContext(Dispatchers.IO) {
        engine.listCategories(recordType)
    }

    override suspend fun listRecordDescriptions(recordType: String?): List<String> = withContext(Dispatchers.IO) {
        engine.listRecordDescriptions(recordType)
    }

    override suspend fun operationSuggestions(): OperationSuggestions = withContext(Dispatchers.IO) {
        engine.operationSuggestions().let {
            OperationSuggestions(
                tags = it.tags,
                incomeCategories = it.incomeCategories,
                expenseCategories = it.expenseCategories,
                descriptions = it.descriptions,
                incomeDescriptions = it.incomeDescriptions,
                expenseDescriptions = it.expenseDescriptions,
            )
        }
    }

    override suspend fun listTagColors(): List<TagColor> = withContext(Dispatchers.IO) {
        engine.listTagColors().map { TagColor(name = it.name, color = it.color) }
    }

    override suspend fun tagColorPalette(): List<String> = withContext(Dispatchers.IO) {
        engine.tagColorPalette()
    }

    override suspend fun listWallets(): List<WalletOption> = withContext(Dispatchers.IO) {
        engine.listWallets().filter { it.isActive }.map {
            WalletOption(id = it.id, name = it.name, currency = it.currency)
        }
    }

    override suspend fun walletBalances(): List<WalletOption> = withContext(Dispatchers.IO) {
        engine.walletBalances().map {
            WalletOption(id = it.walletId, name = it.name, currency = it.currency, balance = it.balance)
        }
    }

    override suspend fun listWalletsForSettings(): List<WalletSettingsItem> = withContext(Dispatchers.IO) {
        val balancesById = engine.walletBalances().associateBy { it.walletId }
        engine.listWallets().map { wallet ->
            WalletSettingsItem(
                id = wallet.id,
                name = wallet.name,
                currency = wallet.currency,
                initialBalance = wallet.initialBalance,
                balance = balancesById[wallet.id]?.balance ?: wallet.initialBalance,
                system = wallet.system,
                allowNegative = wallet.allowNegative,
                active = wallet.isActive,
            )
        }
    }

    override suspend fun createWallet(request: CreateWalletRequest): WalletSettingsItem =
        withContext(Dispatchers.IO) {
            val created = engine.createWallet(
                NativeCreateWalletRequest(
                    name = request.name,
                    currency = request.currency,
                    initialBalance = request.initialBalance,
                    allowNegative = request.allowNegative,
                )
            )
            WalletSettingsItem(
                id = created.id,
                name = created.name,
                currency = created.currency,
                initialBalance = created.initialBalance,
                balance = created.initialBalance,
                system = created.system,
                allowNegative = created.allowNegative,
                active = created.isActive,
            )
        }

    override suspend fun deleteWallet(walletId: Long): WalletDeleteResult = withContext(Dispatchers.IO) {
        val result = engine.deleteWallet(walletId)
        WalletDeleteResult(
            walletId = result.walletId,
            action = result.action,
        )
    }

    override suspend fun listDebts(): List<DebtItem> = withContext(Dispatchers.IO) {
        engine.listDebts().map {
            DebtItem(
                id = it.id,
                contactName = it.contactName,
                kind = it.kind,
                totalAmount = it.totalAmount,
                remainingAmount = it.remainingAmount,
                currency = it.currency,
                interestRate = it.interestRate,
                status = it.status,
                createdAt = it.createdAt,
                closedAt = it.closedAt,
            )
        }
    }

    override suspend fun listDebtPayments(debtId: Long): List<DebtPaymentItem> = withContext(Dispatchers.IO) {
        engine.listDebtPayments(debtId).map(::toDebtPaymentItem)
    }

    override suspend fun createDebt(request: CreateDebtRequest): DebtItem = withContext(Dispatchers.IO) {
        engine.createDebt(
            NativeCreateDebtRequest(
                kind = request.kind,
                contactName = request.contactName,
                walletId = request.walletId,
                amount = request.amount,
                currency = request.currency,
                createdAt = request.createdAt,
                description = request.description,
            )
        ).let {
            toDebtItem(it)
        }
    }

    override suspend fun registerDebtPayment(request: RegisterDebtPaymentRequest): DebtPaymentItem =
        withContext(Dispatchers.IO) {
            engine.registerDebtPayment(request.toNative()).let(::toDebtPaymentItem)
        }

    override suspend fun registerDebtWriteOff(request: RegisterDebtPaymentRequest): DebtPaymentItem =
        withContext(Dispatchers.IO) {
            engine.registerDebtWriteOff(request.toNative()).let(::toDebtPaymentItem)
        }

    override suspend fun closeDebt(request: RegisterDebtPaymentRequest): DebtItem = withContext(Dispatchers.IO) {
        engine.closeDebt(request.toNative()).let(::toDebtItem)
    }

    override suspend fun deleteDebt(debtId: Long): Boolean = withContext(Dispatchers.IO) {
        engine.deleteDebt(debtId)
    }

    override suspend fun deleteDebtPayment(paymentId: Long, deleteLinkedRecord: Boolean): DebtItem =
        withContext(Dispatchers.IO) {
            engine.deleteDebtPayment(paymentId, deleteLinkedRecord).let(::toDebtItem)
        }

    override suspend fun listMandatoryTemplates(): List<MandatoryTemplateItem> = withContext(Dispatchers.IO) {
        engine.listMandatoryTemplates().map(::toMandatoryTemplateItem)
    }

    override suspend fun getMandatoryTemplate(templateId: Long): MandatoryTemplateItem? = withContext(Dispatchers.IO) {
        engine.getMandatoryTemplate(templateId)?.let(::toMandatoryTemplateItem)
    }

    override suspend fun createMandatoryTemplate(
        request: CreateMandatoryTemplateRequest,
    ): MandatoryTemplateItem = withContext(Dispatchers.IO) {
        engine.createMandatoryTemplate(
            NativeCreateMandatoryTemplateRequest(
                walletId = request.walletId,
                amountOriginal = request.amountOriginal,
                currency = request.currency,
                rateAtOperation = request.rateAtOperation,
                amountBase = request.amountBase,
                category = request.category,
                description = request.description,
                period = request.period,
                date = request.date,
            )
        ).let(::toMandatoryTemplateItem)
    }

    override suspend fun updateMandatoryTemplate(
        templateId: Long,
        request: UpdateMandatoryTemplateRequest,
    ): MandatoryTemplateItem = withContext(Dispatchers.IO) {
        engine.updateMandatoryTemplate(
            templateId,
            NativeUpdateMandatoryTemplateRequest(
                walletId = request.walletId,
                amountBase = request.amountBase,
                period = request.period,
                date = request.date,
            )
        ).let(::toMandatoryTemplateItem)
    }

    override suspend fun deleteMandatoryTemplate(templateId: Long): Boolean = withContext(Dispatchers.IO) {
        engine.deleteMandatoryTemplate(templateId)
    }

    override suspend fun deleteAllMandatoryTemplates(): Long = withContext(Dispatchers.IO) {
        engine.deleteAllMandatoryTemplates()
    }

    override suspend fun addMandatoryToRecords(
        request: AddMandatoryToRecordsRequest,
    ): OperationRecord = withContext(Dispatchers.IO) {
        engine.addMandatoryToRecords(
            NativeAddMandatoryToRecordsRequest(
                templateId = request.templateId,
                date = request.date,
                walletId = request.walletId,
            )
        ).let(::toOperationRecord)
    }

    override suspend fun applyMandatoryAutoPayments(today: String): MandatoryAutoPayResult =
        withContext(Dispatchers.IO) {
            engine.applyMandatoryAutoPayments(today).let { result ->
                MandatoryAutoPayResult(
                    createdRecords = result.createdRecords.map(::toOperationRecord),
                )
            }
        }

    override suspend fun previewImportMandatoryCsv(path: String): MandatoryImportResult =
        withContext(Dispatchers.IO) {
            engine.previewImportMandatoryCsv(path).toModel()
        }

    override suspend fun importMandatoryCsv(path: String): MandatoryImportResult =
        withContext(Dispatchers.IO) {
            engine.importMandatoryCsv(path).toModel()
        }

    override suspend fun exportMandatoryCsv(path: String): MandatoryExportResult =
        withContext(Dispatchers.IO) {
            engine.exportMandatoryCsv(path).toModel()
        }

    override suspend fun previewImportMandatoryXlsx(path: String): MandatoryImportResult =
        withContext(Dispatchers.IO) {
            engine.previewImportMandatoryXlsx(path).toModel()
        }

    override suspend fun importMandatoryXlsx(path: String): MandatoryImportResult =
        withContext(Dispatchers.IO) {
            engine.importMandatoryXlsx(path).toModel()
        }

    override suspend fun exportMandatoryXlsx(path: String): MandatoryExportResult =
        withContext(Dispatchers.IO) {
            engine.exportMandatoryXlsx(path).toModel()
        }

    override suspend fun runAudit(): List<AuditFinding> = withContext(Dispatchers.IO) {
        engine.auditRun().map {
            AuditFinding(
                check = it.check,
                severity = it.severity,
                message = it.message,
                entity = it.entity,
            )
        }
    }

    private fun toOperationRecord(record: app.ledgera.engine.RecordDto): OperationRecord =
        OperationRecord(
            id = record.id,
            type = record.recordType,
            date = record.date,
            walletId = record.walletId,
            transferId = record.transferId,
            relatedDebtId = record.relatedDebtId,
            amountOriginal = record.amountOriginal,
            currency = record.currency,
            rateAtOperation = record.rateAtOperation,
            amountBase = record.amountBase,
            category = record.category,
            description = record.description,
            tags = record.tags,
        )

    private fun toTransferDetails(transfer: app.ledgera.engine.TransferDto): TransferDetails =
        TransferDetails(
            id = transfer.id,
            fromWalletId = transfer.fromWalletId,
            toWalletId = transfer.toWalletId,
            date = transfer.date,
            amountOriginal = transfer.amountOriginal,
            currency = transfer.currency,
            rateAtOperation = transfer.rateAtOperation,
            amountBase = transfer.amountBase,
            description = transfer.description,
        )

    private fun toDebtItem(debt: app.ledgera.engine.DebtDto): DebtItem =
        DebtItem(
            id = debt.id,
            contactName = debt.contactName,
            kind = debt.kind,
            totalAmount = debt.totalAmount,
            remainingAmount = debt.remainingAmount,
            currency = debt.currency,
            interestRate = debt.interestRate,
            status = debt.status,
            createdAt = debt.createdAt,
            closedAt = debt.closedAt,
        )

    private fun toDebtPaymentItem(payment: app.ledgera.engine.DebtPaymentDto): DebtPaymentItem =
        DebtPaymentItem(
            id = payment.id,
            debtId = payment.debtId,
            recordId = payment.recordId,
            operationType = payment.operationType,
            principalPaid = payment.principalPaid,
            isWriteOff = payment.isWriteOff,
            paymentDate = payment.paymentDate,
        )

    private fun toMandatoryTemplateItem(template: app.ledgera.engine.MandatoryTemplateDto): MandatoryTemplateItem =
        MandatoryTemplateItem(
            id = template.id,
            walletId = template.walletId,
            amountOriginal = template.amountOriginal,
            currency = template.currency,
            rateAtOperation = template.rateAtOperation,
            amountBase = template.amountBase,
            category = template.category,
            description = template.description,
            period = template.period,
            date = template.date,
            autoPay = template.autoPay,
        )

    private fun RegisterDebtPaymentRequest.toNative(): NativeRegisterDebtPaymentRequest =
        NativeRegisterDebtPaymentRequest(
            debtId = debtId,
            walletId = walletId,
            amount = amount,
            paymentDate = paymentDate,
            description = description,
        )

    private fun OperationImportResultDto.toModel(): OperationImportResult =
        OperationImportResult(
            imported = imported,
            skipped = skipped,
            errors = errors,
            dryRun = dryRun,
            blockingErrors = blockingErrors,
        )

    private fun OperationExportResultDto.toModel(): OperationExportResult =
        OperationExportResult(exportedRows = exportedRows, path = path)

    private fun MandatoryImportResultDto.toModel(): MandatoryImportResult =
        MandatoryImportResult(
            imported = imported,
            skipped = skipped,
            errors = errors,
            dryRun = dryRun,
            blockingErrors = blockingErrors,
        )

    private fun MandatoryExportResultDto.toModel(): MandatoryExportResult =
        MandatoryExportResult(exportedRows = exportedRows, path = path)
}

private fun ReportFilters.toNative() = NativeReportFiltersDto(
    walletId = walletId,
    periodStart = periodStart,
    periodEnd = periodEnd,
    category = category,
    tag = tag,
    tagMode = tagMode,
    totalsMode = totalsMode,
    groupByCategory = groupByCategory,
)

private fun ReportExportResultDto.toModel() = ReportExportResult(exportedRows, path)
