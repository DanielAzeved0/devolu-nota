import uuid
from datetime import UTC, datetime

import pytest

from app.core.encryption import (
    EncryptionConfigurationError,
    EncryptionError,
    EncryptionService,
    InvalidEncryptedPayloadError,
    decrypt_secret,
    encrypt_secret,
)
from app.models import Integration
from app.schemas.integrations import IntegrationPublic
from app.services.integration_credentials import (
    SensitiveCredentialError,
    decrypt_integration_credentials,
    encrypt_integration_credentials,
)


def test_encrypt_secret_returns_non_plaintext_payload_and_decrypts_original() -> None:
    secret = "tiny-access-token"

    encrypted = encrypt_secret(secret)
    decrypted = decrypt_secret(encrypted)

    assert encrypted != secret
    assert secret not in encrypted
    assert decrypted == secret


def test_encrypt_secret_is_not_deterministic() -> None:
    secret = "mercado-livre-refresh-token"

    first = encrypt_secret(secret)
    second = encrypt_secret(secret)

    assert first != second
    assert decrypt_secret(first) == secret
    assert decrypt_secret(second) == secret


def test_encrypt_secret_rejects_empty_value() -> None:
    with pytest.raises(EncryptionError, match="cannot be empty"):
        encrypt_secret("")


def test_decrypt_secret_rejects_invalid_payload_without_leaking_secret() -> None:
    secret = "shopee-token"

    with pytest.raises(InvalidEncryptedPayloadError) as exc:
        decrypt_secret(f"invalid-{secret}")

    assert secret not in str(exc.value)


def test_encryption_service_rejects_invalid_key() -> None:
    with pytest.raises(EncryptionConfigurationError, match="Invalid encryption key"):
        EncryptionService("invalid-key")


def test_integration_credentials_are_encrypted_and_recoverable() -> None:
    credentials = {
        "access_token": "tiny-access-token",
        "refresh_token": "tiny-refresh-token",
    }

    encrypted_credentials = encrypt_integration_credentials(credentials)
    decrypted_credentials = decrypt_integration_credentials(encrypted_credentials)

    assert decrypted_credentials == credentials
    assert encrypted_credentials["access_token"] != credentials["access_token"]
    assert encrypted_credentials["refresh_token"] != credentials["refresh_token"]
    assert credentials["access_token"] not in str(encrypted_credentials)
    assert credentials["refresh_token"] not in str(encrypted_credentials)


def test_integration_credentials_reject_unsupported_fields() -> None:
    with pytest.raises(SensitiveCredentialError):
        encrypt_integration_credentials({"public_setting": "not-sensitive"})


def test_integration_public_schema_does_not_expose_credentials() -> None:
    now = datetime.now(UTC)
    integration = Integration(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        provider="TINY",
        status="ACTIVE",
        settings={"sync_interval_minutes": 30},
        encrypted_credentials={"access_token": "encrypted-token"},
        created_at=now,
        updated_at=now,
    )

    payload = IntegrationPublic.model_validate(integration).model_dump()

    assert "encrypted_credentials" not in payload
    assert "access_token" not in str(payload)
    assert "refresh_token" not in str(payload)
    assert payload["settings"] == {"sync_interval_minutes": 30}
