---
adr_id: "026"
title: "Initial Setup Wizard with Zero-Based Budget Enforcement"
status: accepted
---

# ADR-26: Initial Setup Wizard with Zero-Based Budget Enforcement

- **Decision**: Add a `/wizard` view (`views/wizard.py`) that guides new users through sequential steps: institution → accounts with opening balances → categories → zero-based budget assignment. The "Finish Setup" button is disabled until the unassigned amount equals zero. A separate `/setup` view (`views/setup.py`) handles first-run database configuration (local vs cloud).
- **Rationale**: An empty database provides no orientation. The wizard ensures every user begins with a valid institution, at least one account, a category structure, and a fully assigned budget — the minimum viable state for the app to be useful. Enforcing zero-based assignment at setup establishes the budgeting discipline the app is built around.
- **Consequence**: A `setup_complete` flag (stored in `app.storage.user` or a settings row) gates the redirect: an empty database sends the user to `/wizard`; a completed setup sends them to the dashboard. Wizard state (which steps are complete) persists so users can resume after an interruption. The "load suggested categories" action inserts a predefined Polish-language category set. Opening balances entered in the accounts step are recorded as initial-balance transactions on the respective accounts.
