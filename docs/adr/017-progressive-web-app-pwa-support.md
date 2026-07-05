---
adr_id: "017"
title: "Progressive Web App (PWA) Support"
status: accepted
---

# ADR-17: Progressive Web App (PWA) Support

- **Decision**: Add PWA support via `src/kaleta/pwa.py`, which registers `/manifest.json`, `/sw.js`, and `/static` endpoints on the NiceGUI/FastAPI app. `PWA_HEAD` (meta tags + service worker registration script) is injected via `ui.add_head_html()` in every page. `pwa.setup()` runs in `main.py` before views register, for both `web` and `app` modes.
- **Rationale**: PWA support allows Kaleta to be installed on mobile and desktop as a standalone app without a separate native build. The service worker uses cache-first for static assets and network-first for navigation; API calls bypass the cache entirely to keep financial data fresh.
- **Consequence**: Static files live in `src/kaleta/static/` (manifest, service worker, SVG icon). The `pwa` module owns all PWA-related routes and keeps them out of `main.py` and individual views.
