---
adr_id: "021"
title: "BDD/E2E Test Layer with pytest-playwright"
status: accepted
---

# ADR-21: BDD/E2E Test Layer with pytest-playwright

- **Decision**: Add a `tests/e2e/` layer using pytest-playwright. Tests run against a live Kaleta instance (default `http://localhost:8080`). The Gherkin-style scenarios driving the suite are documented in `docs/bdd.md`.
- **Rationale**: Unit and integration tests cover service logic and schema validation in isolation but cannot catch regressions in UI flow, page routing, or NiceGUI component wiring. Playwright-based e2e tests exercise the full stack from the browser, covering the same user journeys described in the BDD scenarios.
- **Consequence**: The app must be running before the e2e suite executes. Browsers must be installed once with `uv run playwright install chromium`. E2e tests are kept in a separate directory so they are not picked up by the default `uv run pytest` invocation (which targets unit/integration). The `tests/e2e/conftest.py` provides the `base_url` session fixture.
