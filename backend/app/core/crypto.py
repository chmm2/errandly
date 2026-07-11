import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import settings


@lru_cache
def _fernet() -> Fernet:
    # Derive a stable 32-byte key from the app secret so we don't manage a
    # second secret; rotating jwt_secret invalidates stored ciphertexts,
    # which is acceptable for short-lived handoff OTPs.
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_str(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt_str(ciphertext: bytes) -> str:
    return _fernet().decrypt(ciphertext).decode()
