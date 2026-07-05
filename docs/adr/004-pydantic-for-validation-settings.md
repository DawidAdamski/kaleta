---
adr_id: "004"
title: "Pydantic for Validation & Settings"
status: accepted
---

# ADR-4: Pydantic for Validation & Settings

- **Decision**: Use Pydantic v2 for request/response schemas and app configuration.
- **Rationale**: Type-safe validation, serialization, and env-based settings.
  Integrates natively with FastAPI (and thus NiceGUI).
