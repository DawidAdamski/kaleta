# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI session authentication — middleware and session helpers."""

from kaleta.auth.middleware import register_auth_middleware
from kaleta.auth.routes import register_session_routes
from kaleta.auth.session import (
    begin_mfa_challenge,
    clear_session,
    finish_login,
    finish_logout,
    is_authenticated,
    is_mfa_pending,
    login_session,
    logout_session,
    mark_mfa_verified,
    mfa_pending_user,
    mfa_verified_at,
)

__all__ = [
    "begin_mfa_challenge",
    "clear_session",
    "finish_login",
    "finish_logout",
    "is_authenticated",
    "is_mfa_pending",
    "login_session",
    "logout_session",
    "mark_mfa_verified",
    "mfa_pending_user",
    "mfa_verified_at",
    "register_auth_middleware",
    "register_session_routes",
]
