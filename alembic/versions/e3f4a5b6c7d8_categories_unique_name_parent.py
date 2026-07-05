"""change categories unique constraint from name to (name, parent_id)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-03-25 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


_COLS = "id, name, type, parent_id, created_at, updated_at"


def _upgrade_postgresql() -> None:
    op.drop_constraint("categories_name_key", "categories", type_="unique")
    op.create_unique_constraint("uq_categories_name_parent", "categories", ["name", "parent_id"])


def _downgrade_postgresql() -> None:
    op.drop_constraint("uq_categories_name_parent", "categories", type_="unique")
    op.create_unique_constraint("categories_name_key", "categories", ["name"])


def _upgrade_sqlite() -> None:
    # SQLite cannot drop individual constraints; rebuild the table without the
    # old unnamed UNIQUE(name) and with the new UNIQUE(name, parent_id) instead.
    op.execute("""
        CREATE TABLE categories_new (
            id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(7) NOT NULL,
            parent_id INTEGER,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_categories_parent_id
                FOREIGN KEY (parent_id) REFERENCES categories (id) ON DELETE SET NULL,
            CONSTRAINT uq_categories_name_parent UNIQUE (name, parent_id)
        )
    """)
    op.execute(f"INSERT INTO categories_new ({_COLS}) SELECT {_COLS} FROM categories")
    op.execute("DROP TABLE categories")
    op.execute("ALTER TABLE categories_new RENAME TO categories")


def _downgrade_sqlite() -> None:
    op.execute("""
        CREATE TABLE categories_new (
            id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL UNIQUE,
            type VARCHAR(7) NOT NULL,
            parent_id INTEGER,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT fk_categories_parent_id
                FOREIGN KEY (parent_id) REFERENCES categories (id) ON DELETE SET NULL
        )
    """)
    op.execute(f"INSERT INTO categories_new ({_COLS}) SELECT {_COLS} FROM categories")
    op.execute("DROP TABLE categories")
    op.execute("ALTER TABLE categories_new RENAME TO categories")


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _upgrade_postgresql()
        return
    _upgrade_sqlite()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _downgrade_postgresql()
        return
    _downgrade_sqlite()
