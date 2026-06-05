import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


class EncryptionError(ValueError):
    pass


class EncryptionConfigurationError(ValueError):
    pass


class InvalidEncryptedPayloadError(EncryptionError):
    pass


class EncryptionService:
    def __init__(self, key: str) -> None:
        try:
            raw_key = base64.urlsafe_b64decode(key)
        except (binascii.Error, ValueError) as exc:
            raise EncryptionConfigurationError("Invalid encryption key") from exc

        if len(raw_key) != 32:
            raise EncryptionConfigurationError("Invalid encryption key")

        self._aesgcm = AESGCM(raw_key)

    def encrypt(self, plain_text: str) -> str:
        if not plain_text:
            raise EncryptionError("Secret value cannot be empty")

        nonce = os.urandom(12)
        cipher_text = self._aesgcm.encrypt(nonce, plain_text.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + cipher_text).decode("utf-8")

    def decrypt(self, encrypted_text: str) -> str:
        if not encrypted_text:
            raise InvalidEncryptedPayloadError("Invalid encrypted payload")

        try:
            payload = base64.urlsafe_b64decode(encrypted_text)
        except (binascii.Error, ValueError) as exc:
            raise InvalidEncryptedPayloadError("Invalid encrypted payload") from exc

        if len(payload) <= 12:
            raise InvalidEncryptedPayloadError("Invalid encrypted payload")

        nonce = payload[:12]
        cipher_text = payload[12:]

        try:
            return self._aesgcm.decrypt(nonce, cipher_text, None).decode("utf-8")
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise InvalidEncryptedPayloadError("Invalid encrypted payload") from exc


def get_encryption_service() -> EncryptionService:
    settings = get_settings()
    return EncryptionService(settings.encryption_key)


def encrypt_secret(value: str) -> str:
    return get_encryption_service().encrypt(value)


def decrypt_secret(encrypted_value: str) -> str:
    return get_encryption_service().decrypt(encrypted_value)
