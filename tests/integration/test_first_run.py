# SPDX-License-Identifier: AGPL-3.0-or-later
"""First-run setup integration coverage."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kaleta.api import create_api_router
from kaleta.api.errors import register_error_handlers
from kaleta.config import settings, setup_config
from kaleta.services.setup_service import activate_database, current_revision, head_revision


class TestFirstRunSetup:
    @pytest.mark.asyncio
    async def test_recommended_activate_persists_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Covers: KAL-SET-021"""
        home = tmp_path / "home"
        home.mkdir()
        config_dir = home / ".kaleta"
        backup_dir = tmp_path / "backups"
        monkeypatch.setattr(setup_config, "_CONFIG_DIR", config_dir)
        monkeypatch.setattr(setup_config, "_CONFIG_FILE", config_dir / "config.json")
        monkeypatch.setattr(settings, "backup_dir", str(backup_dir))

        db_path = setup_config.recommended_db_path()
        assert db_path == config_dir / "kaleta.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = setup_config.recommended_db_url()

        await activate_database(db_url, name="kaleta")

        assert setup_config.is_configured()
        assert setup_config.get_db_url() == db_url
        assert db_path.is_file()
        assert current_revision(db_url) == head_revision()
        backups = list(backup_dir.glob("kaleta-*.db"))
        assert len(backups) == 1
        assert backups[0].is_file()

    @pytest.mark.asyncio
    async def test_api_returns_setup_required_when_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Covers: KAL-SET-022"""
        monkeypatch.setattr("kaleta.api.deps.is_configured", lambda: False)

        app = FastAPI()
        register_error_handlers(app)
        app.include_router(create_api_router())

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/accounts/")

        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "setup_required"
