"""Security helpers: code generation, IP hashing, key hashing."""

import hashlib
import secrets
import string

from app.core.config import get_settings

settings = get_settings()

CODE_ALPHABET = string.ascii_letters + string.digits


def generate_short_code(length: int | None = None) -> str:
    """Cryptographically random, URL-safe short code."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length or settings.code_length))


def hash_ip(ip: str | None) -> str | None:
    """Salted SHA-256 of the visitor IP — raw addresses are never stored."""
    if not ip:
        return None
    value = f"{settings.ip_hash_salt}:{ip}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def hash_identifier(identifier: str) -> str:
    """Stable pseudonym for rate-limit buckets (keeps raw API keys out of Redis)."""
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:32]
