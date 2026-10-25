# SPDX-License-Identifier: AGPL-3.0-or-later
"""Institution logos live in the database, encrypted, not on the pod filesystem.

The bug this guards: logos were files under ``~/.kaleta/logos`` served at
``/logos/..``; on a redeploy that directory is wiped while the DB path
survives, so the avatar renders a broken image. Now the bytes are stored in
the family's own schema (base64 inside an ``EncryptedText`` column) and served
from a route — so they outlive any restart and ride the backup.

Covers: KAL-INS-010
"""

from __future__ import annotations

import base64

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.schemas.institution import InstitutionCreate, InstitutionType
from kaleta.services.institution_service import MAX_LOGO_BYTES, InstitutionService

# A 1x1 transparent PNG — the scenario's "uploaded logo", pinned as a literal.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _make_institution(session: AsyncSession, name: str = "Revolut") -> int:
    inst = await InstitutionService(session).create(
        InstitutionCreate(name=name, type=InstitutionType.FINTECH)
    )
    return inst.id


async def test_logo_persists_in_db_across_reload(session: AsyncSession) -> None:
    """Covers: KAL-INS-010

    Store a logo, drop every in-memory row (a restart with session storage
    gone), then read it back: identical bytes mean it came from the DB column,
    not from a file or in-process state.
    """
    svc = InstitutionService(session)
    inst_id = await _make_institution(session)
    assert await svc.set_logo(inst_id, "revolut.png", _PNG_BYTES) is True

    session.expire_all()

    logo = await svc.get_logo(inst_id)
    assert logo is not None
    content, mime = logo
    assert content == _PNG_BYTES
    assert mime == "image/png"


async def test_has_logo_reflects_the_stored_state(session: AsyncSession) -> None:
    svc = InstitutionService(session)
    inst_id = await _make_institution(session)

    before = await svc.get(inst_id)
    assert before is not None and before.has_logo is False

    await svc.set_logo(inst_id, "revolut.png", _PNG_BYTES)
    session.expire_all()
    after = await svc.get(inst_id)
    assert after is not None and after.has_logo is True


async def test_clear_logo_removes_it(session: AsyncSession) -> None:
    svc = InstitutionService(session)
    inst_id = await _make_institution(session)
    await svc.set_logo(inst_id, "revolut.png", _PNG_BYTES)

    assert await svc.clear_logo(inst_id) is True
    session.expire_all()
    assert await svc.get_logo(inst_id) is None
    reloaded = await svc.get(inst_id)
    assert reloaded is not None and reloaded.has_logo is False


async def test_get_logo_is_none_without_a_logo(session: AsyncSession) -> None:
    svc = InstitutionService(session)
    inst_id = await _make_institution(session)
    assert await svc.get_logo(inst_id) is None


async def test_set_logo_rejects_unsupported_format(session: AsyncSession) -> None:
    svc = InstitutionService(session)
    inst_id = await _make_institution(session)
    with pytest.raises(ValidationError):
        await svc.set_logo(inst_id, "logo.gif", _PNG_BYTES)


async def test_set_logo_rejects_oversize_image(session: AsyncSession) -> None:
    svc = InstitutionService(session)
    inst_id = await _make_institution(session)
    too_big = b"\x00" * (MAX_LOGO_BYTES + 1)
    with pytest.raises(ValidationError):
        await svc.set_logo(inst_id, "logo.png", too_big)


async def test_logo_route_404_without_a_logo(api_client: AsyncClient) -> None:
    """The serving route is wired and returns 404 when nothing is stored."""
    created = await api_client.post(
        "/api/v1/institutions/", json={"name": "No Logo Bank", "type": "bank"}
    )
    inst_id = created.json()["id"]
    resp = await api_client.get(f"/api/v1/institutions/{inst_id}/logo")
    assert resp.status_code == 404


async def test_logo_route_serves_the_stored_image(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    """Covers: KAL-INS-010

    The route is the "still served" half of the scenario. ``session`` and
    ``api_client`` share the test's single DB connection, so a logo stored
    through the service is visible to the HTTP request. The bytes come back
    byte-identical, with the image's own type and a private, sandboxed response.
    """
    svc = InstitutionService(session)
    inst_id = await _make_institution(session, name="Served Bank")
    await svc.set_logo(inst_id, "served.png", _PNG_BYTES)

    resp = await api_client.get(f"/api/v1/institutions/{inst_id}/logo")

    assert resp.status_code == 200
    assert resp.content == _PNG_BYTES
    assert resp.headers["content-type"] == "image/png"
    assert "private" in resp.headers["cache-control"]
    assert "sandbox" in resp.headers["content-security-policy"]
