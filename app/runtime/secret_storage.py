from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from importlib import import_module
from typing import Any

logger = logging.getLogger(__name__)

keyring: Any = None

try:
    keyring = import_module("keyring")
    keyring_errors = import_module("keyring.errors")
    KeyringError = keyring_errors.KeyringError
    NoKeyringError = keyring_errors.NoKeyringError
except ModuleNotFoundError:  # pragma: no cover - exercised through runtime fallback

    class KeyringError(Exception):
        pass

    class NoKeyringError(KeyringError):
        pass


SERVICE_NAME = "Ledgera"
LEGACY_SERVICE_NAME = "FinAccountingApp"
EXCHANGE_RATE_API_KEY_ACCOUNT = "exchange_rate_api_key"


class SecretStorageUnavailableError(RuntimeError):
    """Raised when secure OS-backed secret storage is unavailable."""


@dataclass(frozen=True)
class SecretStorageStatus:
    available: bool
    backend_name: str
    backend_label: str


def _is_expected_keyring_error(exc: BaseException) -> bool:
    return isinstance(exc, (KeyringError, NoKeyringError, RuntimeError, AttributeError))


def _keyring_backend() -> object | None:
    if keyring is None:
        return None
    try:
        return keyring.get_keyring()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to resolve keyring backend")
        return None


def _backend_is_available(backend: object) -> bool:
    backend_name = type(backend).__name__
    backend_module = type(backend).__module__
    backend_name_lower = backend_name.lower()
    backend_module_lower = backend_module.lower()
    if (
        backend_module_lower.startswith("keyring.backends.fail")
        or "failkeyring" in backend_name_lower
    ):
        return False

    priority = getattr(backend, "priority", None)
    if isinstance(priority, (int, float)) and priority <= 0:
        return False

    return True


def get_secret_storage_status() -> SecretStorageStatus:
    backend = _keyring_backend()
    if backend is None:
        return SecretStorageStatus(
            available=False,
            backend_name="",
            backend_label="Secure OS secret storage is unavailable",
        )

    backend_name = type(backend).__name__
    backend_module = type(backend).__module__
    if not _backend_is_available(backend):
        return SecretStorageStatus(
            available=False,
            backend_name=backend_name,
            backend_label="Secure OS secret storage is unavailable",
        )

    if os.name == "nt" and ("win" in backend_name.lower() or "win" in backend_module.lower()):
        backend_label = "Windows Credential Manager"
    else:
        backend_label = "OS secure secret storage"
    return SecretStorageStatus(
        available=True,
        backend_name=backend_name,
        backend_label=backend_label,
    )


def _require_available_status() -> SecretStorageStatus:
    status = get_secret_storage_status()
    if not status.available:
        raise SecretStorageUnavailableError(
            "Secure API key storage is unavailable on this system. "
            "Install a supported keyring backend or use the environment variable override."
        )
    return status


def _get_password(service_name: str) -> str:
    if keyring is None:
        return ""
    try:
        value = keyring.get_password(service_name, EXCHANGE_RATE_API_KEY_ACCOUNT)
    except (KeyringError, NoKeyringError, RuntimeError, AttributeError):
        logger.exception("Failed to read ExchangeRate API key from secure storage")
        return ""
    return str(value or "").strip()


def _delete_password_quietly(service_name: str, *, log_message: str) -> None:
    if keyring is None:
        return
    try:
        keyring.delete_password(service_name, EXCHANGE_RATE_API_KEY_ACCOUNT)
    except Exception as exc:
        if _is_expected_keyring_error(exc):
            logger.debug(log_message, exc_info=True)
            return
        raise


def get_exchange_rate_api_key() -> str:
    if keyring is None:
        return ""
    return _get_password(SERVICE_NAME) or _get_password(LEGACY_SERVICE_NAME)


def set_exchange_rate_api_key(value: str) -> None:
    normalized = str(value or "").strip()
    _require_available_status()
    if keyring is None:  # pragma: no cover - defensive
        raise SecretStorageUnavailableError("Secure API key storage is unavailable")
    try:
        keyring.set_password(SERVICE_NAME, EXCHANGE_RATE_API_KEY_ACCOUNT, normalized)
    except (KeyringError, NoKeyringError, RuntimeError, AttributeError) as exc:
        raise SecretStorageUnavailableError(
            "Failed to persist the API key in secure OS storage."
        ) from exc
    _delete_password_quietly(
        LEGACY_SERVICE_NAME,
        log_message="Legacy ExchangeRate API key cleanup skipped",
    )


def delete_exchange_rate_api_key() -> None:
    status = get_secret_storage_status()
    if not status.available or keyring is None:
        return
    _delete_password_quietly(
        SERVICE_NAME,
        log_message="ExchangeRate API key cleanup skipped",
    )
    _delete_password_quietly(
        LEGACY_SERVICE_NAME,
        log_message="Legacy ExchangeRate API key cleanup skipped",
    )
