from __future__ import annotations

from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, ValidationError
from kaleta.models.user import User

AuthState = Literal["no_user", "placeholder", "ready"]
PLACEHOLDER_USERNAME = "__placeholder__"


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._hasher = PasswordHasher()

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            self._hasher.verify(password_hash, password)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False

    async def create_user(self, username: str, password: str) -> User:
        user = User(username=username, password_hash=self.hash_password(password))
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_single_user(self) -> User | None:
        result = await self.session.execute(select(User).limit(1))
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def auth_state(self) -> AuthState:
        user = await self.get_single_user()
        if user is None:
            return "no_user"
        if user.username == PLACEHOLDER_USERNAME:
            return "placeholder"
        return "ready"

    async def authenticate(self, username: str, password: str) -> User | None:
        user = await self.get_user_by_username(username)
        if user is None or user.username == PLACEHOLDER_USERNAME:
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        return user

    async def secure_placeholder(self, username: str, password: str) -> User:
        user = await self.get_single_user()
        if user is None or user.username != PLACEHOLDER_USERNAME:
            msg = "No placeholder user to secure"
            raise ValidationError(msg)
        username = username.strip()
        if not username:
            msg = "Username is required"
            raise ValidationError(msg)
        if username == PLACEHOLDER_USERNAME:
            msg = "Choose a different username"
            raise ValidationError(msg)
        existing = await self.get_user_by_username(username)
        if existing is not None and existing.id != user.id:
            msg = "Username already taken"
            raise ConflictError(msg)
        user.username = username
        user.password_hash = self.hash_password(password)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def record_login(self, *, username: str | None, success: bool) -> None:
        from kaleta.db.audit import record_auth_event

        await record_auth_event(
            self.session,
            event="login",
            username=username,
            success=success,
        )

    async def record_logout(self, *, username: str | None) -> None:
        from kaleta.db.audit import record_auth_event

        await record_auth_event(
            self.session,
            event="logout",
            username=username,
            success=True,
        )
