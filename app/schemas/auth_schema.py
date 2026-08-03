# Request/response shapes for the auth endpoints.
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime


class RegisterRequest(BaseModel):
    """
    Used by BOTH /auth/register (recruiter) and /auth/register/candidate —
    role is NOT a field here on purpose. Which endpoint you call determines
    the role; a client can't set their own role by passing role="recruiter"
    in the body, since the field doesn't exist for them to set.
    """
    username: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @field_validator("username")
    @classmethod
    def username_min_length(cls, v: str) -> str:
        if len(v.strip()) < 3:
            raise ValueError("Username must be at least 3 characters.")
        return v.strip()


class LoginRequest(BaseModel):
    # Accepts either username or email in the same field — see auth_service.
    # Shared by both roles; the response tells the frontend which role logged in.
    username_or_email: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    auth_provider: str
    created_at: datetime

    class Config:
        from_attributes = True  # lets this build directly from the SQLAlchemy User object


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
