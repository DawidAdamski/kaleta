---
adr_id: "002"
title: "SQLAlchemy 2.0 with Dual Database Support"
status: superseded
---

# ADR-2: SQLAlchemy 2.0 with Dual Database Support

- **Decision**: Use SQLAlchemy ORM with SQLite as default, PostgreSQL as optional.
- **Rationale**: SQLAlchemy's dialect system makes swapping backends trivial.
  SQLite is zero-config for personal use. PostgreSQL for multi-user / production.
- **Consequence**: Must avoid SQLite-incompatible features in models (e.g., array types).
  Use Alembic with `render_as_batch=True` for migrations that work across both backends.
  Enum columns use `SAEnum(..., native_enum=False)` for SQLite compatibility.

> **Superseded** by [ADR-38](038-postgresql-only-one-tenancy-layout.md):
> PostgreSQL is the only database; SQLite support is removed.
