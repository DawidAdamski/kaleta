"""Unit tests for AuthService password hashing and login flows."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.user import User
from kaleta.services.auth_service import PLACEHOLDER_USERNAME, AuthService


@pytest.fixture
def auth(session: AsyncSession) -> AuthService:
    return AuthService(session)


class TestAuthServicePasswordHashing:
    def test_hash_password_returns_argon2_string(self, auth: AuthService) -> None:
        hashed = auth.hash_password("secret-pass")
        assert hashed.startswith("$argon2")

    def test_verify_password_accepts_correct_password(self, auth: AuthService) -> None:
        password = "my-secure-password"
        hashed = auth.hash_password(password)
        assert auth.verify_password(password, hashed) is True

    def test_verify_password_rejects_wrong_password(self, auth: AuthService) -> None:
        hashed = auth.hash_password("correct")
        assert auth.verify_password("wrong", hashed) is False

    def test_verify_password_rejects_invalid_hash(self, auth: AuthService) -> None:
        assert auth.verify_password("anything", "not-a-valid-hash") is False

    def test_same_password_produces_different_hashes(self, auth: AuthService) -> None:
        password = "repeatable"
        assert auth.hash_password(password) != auth.hash_password(password)


class TestAuthServiceAccountLifecycle:
    @pytest.mark.asyncio
    async def test_auth_state_no_user(self, auth: AuthService) -> None:
        assert await auth.auth_state() == "no_user"

    @pytest.mark.asyncio
    async def test_create_user_and_authenticate(self, auth: AuthService) -> None:
        await auth.create_user("alice", "password-one")
        assert await auth.auth_state() == "ready"
        user = await auth.authenticate("alice", "password-one")
        assert user is not None
        assert user.username == "alice"

    @pytest.mark.asyncio
    async def test_authenticate_rejects_wrong_password(self, auth: AuthService) -> None:
        await auth.create_user("alice", "password-one")
        assert await auth.authenticate("alice", "wrong") is None

    @pytest.mark.asyncio
    async def test_authenticate_rejects_placeholder_user(self, auth: AuthService) -> None:
        auth.session.add(
            User(
                username=PLACEHOLDER_USERNAME,
                password_hash=auth.hash_password("not-used"),
            )
        )
        await auth.session.commit()
        assert await auth.auth_state() == "placeholder"
        assert await auth.authenticate(PLACEHOLDER_USERNAME, "not-used") is None

    @pytest.mark.asyncio
    async def test_secure_placeholder_updates_credentials(self, auth: AuthService) -> None:
        auth.session.add(
            User(
                username=PLACEHOLDER_USERNAME,
                password_hash=auth.hash_password("not-used"),
            )
        )
        await auth.session.commit()
        user = await auth.secure_placeholder("owner", "new-password-123")
        assert user.username == "owner"
        assert await auth.auth_state() == "ready"
        assert await auth.authenticate("owner", "new-password-123") is not None
