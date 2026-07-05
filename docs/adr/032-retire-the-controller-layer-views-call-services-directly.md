---
adr_id: "032"
title: "Retire the Controller Layer — Views Call Services Directly"
status: accepted
---

# ADR-32: Retire the Controller Layer — Views Call Services Directly

- **Decision**: Remove the empty `src/kaleta/controllers/` package and drop the controller layer from the declared architecture. The canonical pattern is: **NiceGUI views → services** and **API routes (`api/v1/`) → services**. `CLAUDE.md`, `AGENTS.md`, and the architecture diagram in this document are updated to match. No new intermediary layer is introduced.
- **Rationale**: The controllers package remained empty across 75 commits and ~26k LOC of delivered features — empirical proof the layer is not needed. In NiceGUI, a page function already fulfils the controller role: it binds UI events, calls services, and maps results to components. For REST, FastAPI routers in `api/v1/` are the controllers. Adding a third layer would duplicate orchestration without separating any real concern. The actual discipline worth enforcing is that **business logic lives in services, never in views** — that is guarded by the views-refactor plan (shared components, ≤500 LOC per view file) and by unit-testing services in isolation, not by an empty package.
- **Consequence**: `src/kaleta/controllers/` is deleted. The architecture diagram becomes `Views (NiceGUI) + API (FastAPI) → Services → Models/Schemas → DB`. The naming convention `*Controller` is retired. Any future need for shared orchestration between a view and an API route is met by promoting that logic into the service layer (or a dedicated service), not by resurrecting controllers.
