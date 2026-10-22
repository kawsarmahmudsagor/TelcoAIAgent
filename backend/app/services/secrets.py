"""Reversible encryption for secrets saved from the dashboard (the agent's LLM
API key), which have to be decrypted again at call time -- unlike the admin
password, they can't be a hash.

Keyed by SETTINGS_ENCRYPTION_KEY (a Fernet key). There is no key-rotation path:
changing the key makes previously saved secrets undecryptable, and callers then
fall back to the env key."""

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class EncryptionKeyMissing(RuntimeError):
    """SETTINGS_ENCRYPTION_KEY is unset or not a valid Fernet key."""


def _fernet() -> Fernet:
    key = get_settings().settings_encryption_key.strip()
    if not key:
        raise EncryptionKeyMissing("SETTINGS_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise EncryptionKeyMissing("SETTINGS_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encryption_available() -> bool:
    try:
        _fernet()
    except EncryptionKeyMissing:
        return False
    return True


def encrypt_secret(raw: str) -> str:
    """Returns an opaque token, never the plaintext. Raises EncryptionKeyMissing."""
    return _fernet().encrypt(raw.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str | None:
    """Returns None (rather than raising) when the token can't be decrypted --
    missing/rotated key or a corrupted value -- so callers treat it like "no key
    saved" and fall back to the env key."""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (EncryptionKeyMissing, InvalidToken, ValueError):
        return None
