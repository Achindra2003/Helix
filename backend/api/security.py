from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


def hash_password(plain: str) -> str:
    # bcrypt has a 72-byte input limit; truncate defensively.
    return bcrypt.hashpw(plain.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode()[:72], hashed.encode())
    except ValueError:
        return False


def make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_token(token: str) -> str:
    """Return the user_id (sub) or raise jwt.PyJWTError."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    if payload.get("typ"):
        # A reset token is not a session token. Without this check, the link
        # emailed to a forgetful user would function as a bearer credential for
        # its whole lifetime.
        raise jwt.InvalidTokenError("not a session token")
    return payload["sub"]


def _reset_key(pw_hash: str) -> str:
    """Signing key for a reset token: the server secret plus the current hash.

    Mixing the password hash in is what makes the link single-use, with no table
    and no migration. Completing a reset changes `pw_hash`, which changes the
    key, which makes every token minted against the old one unverifiable — the
    link in the inbox stops working the moment it is used, and any older
    outstanding links die with it.

    The hash never leaves the server; it is key material here, not a claim.
    """
    return f"{settings.jwt_secret}:{pw_hash}"


def make_reset_token(user_id: str, pw_hash: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "typ": "pwreset",  # refused by decode_token; see above
        "iat": now,
        "exp": now + timedelta(minutes=settings.password_reset_ttl_minutes),
    }
    return jwt.encode(payload, _reset_key(pw_hash), algorithm=settings.jwt_alg)


def decode_reset_token(token: str, pw_hash: str) -> str:
    """Return the user_id, or raise jwt.PyJWTError.

    Needs the user's *current* hash, so the caller must find the user first —
    the `sub` claim is read without verification for that lookup, then the
    signature is checked properly against the key it implies. Reading an
    unverified claim is safe only because it is used for nothing but the lookup;
    a forged `sub` simply produces a key that fails verification a line later.
    """
    unverified = jwt.decode(token, options={"verify_signature": False})
    if unverified.get("typ") != "pwreset":
        raise jwt.InvalidTokenError("not a reset token")
    payload = jwt.decode(
        token, _reset_key(pw_hash), algorithms=[settings.jwt_alg]
    )
    return payload["sub"]


def peek_token_subject(token: str) -> str:
    """The `sub` of an unverified token, for looking the user up. Never trust it."""
    return jwt.decode(token, options={"verify_signature": False})["sub"]
