from __future__ import annotations

import pytest

import app.runtime.secret_storage as secret_storage
from app.runtime.secret_storage import (
    EXCHANGE_RATE_API_KEY_ACCOUNT,
    LEGACY_SERVICE_NAME,
    SERVICE_NAME,
    SecretStorageUnavailableError,
    delete_exchange_rate_api_key,
    get_exchange_rate_api_key,
    get_secret_storage_status,
    set_exchange_rate_api_key,
)


def test_secret_storage_status_marks_fail_backend_unavailable(monkeypatch) -> None:
    class FailKeyring:
        __module__ = "keyring.backends.fail"

    monkeypatch.setattr(secret_storage, "_keyring_backend", lambda: FailKeyring())

    status = get_secret_storage_status()

    assert status.available is False
    assert status.backend_name == "FailKeyring"


def test_secret_storage_status_marks_nonpositive_priority_backend_unavailable(
    monkeypatch,
) -> None:
    class HeadlessBackend:
        __module__ = "custom.backend"
        priority = 0

    monkeypatch.setattr(secret_storage, "_keyring_backend", lambda: HeadlessBackend())

    status = get_secret_storage_status()

    assert status.available is False
    assert status.backend_name == "HeadlessBackend"


def test_exchange_rate_api_key_reads_legacy_service_when_new_name_is_empty(monkeypatch) -> None:
    class DummyKeyring:
        def get_password(self, service_name: str, account: str) -> str:
            assert account == EXCHANGE_RATE_API_KEY_ACCOUNT
            if service_name == SERVICE_NAME:
                return ""
            if service_name == LEGACY_SERVICE_NAME:
                return "legacy-key"
            return ""

    monkeypatch.setattr(
        secret_storage,
        "get_secret_storage_status",
        lambda: secret_storage.SecretStorageStatus(
            available=True,
            backend_name="DummyKeyring",
            backend_label="OS secure secret storage",
        ),
    )
    monkeypatch.setattr(secret_storage, "keyring", DummyKeyring())

    assert get_exchange_rate_api_key() == "legacy-key"


def test_exchange_rate_api_key_reads_legacy_service_when_status_is_unavailable(
    monkeypatch,
) -> None:
    class DummyKeyring:
        def get_password(self, service_name: str, account: str) -> str:
            assert account == EXCHANGE_RATE_API_KEY_ACCOUNT
            if service_name == SERVICE_NAME:
                return ""
            if service_name == LEGACY_SERVICE_NAME:
                return "legacy-key"
            return ""

    monkeypatch.setattr(
        secret_storage,
        "get_secret_storage_status",
        lambda: secret_storage.SecretStorageStatus(
            available=False,
            backend_name="DummyKeyring",
            backend_label="Secure OS secret storage is unavailable",
        ),
    )
    monkeypatch.setattr(secret_storage, "keyring", DummyKeyring())

    assert get_exchange_rate_api_key() == "legacy-key"


def test_set_exchange_rate_api_key_cleans_up_legacy_service(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None]] = []

    class DummyKeyring:
        def set_password(self, service_name: str, account: str, value: str) -> None:
            calls.append((service_name, account, value))

        def delete_password(self, service_name: str, account: str) -> None:
            calls.append((service_name, account, None))

    monkeypatch.setattr(
        secret_storage,
        "get_secret_storage_status",
        lambda: secret_storage.SecretStorageStatus(
            available=True,
            backend_name="DummyKeyring",
            backend_label="OS secure secret storage",
        ),
    )
    monkeypatch.setattr(secret_storage, "keyring", DummyKeyring())

    set_exchange_rate_api_key("new-key")

    assert calls == [
        (SERVICE_NAME, EXCHANGE_RATE_API_KEY_ACCOUNT, "new-key"),
        (LEGACY_SERVICE_NAME, EXCHANGE_RATE_API_KEY_ACCOUNT, None),
    ]


def test_set_exchange_rate_api_key_raises_when_backend_cannot_store(monkeypatch) -> None:
    class DummyKeyring:
        def set_password(self, service_name: str, account: str, value: str) -> None:
            raise RuntimeError("store failed")

    monkeypatch.setattr(
        secret_storage,
        "get_secret_storage_status",
        lambda: secret_storage.SecretStorageStatus(
            available=True,
            backend_name="DummyKeyring",
            backend_label="OS secure secret storage",
        ),
    )
    monkeypatch.setattr(secret_storage, "keyring", DummyKeyring())

    with pytest.raises(SecretStorageUnavailableError, match="persist"):
        set_exchange_rate_api_key("new-key")


def test_delete_exchange_rate_api_key_ignores_expected_cleanup_failures(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class DummyKeyring:
        def delete_password(self, service_name: str, account: str) -> None:
            calls.append((service_name, account))
            raise RuntimeError("missing")

    monkeypatch.setattr(
        secret_storage,
        "get_secret_storage_status",
        lambda: secret_storage.SecretStorageStatus(
            available=True,
            backend_name="DummyKeyring",
            backend_label="OS secure secret storage",
        ),
    )
    monkeypatch.setattr(secret_storage, "keyring", DummyKeyring())

    delete_exchange_rate_api_key()

    assert calls == [
        (SERVICE_NAME, EXCHANGE_RATE_API_KEY_ACCOUNT),
        (LEGACY_SERVICE_NAME, EXCHANGE_RATE_API_KEY_ACCOUNT),
    ]
