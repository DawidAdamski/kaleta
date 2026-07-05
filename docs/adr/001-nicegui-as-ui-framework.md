---
adr_id: "001"
title: "NiceGUI as UI Framework"
status: accepted
---

# ADR-1: NiceGUI as UI Framework

- **Decision**: Use NiceGUI for the web frontend.
- **Rationale**: Python-native, builds on FastAPI/Starlette, supports both web and
  desktop (app) mode, no need for separate JS frontend.
- **Consequence**: API layer comes "for free" since NiceGUI wraps FastAPI.
