package app.ledgera.validation

object RateValidation {
    private val positiveRateText = Regex("\\+?(\\d+(\\.\\d*)?|\\.\\d+)")

    fun validatePositiveRate(value: String): String? {
        val normalized = value.trim()
        if (!positiveRateText.matches(normalized)) {
            return "Rate must be a positive number"
        }
        val numeric = normalized.toDoubleOrNull()
        if (numeric == null || !numeric.isFinite()) {
            return "Rate must be a positive number"
        }
        val unsigned = normalized.removePrefix("+")
        val integer = unsigned.substringBefore(".").trimStart('0')
        if (integer.isNotEmpty()) {
            return null
        }
        val fraction = unsigned.substringAfter(".", "")
        val quantizedFraction = fraction.take(6).padEnd(6, '0')
        val hasPositiveQuantizedDigits = quantizedFraction.any { it != '0' }
        val roundsUp = (fraction.getOrNull(6) ?: '0') >= '5'
        return if (hasPositiveQuantizedDigits || roundsUp) null else "Rate must be greater than zero"
    }
}
