# Auth business logic — registration (both roles), login, and the
# dependencies routes use to enforce "must be logged in" and
# "must be this specific role".
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, decode_access_token
from app.repositories.user_repository import user_repository
from app.models.user import User

# Tells Swagger's /docs UI to show the "Authorize" lock icon and lets it
# extract the "Authorization: Bearer <token>" header automatically for us.
bearer_scheme = HTTPBearer()


class AuthService:

    def register(self, db: Session, username: str, email: str, password: str, role: str) -> User:
        if user_repository.get_by_email(db, email):
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
        if user_repository.get_by_username(db, username):
            raise HTTPException(status.HTTP_409_CONFLICT, "This username is already taken.")
        return user_repository.create_user(db, username, email, hash_password(password), role)

    def login(self, db: Session, username_or_email: str, password: str) -> User:
        # Accept either — whichever the person typed. Works for both roles;
        # the returned user.role tells the caller which kind of account it is.
        user = user_repository.get_by_email(db, username_or_email) \
            or user_repository.get_by_username(db, username_or_email)

        # Same error message either way (user not found vs wrong password) —
        # deliberately vague so a login attempt can't be used to check
        # whether a given username/email is registered at all.
        invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username/email or password.")
        if not user:
            raise invalid
        if not verify_password(password, user.password_hash):
            raise invalid
        return user


auth_service = AuthService()


# ── Route protection dependencies ────────────────────────────────────
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Used as `current_user: User = Depends(get_current_user)` on any route
    that should require login, REGARDLESS of role — both recruiters and
    candidates pass this check. Use require_role() instead when a route
    needs to restrict to one specific role.
    """
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.")

    user = user_repository.get_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive.")
    return user


def require_role(*allowed_roles: str):
    """
    Factory — returns a dependency that requires login AND a specific role.
    Usage: current_user: User = Depends(require_role("recruiter"))
    Or for a route either role can hit: Depends(require_role("recruiter", "candidate"))
    (equivalent to plain get_current_user, but explicit about intent).
    """
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This action requires role {allowed_roles}, you are '{current_user.role}'.",
            )
        return current_user
    return checker
