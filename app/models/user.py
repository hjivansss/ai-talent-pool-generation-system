# Stores BOTH recruiter and candidate accounts in one table, distinguished
# by `role`. They share the exact same login mechanics (email+password,
# same JWT shape) — what differs is what each role is allowed to do, which
# is enforced by the require_role dependency in auth_service.py, not by
# having separate tables.
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    username       = Column(String(100), unique=True, nullable=False, index=True)
    email          = Column(String(255), unique=True, nullable=False, index=True)
    password_hash  = Column(String(255), nullable=False)

    # "recruiter" | "candidate" — checked by require_role(), see auth_service.py
    role           = Column(String(20), nullable=False, index=True)

    auth_provider  = Column(String(20), nullable=False, default="password")
    is_active      = Column(Boolean, default=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
