package app.ledgera.validation

object MoneyValidation {
    fun validatePositiveAmount(value: String): String? =
        if (isPositiveMoneyAmount(value)) null else "Amount must be a positive number"

    fun validateNonNegativeAmount(value: String): String? =
        if (isNonNegativeMoneyAmount(value)) null else "Amount must be zero or a positive number"

    fun isPositiveMoneyAmount(value: String): Boolean {
        val normalized = value.trim()
        if (!isUnsignedMoneyText(normalized)) {
            return false
        }
        val unsigned = normalized.removePrefix("+")
        return roundedCents(unsigned)?.let { it > 0L } == true
    }

    fun isNonNegativeMoneyAmount(value: String): Boolean {
        val normalized = value.trim()
        if (!isUnsignedMoneyText(normalized)) {
            return false
        }
        return roundedCents(normalized.removePrefix("+")) != null
    }

    private fun isUnsignedMoneyText(value: String): Boolean =
        Regex("\\+?(\\d+(\\.\\d*)?|\\.\\d+)").matches(value)

    private fun roundedCents(unsigned: String): Long? {
        val integerPart = unsigned.substringBefore(".")
        var minorUnits = 0L
        for (digit in integerPart) {
            val value = digit - '0'
            if (minorUnits > (Long.MAX_VALUE - value) / 10L) {
                return null
            }
            minorUnits = minorUnits * 10L + value
        }
        if (minorUnits > Long.MAX_VALUE / 100L) {
            return null
        }
        minorUnits *= 100L
        val fractionalPart = unsigned.substringAfter(".", "")
        val centDigits = fractionalPart.take(2).padEnd(2, '0')
        val cents = centDigits.toInt()
        if (minorUnits > Long.MAX_VALUE - cents) {
            return null
        }
        minorUnits += cents
        if ((fractionalPart.getOrNull(2) ?: '0') >= '5') {
            if (minorUnits == Long.MAX_VALUE) {
                return null
            }
            minorUnits++
        }
        return minorUnits
    }
}
