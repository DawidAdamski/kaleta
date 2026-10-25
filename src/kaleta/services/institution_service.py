# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import base64
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.exceptions import ValidationError
from kaleta.models.institution import Institution
from kaleta.schemas.institution import InstitutionCreate, InstitutionUpdate
from kaleta.services.text_order import by_name

#: Logos are small brand marks; keep the ceiling well under the generic
#: upload cap so a stray large image cannot bloat the row (and its base64).
MAX_LOGO_BYTES = 2 * 1024 * 1024

#: Suffix → canonical MIME. The suffix is the trusted signal (the browser's
#: reported type can be spoofed or empty); anything else is refused.
_LOGO_MIME_BY_SUFFIX = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def logo_mime_for(filename: str) -> str:
    """The canonical MIME for *filename*'s extension, or raise ``ValidationError``."""
    suffix = PurePosixPath(filename).suffix.lower()
    mime = _LOGO_MIME_BY_SUFFIX.get(suffix)
    if mime is None:
        raise ValidationError(f"Unsupported logo format: {suffix or filename}")
    return mime


class InstitutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Institution]:
        result = await self.session.execute(select(Institution))
        return by_name(result.scalars().all())

    async def get(self, institution_id: int) -> Institution | None:
        return await self.session.get(Institution, institution_id)

    async def get_with_accounts(self, institution_id: int) -> Institution | None:
        result = await self.session.execute(
            select(Institution)
            .options(selectinload(Institution.accounts))
            .where(Institution.id == institution_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: InstitutionCreate) -> Institution:
        institution = Institution(**data.model_dump())
        self.session.add(institution)
        await self.session.commit()
        await self.session.refresh(institution)
        return institution

    async def update(self, institution_id: int, data: InstitutionUpdate) -> Institution | None:
        institution = await self.get(institution_id)
        if institution is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(institution, field, value)
        await self.session.commit()
        await self.session.refresh(institution)
        return institution

    async def delete(self, institution_id: int) -> bool:
        institution = await self.get(institution_id)
        if institution is None:
            return False
        await self.session.delete(institution)
        await self.session.commit()
        return True

    async def set_logo(self, institution_id: int, filename: str, content: bytes) -> bool:
        """Store *content* as this institution's logo (encrypted base64 + plaintext mime).

        Raises ``ValidationError`` for an unsupported format or an oversize
        image. Returns ``False`` when the institution does not exist.
        """
        mime = logo_mime_for(filename)
        if len(content) > MAX_LOGO_BYTES:
            raise ValidationError(f"Logo is larger than {MAX_LOGO_BYTES // (1024 * 1024)} MB")
        institution = await self.get(institution_id)
        if institution is None:
            return False
        institution.logo_mime = mime
        institution.logo_b64 = base64.b64encode(content).decode("ascii")
        await self.session.commit()
        return True

    async def clear_logo(self, institution_id: int) -> bool:
        """Drop the stored logo; returns ``False`` when the institution does not exist."""
        institution = await self.get(institution_id)
        if institution is None:
            return False
        institution.logo_mime = None
        institution.logo_b64 = None
        await self.session.commit()
        return True

    async def get_logo(self, institution_id: int) -> tuple[bytes, str] | None:
        """The logo ``(bytes, mime)`` for the serving route, or ``None`` when unset.

        Selects the deferred, encrypted column explicitly — an async lazy
        attribute load would raise ``MissingGreenlet``.
        """
        result = await self.session.execute(
            select(Institution.logo_b64, Institution.logo_mime).where(
                Institution.id == institution_id
            )
        )
        row = result.one_or_none()
        if row is None or row.logo_mime is None or row.logo_b64 is None:
            return None
        return base64.b64decode(row.logo_b64), row.logo_mime
