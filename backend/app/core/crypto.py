import base64
import hashlib
import hmac
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


@lru_cache
def _ledger_key() -> bytes:
    return hashlib.sha256(settings.ledger_hmac_secret.encode()).digest()


def ledger_hmac(data: bytes) -> bytes:
    """Keyed hash for the tamper-evident ledger chain. HMAC (not a bare SHA)
    is the point: an attacker who edits a stored row cannot recompute the
    chain forward without this server-held key, so the tamper is detectable."""
    return hmac.new(_ledger_key(), data, hashlib.sha256).digest()
