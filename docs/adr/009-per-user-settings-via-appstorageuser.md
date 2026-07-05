---
adr_id: "009"
title: "Per-User Settings via app.storage.user"
status: accepted
---

# ADR-9: Per-User Settings via app.storage.user

- **Decision**: Store all per-user preferences server-side in `app.storage.user`.
- **Rationale**: `app.storage.browser` (cookie-based) is not available synchronously
  on page render in NiceGUI. `app.storage.user` is server-side per-session and
  available immediately, making it reliable for per-page layout decisions.
- **Consequence**: Preferences persist within a session but reset on server restart.
  ECharts charts have explicit colour overrides via `views/chart_utils.py:apply_dark()`
  since ECharts does not auto-adapt to Quasar's dark mode. All persisted keys are
  enumerated in the `views/settings.py` module docstring:

  | Key | Values / Type | Default |
  |-----|---------------|---------|
  | `language` | `"en"` \| `"pl"` | `"en"` |
  | `currency` | ISO 4217 code | `"PLN"` |
  | `date_format` | `"iso"` \| `"eu"` \| `"us"` | `"iso"` |
  | `week_start` | `"monday"` \| `"sunday"` | `"monday"` |
  | `dark_mode` | `bool` | `False` |
  | `sidebar_mini` | `bool` | `False` |
  | `nav_collapsed` | `dict[str, bool]` | `{}` |
  | `wizard_onboarding_open` | `bool` | `True` |
  | `wizard_mentor_dismissed` | `list[str]` | `[]` |
  | `subscriptions_detector_days` | `int` | `730` |
  | `housekeeping_duplicate_days` | `int` | `365` |
  | `payment_calendar_overdue_days` | `int` | `30` |
  | `dashboard_widgets` | `dict[str, list[str]]` | `{}` |
