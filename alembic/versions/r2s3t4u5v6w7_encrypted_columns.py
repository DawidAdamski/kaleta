# SPDX-License-Identifier: AGPL-3.0-or-later
"""Field-level encryption: user-written text becomes bytes, equality moves to blind indexes.

``hosted-field-encryption``. Every column in ``ENCRYPTED`` changes to
``LargeBinary`` and every existing value is rewritten under format byte
``\\x00`` (plaintext) — so an existing database upgrades without a key, and the
reader accepts it either way. ``scripts/encrypt_database.py`` turns the
plaintext rows into ciphertext when encryption is switched on later.

New ``*_bidx`` columns take over equality and uniqueness. They are filled here
under the *plaintext-mode* index key, the one ``kaleta.db.types`` uses while
``KALETA_ENCRYPTION=off``; the normalisation and the key derivation are copied
below rather than imported, so this revision keeps meaning what it meant when
it was written.

Unique constraints on the plain ``name`` columns go — on ciphertext they can
never fire — and ``uq_<table>_name_bidx`` replace them. That makes those names
unique case-insensitively (the index normalises: NFKC, case-folded,
whitespace collapsed).

Revision ID: r2s3t4u5v6w7
Revises: f7a8b9c0d1e2
Create Date: 2026-10-03 10:00:00.000000
"""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from alembic import op

revision: str = "r2s3t4u5v6w7"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: table → columns that become ``EncryptedText``.
ENCRYPTED: dict[str, tuple[str, ...]] = {
    "accounts": ("name", "external_account_number"),
    "transactions": ("description", "notes"),
    "transaction_splits": ("note",),
    "payees": ("name", "website", "address", "city", "country", "email", "phone", "notes"),
    "categories": ("name",),
    "tags": ("name", "description"),
    "institutions": ("name", "website", "description"),
    "assets": ("name", "description"),
    "planned_transactions": ("name", "description"),
    "reserve_funds": ("name",),
    "subscriptions": ("name", "url", "notes"),
    "counterparties": ("name", "notes"),
    "personal_loans": ("notes",),
    "personal_loan_repayments": ("note",),
    "saved_reports": ("name", "config"),
    "categorisation_rules": ("pattern",),
    "import_rules": ("filename_pattern",),
    "import_runs": ("filename",),
    "yearly_plans": ("income_lines", "fixed_lines", "variable_lines", "reserves_lines"),
    "audit_log": ("old_data", "new_data"),
    # Not in the plan's table, which predates them; both carry payee names,
    # which would otherwise sit in plaintext next to the encrypted ones.
    "payee_identities": ("pattern",),
    "payee_auto_merges": ("merged_name", "snapshot"),
}

#: Tables whose ``name`` gets a unique blind index (categories: see below).
_UNIQUE_NAME_BIDX = ("payees", "tags", "institutions", "counterparties")
_COUNTERPARTY_UQ = "uq_counterparty_name_bidx"

#: SQLite reports unnamed unique constraints with no name; batch mode needs one
#: to drop them.
_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}

_PLAIN = b"\x00"
_SUFFIX_DIGITS = 8
_WHITESPACE = re.compile(r"\s+")
_PLAIN_INDEX_KEY = HKDF(
    algorithm=SHA256(), length=32, salt=None, info=b"kaleta-blind-index-plaintext"
).derive(b"\x00" * 32)


def _normalise(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _index(normalised: str) -> str:
    return hmac.new(_PLAIN_INDEX_KEY, normalised.encode("utf-8"), hashlib.sha256).hexdigest()


def _name_index(value: str | None) -> str | None:
    return None if value is None else _index(_normalise(value))


def _digits_index(value: str | None, last: int | None = None) -> str | None:
    if value is None:
        return None
    digits = "".join(
        ch for ch in unicodedata.normalize("NFKC", value) if ch.isascii() and ch.isdigit()
    )
    if last is not None:
        digits = digits[-last:]
    return _index("#" + digits) if digits else None


def _text(value: object) -> str | None:
    """A stored value as text: before the type change it is ``str``, after it ``\\x00``+UTF-8."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    data = bytes(value)  # type: ignore[call-overload]
    if data[:1] == _PLAIN:
        return data[1:].decode("utf-8")
    return data.decode("utf-8")


def _drop_name_uniques(table: str, bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    uniques = [uc for uc in inspector.get_unique_constraints(table) if "name" in uc["column_names"]]
    if not uniques:
        return
    with op.batch_alter_table(table, naming_convention=_NAMING) as batch_op:
        for uc in uniques:
            name = uc["name"] or f"uq_{table}_{uc['column_names'][0]}"
            batch_op.drop_constraint(name, type_="unique")


def _to_binary(table: str, columns: tuple[str, ...], bind: sa.engine.Connection) -> None:
    existing = {c["name"]: c for c in sa.inspect(bind).get_columns(table)}
    postgres = bind.dialect.name == "postgresql"
    defaulted = [c for c in columns if existing[c].get("default") is not None]
    if defaulted:
        # Text defaults (`''`) mean nothing to a bytes column, and Postgres
        # will not cast one across a type change: drop them first. The models
        # set the default in Python instead.
        with op.batch_alter_table(table) as batch_op:
            for column in defaulted:
                batch_op.alter_column(
                    column,
                    existing_type=existing[column]["type"],
                    existing_nullable=existing[column]["nullable"],
                    server_default=None,
                )
    with op.batch_alter_table(table) as batch_op:
        for column in columns:
            info = existing[column]
            kwargs: dict[str, object] = {
                "existing_type": info["type"],
                "existing_nullable": info["nullable"],
                "type_": sa.LargeBinary(),
            }
            if postgres:
                kwargs["postgresql_using"] = (
                    f"('\\x00'::bytea || convert_to({column}::text, 'UTF8'))"
                )
            batch_op.alter_column(column, **kwargs)
    if postgres:
        return
    # SQLite: batch mode copied the text across as it was; prefix the format byte.
    for column in columns:
        rows = bind.execute(
            sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")
        ).all()
        if rows:
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),
                [{"id": row[0], "value": _PLAIN + _text(row[1]).encode("utf-8")} for row in rows],  # type: ignore[union-attr]
            )


def _fill(table: str, source: str, targets: dict[str, object], bind: sa.engine.Connection) -> None:
    rows = bind.execute(sa.text(f"SELECT id, {source} FROM {table}")).all()
    if not rows:
        return
    assignments = ", ".join(f"{target} = :{target}" for target in targets)
    params = []
    for row_id, raw in rows:
        value = _text(raw)
        params.append(
            {"id": row_id, **{target: fn(value) for target, fn in targets.items()}}  # type: ignore[operator]
        )
    bind.execute(
        sa.text(f"UPDATE {table} SET {assignments} WHERE id = :id"),
        params,
    )


def _identity_index(value: str | None) -> str | None:
    """``PayeeIdentity.pattern_key``: the index of the collapsed, case-folded spelling."""
    return None if value is None else _index(_normalise(" ".join(value.split()).casefold()))


def upgrade() -> None:
    bind = op.get_bind()

    # An index on the spelling means nothing once the spelling is ciphertext.
    with op.batch_alter_table("payee_identities") as batch_op:
        batch_op.drop_index("ix_payee_identities_pattern")

    # Uniques on plain names first: on Postgres they would otherwise be carried
    # over onto the bytea column, where ciphertext can never collide.
    for table in (*_UNIQUE_NAME_BIDX, "categories"):
        _drop_name_uniques(table, bind)

    for table, columns in ENCRYPTED.items():
        _to_binary(table, columns, bind)

    for table in (*_UNIQUE_NAME_BIDX, "categories"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("name_bidx", sa.String(length=64), nullable=True))
        _fill(table, "name", {"name_bidx": _name_index}, bind)
    for table in ("payees", "tags", "institutions"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.create_unique_constraint(f"uq_{table}_name_bidx", ["name_bidx"])
    with op.batch_alter_table("counterparties") as batch_op:
        batch_op.create_unique_constraint(_COUNTERPARTY_UQ, ["name_bidx"])
    with op.batch_alter_table("categories") as batch_op:
        batch_op.create_index("ix_categories_name_bidx", ["name_bidx"])
        batch_op.create_unique_constraint(
            "uq_categories_parent_type_name_bidx", ["parent_id", "type", "name_bidx"]
        )

    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(
            sa.Column("external_account_number_bidx", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("external_account_number_sfx_bidx", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            "ix_accounts_external_account_number_bidx", ["external_account_number_bidx"]
        )
        batch_op.create_index(
            "ix_accounts_external_account_number_sfx_bidx", ["external_account_number_sfx_bidx"]
        )
    _fill(
        "accounts",
        "external_account_number",
        {
            "external_account_number_bidx": _digits_index,
            "external_account_number_sfx_bidx": lambda v: _digits_index(v, _SUFFIX_DIGITS),
        },
        bind,
    )

    # The identity key becomes the blind index of the key.
    with op.batch_alter_table("payee_identities") as batch_op:
        batch_op.alter_column(
            "pattern_key",
            existing_type=sa.String(length=200),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
    _fill("payee_identities", "pattern", {"pattern_key": _identity_index}, bind)

    # The merchant key is only ever compared: keep its index, not the key.
    with op.batch_alter_table("dismissed_candidate_patterns") as batch_op:
        batch_op.alter_column(
            "merchant_key",
            existing_type=sa.String(length=60),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
    _fill("dismissed_candidate_patterns", "merchant_key", {"merchant_key": _name_index}, bind)

    op.create_table(
        "local_key_material",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("private_key_wrapped", sa.LargeBinary(), nullable=False),
        sa.Column("private_key_salt", sa.LargeBinary(), nullable=False),
        sa.Column("kdf_params", sa.Text(), nullable=False),
        sa.Column("recovery_wrapped", sa.LargeBinary(), nullable=True),
        sa.Column("recovery_salt", sa.LargeBinary(), nullable=True),
        sa.Column("dek_sealed", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Back to text — refused while any value is a ciphertext (decrypt it first)."""
    bind = op.get_bind()
    for table, columns in ENCRYPTED.items():
        for column in columns:
            rows = bind.execute(
                sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")
            ).all()
            if any(bytes(raw)[:1] != _PLAIN for _id, raw in rows):
                msg = (
                    f"{table}.{column} holds encrypted values; run "
                    "scripts/encrypt_database.py --decrypt before downgrading."
                )
                raise RuntimeError(msg)

    op.drop_table("local_key_material")
    # The index of a merchant key cannot be turned back into the key: the
    # dismissals it recorded are dropped, and the radar will offer them again.
    bind.execute(sa.text("DELETE FROM dismissed_candidate_patterns WHERE merchant_key IS NOT NULL"))
    with op.batch_alter_table("dismissed_candidate_patterns") as batch_op:
        batch_op.alter_column(
            "merchant_key",
            existing_type=sa.String(length=64),
            type_=sa.String(length=60),
            existing_nullable=True,
        )
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_index("ix_accounts_external_account_number_sfx_bidx")
        batch_op.drop_index("ix_accounts_external_account_number_bidx")
        batch_op.drop_column("external_account_number_sfx_bidx")
        batch_op.drop_column("external_account_number_bidx")
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_constraint("uq_categories_parent_type_name_bidx", type_="unique")
        batch_op.drop_index("ix_categories_name_bidx")
        batch_op.drop_column("name_bidx")
    with op.batch_alter_table("counterparties") as batch_op:
        batch_op.drop_constraint(_COUNTERPARTY_UQ, type_="unique")
        batch_op.drop_column("name_bidx")
    for table in ("payees", "tags", "institutions"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(f"uq_{table}_name_bidx", type_="unique")
            batch_op.drop_column("name_bidx")

    postgres = bind.dialect.name == "postgresql"
    for table, columns in ENCRYPTED.items():
        if not postgres:
            decoded = {
                column: [
                    {"id": row[0], "value": _text(row[1])}
                    for row in bind.execute(
                        sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")
                    ).all()
                ]
                for column in columns
            }
        with op.batch_alter_table(table) as batch_op:
            for column in columns:
                is_json = (table, column) == ("payee_auto_merges", "snapshot")
                kwargs: dict[str, object] = {
                    "existing_type": sa.LargeBinary(),
                    "type_": sa.JSON() if is_json else sa.Text(),
                }
                if postgres:
                    cast = "::json" if is_json else ""
                    kwargs["postgresql_using"] = (
                        f"convert_from(substring({column} from 2), 'UTF8'){cast}"
                    )
                batch_op.alter_column(column, **kwargs)
        if not postgres:
            for column, params in decoded.items():
                if params:
                    bind.execute(
                        sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),
                        params,
                    )

    with op.batch_alter_table("payee_identities") as batch_op:
        batch_op.alter_column(
            "pattern_key",
            existing_type=sa.String(length=64),
            type_=sa.String(length=200),
            existing_nullable=False,
        )
    _fill(
        "payee_identities",
        "pattern",
        {"pattern_key": lambda v: None if v is None else " ".join(v.split()).casefold()},
        bind,
    )
    with op.batch_alter_table("payee_identities") as batch_op:
        batch_op.create_index("ix_payee_identities_pattern", ["pattern"])

    with op.batch_alter_table("counterparties") as batch_op:
        batch_op.create_unique_constraint("uq_counterparty_name", ["name"])
    with op.batch_alter_table("categories") as batch_op:
        batch_op.create_unique_constraint(
            "uq_categories_name_parent_type", ["name", "parent_id", "type"]
        )
    for table in ("payees", "tags", "institutions"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.create_unique_constraint(f"uq_{table}_name", ["name"])
