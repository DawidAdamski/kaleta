---
adr_id: "003"
title: "MVC + Service Layer Separation"
status: accepted
---

# ADR-3: MVC + Service Layer Separation

- **Decision**: Strict separation between Models, Views, Controllers, and Services.
- **Rationale**: Clean separation of concerns enables independent testing, reuse
  of business logic across UI and API, and easier future changes.
- **Consequence**: Slightly more files/boilerplate, but much better maintainability.
