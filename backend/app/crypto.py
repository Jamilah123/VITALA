"""Field-level encryption for highly sensitive identifiers (national ID, insurance member number).

The key comes from VITALA_FIELD_ENCRYPTION_KEY (a Fernet key). Without a key the
backend refuses to store these fields rather than storing them in clear.
Values are never logged, never returned unmasked, and never sent to the chatbot.
"""

import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken


class EncryptionUnavailable(RuntimeError):
    pass


class FieldCipher:
    def __init__(self, key: str | None):
        self._fernet: Fernet | None = None
        self._hash_key: bytes | None = None
        if key:
            try:
                self._fernet = Fernet(key.encode("ascii"))
            except (ValueError, TypeError) as exc:
                raise ValueError("VITALA_FIELD_ENCRYPTION_KEY is not a valid Fernet key") from exc
            # A separate key for the duplicate-detection hash, derived from the same secret.
            self._hash_key = hmac.new(key.encode("ascii"), b"vitala-identifier-hash-v1", hashlib.sha256).digest()

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def _require(self) -> Fernet:
        if self._fernet is None:
            raise EncryptionUnavailable("Field encryption key is not configured")
        return self._fernet

    def encrypt(self, value: str) -> str:
        return self._require().encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            return self._require().decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise EncryptionUnavailable("Stored value cannot be decrypted with the configured key") from exc

    def identifier_hash(self, value: str) -> str:
        self._require()
        return hmac.new(self._hash_key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def last4(value: str) -> str:
    return value[-4:]


def mask(last_four: str | None, total: int = 10) -> str | None:
    if not last_four:
        return None
    return "*" * max(total - len(last_four), 4) + last_four
