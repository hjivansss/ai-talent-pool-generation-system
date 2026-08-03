# Auth endpoints. Two register endpoints (recruiter/candidate) writing to
# the same users table with different `role` values; login and /me are
# shared since both roles authenticate identically.
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.services.auth_service import auth_service, get_current_user
from app.schemas.auth_schema import RegisterRequest, LoginRequest, TokenResponse, UserOut
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse)
def register_recruiter(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Recruiter signup."""
    user = auth_service.register(db, payload.username, payload.email, payload.password, role="recruiter")
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/register/candidate", response_model=TokenResponse)
def register_candidate(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Candidate signup — same validation rules, different role stamped."""
    user = auth_service.register(db, payload.username, payload.email, payload.password, role="candidate")
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Shared by both roles — the returned user.role tells you which kind of account it is."""
    user = auth_service.login(db, payload.username_or_email, payload.password)
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    """Protected route — proves a token actually works, for either role."""
    return UserOut.model_validate(current_user)
