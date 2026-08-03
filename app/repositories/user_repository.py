# Saves and retrieves user accounts (both roles) from PostgreSQL.
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.user import User


class UserRepository:

    def get_by_id(self, db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, db: Session, email: str) -> User | None:
        return db.query(User).filter(func.lower(User.email) == email.lower().strip()).first()

    def get_by_username(self, db: Session, username: str) -> User | None:
        return db.query(User).filter(func.lower(User.username) == username.lower().strip()).first()

    def create_user(self, db: Session, username: str, email: str, password_hash: str, role: str) -> User:
        user = User(
            username=username, email=email,
            password_hash=password_hash, role=role, auth_provider="password",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


user_repository = UserRepository()
