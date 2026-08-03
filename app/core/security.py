# Password hashing and JWT creation/verification.
#
# Password hashing: we NEVER store the actual password anywhere, not even
# encrypted. bcrypt is a one-way hash — given a hash, there's no way to get
# the original password back out, only to check "does this candidate
# password produce this same hash". bcrypt also automatically includes a
# random "salt" per password, so two users with the same password get
# completely different stored hashes.
#
# JWT (JSON Web Token): after login, instead of the server remembering
# "this session ID is logged in" (a stateful session), we hand the client a
# signed token containing their user ID + role and an expiry time. The
# client sends it back on every request in the Authorization header. The
# server verifies the signature (proving WE issued it and it wasn't
# tampered with) and reads the user ID/role straight out of it — no
# database lookup needed just to check "is this session valid".

import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

from app.core.config import settings


def hash_password(plain_password: str) -> str:
    """One-way hash. Store this, never the plain password."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Used at login: checks a candidate password against the stored hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: int, role: str, extra_claims: dict | None = None) -> str:
    """
    Builds a signed JWT. `sub` (subject) is the standard JWT claim name for
    "who is this token about" — the user's DB id. `role` is our own custom
    claim (not a JWT standard, just a field we chose to include) — it lets
    get_current_user/require_role check permissions without a DB lookup for
    the role check specifically. `exp` (expiry) is a standard claim JWT
    libraries check automatically.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Verifies signature + expiry and returns the payload. Raises
    jwt.PyJWTError (caught by the caller) if the token is invalid, expired,
    or was signed with a different secret (i.e. not issued by us).
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
