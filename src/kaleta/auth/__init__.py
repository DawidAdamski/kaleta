# SPDX-License-Identifier: AGPL-3.0-or-later
"""UI session authentication — middleware and session helpers."""

from kaleta.auth.middleware import register_auth_middleware
from kaleta.auth.session import clear_session, is_authenticated, login_session, logout_session

__all__ = [
    "clear_session",
    "is_authenticated",
    "login_session",
    "logout_session",
    "register_auth_middleware",
]
