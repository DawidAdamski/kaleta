# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import secrets
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.user import User

AuthState = Literal["no_user", "placeholder", "ready"]
PLACEHOLDER_USERNAME = "__placeholder__"
API_BOOTSTRAP_USERNAME = "api"
MIN_PASSWORD_LENGTH = 8


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

    def validate_new_password(self, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            msg = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            raise ValidationError(msg)

    async def create_user(self, username: str, password: str) -> User:
        self.validate_new_password(password)
        user = User(username=username, password_hash=self.hash_password(password))
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def count_users(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

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
        self.validate_new_password(password)
        existing = await self.get_user_by_username(username)
        if existing is not None and existing.id != user.id:
            msg = "Username already taken"
            raise ConflictError(msg)
        user.username = username
        user.password_hash = self.hash_password(password)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def reset_password(self, new_password: str) -> User:
        """Set a new password for the sole real user (CLI forgotten-password path)."""
        self.validate_new_password(new_password)
        count = await self.count_users()
        if count == 0:
            msg = (
                "No user found. Create an account via the first-run bootstrap "
                "(open the app and use Create account)."
            )
            raise NotFoundError(msg)
        if count > 1:
            msg = "Multiple users found. Refusing to reset password in single-user mode."
            raise ConflictError(msg)
        user = await self.get_single_user()
        if user is None or user.username == PLACEHOLDER_USERNAME:
            msg = "No real user account found. Open the app to finish creating your account."
            raise NotFoundError(msg)
        user.password_hash = self.hash_password(new_password)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def ensure_api_bootstrap_user(self) -> User:
        """Ensure a real user exists so ``KALETA_API_TOKEN`` can authenticate.

        Used on ``KALETA_MODE=api`` startup when an env bootstrap token is set.
        Creates (or converts a placeholder into) username ``api`` with a random
        unusable password — login is via bearer only.
        """
        state = await self.auth_state()
        if state == "ready":
            user = await self.get_single_user()
            if user is None:
                msg = "Auth state ready but no user row found"
                raise NotFoundError(msg)
            return user
        locked_password = secrets.token_urlsafe(32)
        if state == "placeholder":
            return await self.secure_placeholder(API_BOOTSTRAP_USERNAME, locked_password)
        return await self.create_user(API_BOOTSTRAP_USERNAME, locked_password)

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
