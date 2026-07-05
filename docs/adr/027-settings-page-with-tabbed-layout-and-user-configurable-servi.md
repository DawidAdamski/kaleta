---
adr_id: "027"
title: "Settings Page with Tabbed Layout and User-Configurable Service Parameters"
status: accepted
---

# ADR-27: Settings Page with Tabbed Layout and User-Configurable Service Parameters

- **Decision**: Restructure `/settings` (`views/settings.py`) into 6 tabs — General, Appearance, Features, Data, History, About — and thread user-configurable window parameters into the services that previously used hard-coded defaults.
- **Rationale**: A flat settings page becomes unwieldy once the number of knobs exceeds a handful. Tabs group concerns naturally: locale/format knobs belong in General; theme knobs in Appearance; detector look-back windows in Features; backup/restore/wipe in Data; the audit log in History; and build metadata in About. Passing `window_days` arguments at the call site (rather than reading `app.storage.user` inside a service) keeps services storage-agnostic and independently testable.
- **Consequence**: `SubscriptionService.detect_candidates(window_days=...)`, `DedupeService.duplicate_transactions(window_days=...)`, and `PlannedTransactionService.grid_for_month(..., overdue_window_days=...)` each accept an explicit window parameter; callers read the value from `app.storage.user` and pass it in. The Wipe-DB action requires the user to type `DELETE` to confirm. The Reset Getting Started button clears `wizard_mentor_dismissed` and sets `wizard_onboarding_open = True`.
