"""store institution logos in the database, not on the filesystem

Logos were files under ``~/.kaleta/logos`` served at ``/logos/..``, with only
``institutions.logo_path`` in the database. On a pod that directory is
ephemeral, so a redeploy wiped the files while the path survived and the
avatar rendered a broken image. The image now lives in the family's own
schema: ``logo_b64`` holds the bytes base64-encoded and encrypted under the
account data key (``EncryptedText``, storage type ``LargeBinary``), and the
plaintext ``logo_mime`` is the cheap "has a logo" signal and the route's
Content-Type.

Dropping ``logo_path`` discards the now-dead file references, so existing rows
fall back to the brand letter-circle until a logo is re-uploaded. No schema is
hard-coded: a per-family run is rewritten by ``schema_translate_map`` in
``alembic/env.py`` (ADR-35/ADR-38), as for every other migration.

Revision ID: b2e9f41a7c38
Revises: a1c7e2f84b50
Create Date: 2026-10-25 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2e9f41a7c38"
down_revision: str | Sequence[str] | None = "a1c7e2f84b50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("institutions", sa.Column("logo_mime", sa.String(length=100), nullable=True))
    op.add_column("institutions", sa.Column("logo_b64", sa.LargeBinary(), nullable=True))
    op.drop_column("institutions", "logo_path")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("institutions", sa.Column("logo_path", sa.String(length=255), nullable=True))
    op.drop_column("institutions", "logo_b64")
    op.drop_column("institutions", "logo_mime")
