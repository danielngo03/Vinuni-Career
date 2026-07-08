"""Password hashing using Argon2id (``argon2-cffi``).

Passwords are never stored or logged in plaintext (``docs/SECURITY_PRIVACY.md``).
Argon2id is the maintained, memory-hard default; the verifier transparently
re-hashes when parameters change.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plaintext: str) -> str:
    return _hasher.hash(plaintext)


def verify_password(plaintext: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, plaintext)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False
