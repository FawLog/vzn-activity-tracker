"""Password hashing and constant-time security helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_SALT_BYTES = 16
SCRYPT_DERIVED_BYTES = 64


def _parse_password_hash(stored: str) -> tuple[bytes, bytes] | None:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
        parameters = (int(n), int(r), int(p))
        salt = bytes.fromhex(salt_hex)
        digest = bytes.fromhex(digest_hex)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None
    if algorithm != "scrypt" or parameters != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
        return None
    if len(salt) != SCRYPT_SALT_BYTES or len(digest) != SCRYPT_DERIVED_BYTES:
        return None
    return salt, digest


def password_hash_is_valid(stored: str) -> bool:
    return _parse_password_hash(stored) is not None


def hash_password(password: str) -> str:
    if len(password) < 14:
        raise ValueError("Administrator password must contain at least 14 characters")
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    parsed = _parse_password_hash(stored)
    if parsed is None:
        return False
    salt, expected_digest = parsed
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    return hmac.compare_digest(derived, expected_digest)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def keyed_identifier(value: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
