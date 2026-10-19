package app.ledgera.runtime

import com.sun.jna.Memory
import com.sun.jna.Native
import com.sun.jna.Pointer
import com.sun.jna.Library
import com.sun.jna.Structure
import com.sun.jna.WString
import com.sun.jna.ptr.PointerByReference
import com.sun.jna.platform.win32.WinBase
import com.sun.jna.platform.win32.Win32Exception
import java.nio.charset.StandardCharsets

/** Resolves provider secrets without putting them in SQLite or application state. */
object DesktopCredentialStore {
    private const val EXCHANGE_RATE_PROVIDER = "exchange_rate"
    private const val EXCHANGE_RATE_ENV = "LEDGERA_EXCHANGE_RATE_API_KEY"
    private const val LEGACY_EXCHANGE_RATE_ENV = "FINACCOUNTING_EXCHANGE_RATE_API_KEY"
    private const val TARGET_PREFIX = "Ledgera.CurrencyProvider."
    private const val ERROR_NOT_FOUND = 1168

    fun status(providerId: String): String {
        val normalized = normalizeProviderId(providerId)
        if (environmentSecret(normalized).isNotBlank()) return "Environment override"
        if (!isWindows()) return "Secure storage unavailable"
        return runCatching { readWindowsCredential(normalized) }
            .fold(
                onSuccess = { if (it.isNullOrBlank()) "Missing" else "Configured" },
                onFailure = { "Secure storage error: ${it.message ?: "Credential Manager request failed"}" },
            )
    }

    fun resolve(providerId: String): String {
        val normalized = normalizeProviderId(providerId)
        return environmentSecret(normalized).ifBlank {
            if (isWindows()) readWindowsCredential(normalized).orEmpty() else ""
        }
    }

    fun save(providerId: String, secret: String) {
        val normalized = normalizeProviderId(providerId)
        require(secret.isNotBlank()) { "Credential cannot be blank" }
        check(isWindows()) { "Windows secure credential storage is unavailable" }

        val bytes = secret.trim().toByteArray(StandardCharsets.UTF_8)
        val blob = Memory(bytes.size.toLong())
        blob.write(0, bytes, 0, bytes.size)
        val credential = Credential()
        credential.type = CRED_TYPE_GENERIC
        credential.targetName = WString(targetName(normalized))
        credential.CredentialBlobSize = bytes.size
        credential.CredentialBlob = blob
        credential.persist = CRED_PERSIST_LOCAL_MACHINE
        credential.userName = WString(System.getProperty("user.name"))
        credential.write()
        if (!api.CredWriteW(credential, 0)) {
            throw Win32Exception(Native.getLastError())
        }
    }

    private fun environmentSecret(providerId: String): String {
        if (providerId == EXCHANGE_RATE_PROVIDER) {
            return System.getenv(EXCHANGE_RATE_ENV).orEmpty().ifBlank {
                System.getenv(LEGACY_EXCHANGE_RATE_ENV).orEmpty()
            }
        }
        if (!providerId.startsWith("custom:")) return ""
        val slug = providerId.removePrefix("custom:")
            .uppercase()
            .replace(Regex("[^A-Z0-9]"), "_")
        return System.getenv("LEDGERA_CURRENCY_PROVIDER_${slug}_API_KEY").orEmpty()
    }

    private fun readWindowsCredential(providerId: String): String? {
        val reference = PointerByReference()
        if (!api.CredReadW(WString(targetName(providerId)), CRED_TYPE_GENERIC, 0, reference)) {
            val errorCode = Native.getLastError()
            if (errorCode == ERROR_NOT_FOUND) return null
            throw Win32Exception(errorCode)
        }
        val pointer = reference.value ?: return null
        return try {
            val credential = Credential(pointer)
            credential.read()
            val blob = credential.CredentialBlob ?: return null
            blob.getByteArray(0, credential.CredentialBlobSize).toString(StandardCharsets.UTF_8)
        } finally {
            api.CredFree(pointer)
        }
    }

    private fun targetName(providerId: String): String = "$TARGET_PREFIX${normalizeProviderId(providerId)}"

    private fun normalizeProviderId(providerId: String): String {
        val normalized = providerId.trim().lowercase()
        require(
            normalized == EXCHANGE_RATE_PROVIDER ||
                normalized.matches(Regex("custom:[a-z0-9][a-z0-9_-]{1,63}")),
        ) { "Unsupported provider credential: $providerId" }
        return normalized
    }
    private fun isWindows(): Boolean = System.getProperty("os.name").contains("win", ignoreCase = true)

    private val api: Advapi32CredentialApi by lazy {
        Native.load("Advapi32", Advapi32CredentialApi::class.java)
    }

    private interface Advapi32CredentialApi : Library {
        fun CredWriteW(credential: Credential, flags: Int): Boolean
        fun CredReadW(targetName: WString, type: Int, flags: Int, credential: PointerByReference): Boolean
        fun CredFree(credential: Pointer)
    }

    @Structure.FieldOrder(
        "flags",
        "type",
        "targetName",
        "comment",
        "lastWritten",
        "CredentialBlobSize",
        "CredentialBlob",
        "persist",
        "attributeCount",
        "attributes",
        "targetAlias",
        "userName",
    )
    class Credential() : Structure() {
        @JvmField var flags: Int = 0
        @JvmField var type: Int = 0
        @JvmField var targetName: WString? = null
        @JvmField var comment: WString? = null
        @JvmField var lastWritten: WinBase.FILETIME = WinBase.FILETIME()
        @JvmField var CredentialBlobSize: Int = 0
        @JvmField var CredentialBlob: Pointer? = null
        @JvmField var persist: Int = 0
        @JvmField var attributeCount: Int = 0
        @JvmField var attributes: Pointer? = null
        @JvmField var targetAlias: WString? = null
        @JvmField var userName: WString? = null

        constructor(pointer: Pointer) : this() {
            useMemory(pointer)
            read()
        }
    }

    private const val CRED_TYPE_GENERIC = 1
    private const val CRED_PERSIST_LOCAL_MACHINE = 2
}
