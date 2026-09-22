# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI session authentication — middleware and session helpers."""

from kaleta.auth.middleware import register_auth_middleware
from kaleta.auth.session import (
    begin_mfa_challenge,
    clear_session,
    is_authenticated,
    is_mfa_pending,
    login_session,
    logout_session,
    mark_mfa_verified,
    mfa_pending_user,
    mfa_recently_verified,
)

__all__ = [
    "begin_mfa_challenge",
    "clear_session",
    "is_authenticated",
    "is_mfa_pending",
    "login_session",
    "logout_session",
    "mark_mfa_verified",
    "mfa_pending_user",
    "mfa_recently_verified",
    "register_auth_middleware",
]
