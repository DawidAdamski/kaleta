# SPDX-License-Identifier: AGPL-3.0-or-later
"""A stand-in for Supabase Auth (GoTrue) — the e2e "verification stub".

Speaks the handful of GoTrue endpoints ``SupabaseAuthProvider`` calls, in their
shapes, and keeps its users in memory. Sign-up leaves the address unconfirmed
and "sends" a verification link that the test reads from ``/_test/inbox``
instead of a mailbox; following it confirms the address and redirects back to
Kaleta, as GoTrue does. Nothing here is a real credential check worth the name.
"""

from __future__ import annotations

import base64
import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response


def _jwt(claims: dict[str, Any]) -> str:
    def _part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{_part({'alg': 'HS256', 'typ': 'JWT'})}.{_part(claims)}.ZmFrZQ"


@dataclass
class _User:
    id: str
    email: str
    password: str
    confirmed: bool = False


@dataclass
class FakeGoTrue:
    base_url: str
    users: dict[str, _User] = field(default_factory=dict)
    #: e-mail → the last link "sent" to it.
    inbox: dict[str, str] = field(default_factory=dict)
    _tokens: dict[str, str] = field(default_factory=dict)
    #: recovery token hash → e-mail; access token → e-mail.
    _recovery: dict[str, str] = field(default_factory=dict)
    _sessions: dict[str, str] = field(default_factory=dict)

    def app(self) -> FastAPI:
        app = FastAPI()

        def _user_json(user: _User) -> dict[str, Any]:
            return {
                "id": user.id,
                "aud": "authenticated",
                "email": user.email,
                "email_confirmed_at": "2026-09-30T10:00:00Z" if user.confirmed else None,
            }

        @app.post("/auth/v1/signup")
        async def signup(request: Request) -> JSONResponse:
            body = await request.json()
            email = str(body["email"]).strip().lower()
            if email in self.users:
                return JSONResponse(
                    {"code": 422, "error_code": "user_already_exists", "msg": "exists"}, 422
                )
            user = _User(id=str(uuid.uuid4()), email=email, password=str(body["password"]))
            self.users[email] = user
            token = secrets.token_urlsafe(16)
            self._tokens[token] = email
            redirect_to = request.query_params.get("redirect_to", "")
            self.inbox[email] = (
                f"{self.base_url}/auth/v1/verify?token={token}&type=signup&redirect_to={redirect_to}"
            )
            return JSONResponse(_user_json(user))

        @app.get("/auth/v1/verify")
        async def verify(token: str, redirect_to: str = "") -> Response:
            email = self._tokens.pop(token, None)
            if email is None:
                return JSONResponse({"code": 403, "error_code": "otp_expired"}, 403)
            self.users[email].confirmed = True
            return RedirectResponse(redirect_to or "/", status_code=303)

        @app.post("/auth/v1/token")
        async def token(request: Request) -> JSONResponse:
            body = await request.json()
            user = self.users.get(str(body["email"]).strip().lower())
            if user is None or not secrets.compare_digest(user.password, str(body["password"])):
                return JSONResponse(
                    {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid"}, 400
                )
            if not user.confirmed:
                return JSONResponse(
                    {"code": 400, "error_code": "email_not_confirmed", "msg": "Not confirmed"},
                    400,
                )
            return JSONResponse(_session(user))

        def _session(user: _User) -> dict[str, Any]:
            claims = {
                "sub": user.id,
                "email": user.email,
                "exp": int(time.time()) + 3600,
                "jti": secrets.token_hex(4),
            }
            access_token = _jwt(claims)
            self._sessions[access_token] = user.email
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_token": secrets.token_urlsafe(8),
                "user": _user_json(user),
            }

        @app.post("/auth/v1/verify")
        async def verify_recovery(request: Request) -> JSONResponse:
            body = await request.json()
            email = self._recovery.pop(str(body.get("token_hash", "")), None)
            if body.get("type") != "recovery" or email is None:
                return JSONResponse({"code": 403, "error_code": "otp_expired"}, 403)
            return JSONResponse(_session(self.users[email]))

        @app.put("/auth/v1/user")
        async def update_user(request: Request) -> JSONResponse:
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            email = self._sessions.get(token)
            if email is None:
                return JSONResponse({"code": 401, "error_code": "bad_jwt"}, 401)
            body = await request.json()
            self.users[email].password = str(body["password"])
            return JSONResponse(_user_json(self.users[email]))

        @app.post("/auth/v1/logout")
        async def logout() -> Response:
            return Response(status_code=204)

        @app.post("/auth/v1/recover")
        async def recover(request: Request) -> JSONResponse:
            body = await request.json()
            email = str(body["email"]).strip().lower()
            if email in self.users:
                # What the Supabase "Reset password" template in
                # docs/deployment.md sends: Kaleta's page with the token hash.
                token_hash = secrets.token_urlsafe(16)
                self._recovery[token_hash] = email
                redirect_to = request.query_params.get("redirect_to", "")
                self.inbox[email] = f"{redirect_to}?token_hash={token_hash}"
            return JSONResponse({})

        @app.get("/_test/inbox")
        async def inbox(email: str) -> JSONResponse:
            link = self.inbox.get(email.strip().lower())
            return JSONResponse({"link": link}, 200 if link else 404)

        return app


class FakeGoTrueServer:
    """Runs a ``FakeGoTrue`` on a port in a background thread."""

    def __init__(self, port: int) -> None:
        self.base_url = f"http://127.0.0.1:{port}"
        self.gotrue = FakeGoTrue(base_url=self.base_url)
        config = uvicorn.Config(self.gotrue.app(), host="127.0.0.1", port=port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def __enter__(self) -> FakeGoTrueServer:
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            if time.monotonic() > deadline:
                msg = "fake GoTrue did not start"
                raise RuntimeError(msg)
            time.sleep(0.05)
        return self

    def __exit__(self, *_exc: object) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
