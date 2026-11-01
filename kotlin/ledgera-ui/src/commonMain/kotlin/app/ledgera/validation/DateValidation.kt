package app.ledgera.validation

data class LedgerDate(
    val year: Int,
    val month: Int,
    val day: Int,
) : Comparable<LedgerDate> {
    override fun compareTo(other: LedgerDate): Int =
        when {
            year != other.year -> year.compareTo(other.year)
            month != other.month -> month.compareTo(other.month)
            else -> day.compareTo(other.day)
        }
}

expect fun currentLedgerDate(): LedgerDate

expect fun currentUtcTimestamp(): String

object DateValidation {
    fun validateYmdNotFuture(value: String, today: LedgerDate = currentLedgerDate()): String? {
        val parsed = parseYmd(value) ?: return "Date must use a valid YYYY-MM-DD value"
        return if (parsed > today) "Date cannot be in the future" else null
    }

    fun validateDmyNotFuture(value: String, today: LedgerDate = currentLedgerDate()): String? {
        val parsed = parseDmyStrict(value.trim()) ?: return "Date must use a valid DD.MM.YYYY value"
        return if (parsed > today) "Date cannot be in the future" else null
    }

    fun validateGuiNotFuture(value: String, today: LedgerDate = currentLedgerDate()): String? {
        val parsed = parseGuiDate(value.trim()) ?: return "Date must use a valid date"
        return if (parsed > today) "Date cannot be in the future" else null
    }

    fun validateOptionalDmy(value: String): String? {
        val normalized = value.trim()
        if (normalized.isEmpty()) {
            return null
        }
        return if (parseDmyStrict(normalized) == null) {
            "Date must use a valid DD.MM.YYYY value"
        } else {
            null
        }
    }

    fun parseYmd(value: String): LedgerDate? {
        if (!Regex("\\d{4}-\\d{2}-\\d{2}").matches(value)) {
            return null
        }
        val year = value.substring(0, 4).toInt()
        val month = value.substring(5, 7).toInt()
        val day = value.substring(8, 10).toInt()
        if (month !in 1..12) {
            return null
        }
        if (day !in 1..daysInMonth(year, month)) {
            return null
        }
        if (year < UnixEpochYear) {
            return null
        }
        return LedgerDate(year = year, month = month, day = day)
    }

    fun parseDmyStrict(value: String): LedgerDate? {
        if (!Regex("\\d{2}\\.\\d{2}\\.\\d{4}").matches(value)) {
            return null
        }
        val day = value.substring(0, 2).toInt()
        val month = value.substring(3, 5).toInt()
        val year = value.substring(6, 10).toInt()
        if (month !in 1..12) {
            return null
        }
        if (day !in 1..daysInMonth(year, month)) {
            return null
        }
        if (year < UnixEpochYear) {
            return null
        }
        return LedgerDate(year = year, month = month, day = day)
    }

    fun parseGuiDate(value: String): LedgerDate? =
        parseDmyStrict(value.trim()) ?: parseYmd(value.trim())

    fun formatYmdToDmy(value: String): String =
        parseYmd(value.trim())?.let(::formatDmy).orEmpty()

    fun formatDmyToYmd(value: String): String? =
        parseDmyStrict(value.trim())?.let(::formatYmd)

    fun formatGuiDateToYmd(value: String): String? =
        parseGuiDate(value.trim())?.let(::formatYmd)

    fun formatYmd(date: LedgerDate): String =
        "%04d-%02d-%02d".format(date.year, date.month, date.day)

    fun formatDmy(date: LedgerDate): String =
        "%02d.%02d.%04d".format(date.day, date.month, date.year)

    fun sanitizeDmyInput(value: String): String =
        value.lineSequence()
            .firstOrNull()
            .orEmpty()
            .filter { it.isDigit() || it == '.' }
            .take(10)

    fun toEpochMillisUtc(date: LedgerDate): Long =
        daysFromCivil(date.year, date.month, date.day) * MillisPerDay

    fun fromEpochMillisUtc(value: Long): LedgerDate =
        civilFromDays(value.floorDiv(MillisPerDay))

    private fun daysInMonth(year: Int, month: Int): Int =
        when (month) {
            1, 3, 5, 7, 8, 10, 12 -> 31
            4, 6, 9, 11 -> 30
            2 -> if (isLeapYear(year)) 29 else 28
            else -> 0
        }

    private fun isLeapYear(year: Int): Boolean =
        year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)

    private fun daysFromCivil(year: Int, month: Int, day: Int): Long {
        var y = year.toLong()
        val m = month.toLong()
        y -= if (m <= 2) 1 else 0
        val era = y.floorDiv(400)
        val yoe = y - era * 400
        val mp = m + if (m > 2) -3 else 9
        val doy = (153 * mp + 2) / 5 + day.toLong() - 1
        val doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
        return era * 146097 + doe - DaysToUnixEpoch
    }

    private fun civilFromDays(days: Long): LedgerDate {
        val z = days + DaysToUnixEpoch
        val era = z.floorDiv(146097)
        val doe = z - era * 146097
        val yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365
        var year = yoe + era * 400
        val doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
        val mp = (5 * doy + 2) / 153
        val day = doy - (153 * mp + 2) / 5 + 1
        val month = mp + if (mp < 10) 3 else -9
        year += if (month <= 2) 1 else 0
        return LedgerDate(year = year.toInt(), month = month.toInt(), day = day.toInt())
    }

    private fun Long.floorDiv(other: Long): Long {
        var result = this / other
        if ((this xor other) < 0 && result * other != this) {
            result--
        }
        return result
    }

    private const val MillisPerDay = 86_400_000L
    private const val DaysToUnixEpoch = 719_468L
    private const val UnixEpochYear = 1970
}
