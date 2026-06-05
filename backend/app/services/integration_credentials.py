from collections.abc import Mapping

from app.core.encryption import decrypt_secret, encrypt_secret

SENSITIVE_CREDENTIAL_FIELDS = frozenset({"access_token", "refresh_token", "api_token", "client_secret"})


class SensitiveCredentialError(ValueError):
    pass


def encrypt_integration_credentials(credentials: Mapping[str, str]) -> dict[str, str]:
    encrypted_credentials: dict[str, str] = {}

    for key, value in credentials.items():
        if key not in SENSITIVE_CREDENTIAL_FIELDS:
            raise SensitiveCredentialError("Unsupported sensitive credential field")
        encrypted_credentials[key] = encrypt_secret(value)

    return encrypted_credentials


def decrypt_integration_credentials(encrypted_credentials: Mapping[str, str]) -> dict[str, str]:
    decrypted_credentials: dict[str, str] = {}

    for key, value in encrypted_credentials.items():
        if key not in SENSITIVE_CREDENTIAL_FIELDS:
            raise SensitiveCredentialError("Unsupported sensitive credential field")
        decrypted_credentials[key] = decrypt_secret(value)

    return decrypted_credentials
