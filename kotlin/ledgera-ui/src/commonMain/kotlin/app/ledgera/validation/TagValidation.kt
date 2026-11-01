package app.ledgera.validation

object TagValidation {
    private const val MaxTagsPerRecord = 3
    private val splitRegex = Regex("[,\\n;]+")

    fun validateTagText(value: String): String? {
        val invalidTags = numericOnlyTags(value)
        if (invalidTags.isNotEmpty()) {
            return "Invalid tag: tags must not contain numbers only (${invalidTags.joinToString(", ") { "\"$it\"" }})"
        }
        return null
    }

    fun normalizeTagName(value: String): String? =
        stripTagNoise(value).lowercase().takeIf { it.isNotEmpty() && !it.all(Char::isDigit) }

    fun parseTagText(value: String): List<String> =
        splitTagText(value)
            .mapNotNull(::normalizeTagName)
            .distinct()
            .take(MaxTagsPerRecord)

    private fun numericOnlyTags(value: String): List<String> =
        splitTagText(value)
            .map { stripTagNoise(it) }
            .filter { it.isNotEmpty() && it.all(Char::isDigit) }
            .distinct()

    private fun splitTagText(value: String): List<String> {
        val trimmed = value.trim()
        if (trimmed.isEmpty()) {
            return emptyList()
        }
        return trimmed.split(splitRegex)
    }

    private fun stripTagNoise(value: String): String =
        value.trim()
            .replace("#", "")
            .filter { char ->
                char.isAsciiLetterOrDigit() || char in 'А'..'Я' || char in 'а'..'я'
            }

    private fun Char.isAsciiLetterOrDigit(): Boolean =
        this in '0'..'9' || this in 'A'..'Z' || this in 'a'..'z'
}
