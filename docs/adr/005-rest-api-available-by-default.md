---
adr_id: "005"
title: "REST API Available by Default"
status: accepted
---

# ADR-5: REST API Available by Default

- **Decision**: Expose a REST API alongside the UI.
- **Rationale**: Enables external integrations, mobile apps, automation scripts,
  and headless usage. Since NiceGUI uses FastAPI, API routes are easy to add.
