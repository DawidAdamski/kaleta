---
plan_id: subscription-cadence-float-parse
title: Saving a subscription with a changed cadence fails ("invalid literal for int() ... '365.0'")
area: subscriptions
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Saving a subscription with a changed cadence fails ("invalid literal for int() ... '365.0'")

## Intent

In Kaleta 0.8.0 a subscription's cadence cannot be changed from the UI. In the
"New subscription" or "Edit subscription" dialog, typing any value into
"Cadence (days)", for example `365` for a yearly plan, and pressing Save shows
the warning toast

```
invalid literal for int() with base 10: '365.0'
```

and nothing is saved. Saving works only if the cadence field was **never
focused**. Even focusing the field and leaving it unchanged turns `30` into
`30.0` (NiceGUI sanitises the value on blur). As a result no yearly (or other
non-30-day) subscription can be created or corrected in the UI. The
subscriptions REST API is read-only (`GET /api/v1/subscriptions/` only), so
there is no workaround.

The bug was found on 2026-11-09 on a self-hosted 0.8.0 instance while fixing the
user's subscription list. Disney+, moved to a yearly plan at 599,90 PLN, stays
recorded as monthly 49,99 with a wrong next date. A yearly subscription at
599,99 PLN could not be added at all.

Root cause (verified against NiceGUI 3.18.0, pinned in `uv.lock`):

- `src/kaleta/views/subscriptions/dialogs.py:63–73` defines the field as
  `ui.number(..., value=30, min=1, max=400, format="%d")`. NiceGUI stores
  edits as `float(e.args)`, and `sanitize()` on blur applies
  `float(self.format % value)`. So after any interaction the value is a
  Python `float` (`365.0`). `format="%d"` also already truncates `365.5` to
  `365.0` on blur.
- `dialogs.py:~203` passes `cadence_value=cadence_in.value` to
  `parse_subscription_form`.
- `src/kaleta/services/subscription_service.py:128` does
  `cadence = int(str(cadence_value or 30))`, so `int("365.0")` raises
  `ValueError`. That is re-raised as `SubscriptionFormError(str(exc))`, and the
  dialog shows the raw Python message
  (`ui.notify(exc.message, type="warning")`, `dialogs.py:211–212`).

## Scope

In scope:

1. **Typed error with a translation key.** Make `SubscriptionFormError`
   (`subscription_service.py:84`) a subclass of
   `kaleta.exceptions.ValidationError`, which already carries `message_key`
   and `params` (`exceptions.py:22–35`). Keep `.message` as the English
   fallback so the existing callers and the tests that match on `.message`
   ("Name required") keep working. In `save_sub` (`dialogs.py:211–212`), replace
   `ui.notify(exc.message, ...)` with the existing helper that resolves
   `message_key`/`params` for toasts (`views.error_handling.notify_kaleta_error`
   / `resolve_toast_text`, KAL-ERR-001), so the toast is translated and falls
   back to `.message` when no key is set.
2. **Whole-number parsing.** Add a private module-level function
   `_parse_cadence_days(value: object) -> int` in `subscription_service.py`,
   next to `parse_subscription_form`. It is a module-level function because
   `parse_subscription_form` is one; it is not a new feature class (AGENTS.md
   style note).
   - `None` or `""` → `30` (the default).
   - Reject `bool` → `errors.subscription.cadence_whole_days`.
   - `int`: used as is.
   - `float`, `Decimal`, or `str`: strip whitespace, replace `,` with `.`, and
     parse with `Decimal(...)`. A non-numeric string, NaN or infinity raises
     `errors.subscription.cadence_whole_days`. A value with a fractional part
     (`365.5`) raises the same key. An integral value (`365.0`) becomes `365`.
   - A result outside `1..400` raises `errors.subscription.cadence_range` with
     params `{min: 1, max: 400}`. The bounds match `schemas/subscription.py:17,36`
     and the widget.
   - **Behaviour change, deliberate:** `0` today silently becomes `30`
     (`cadence_value or 30`). It now raises the range error. `0` is never a
     valid cadence, and the widget's `min=1` already forbids it.
   `parse_subscription_form` uses `_parse_cadence_days(cadence_value)` in
   place of `int(str(cadence_value or 30))`. The other parsing there stays as
   it is.
3. **Translation strings**, added to `src/kaleta/i18n/locales/en.json` and
   `pl.json` under `errors.subscription`, following the existing keys
   (`subscription_service.py:516,522,527,641`):
   - `cadence_whole_days`
     - en: "Cadence must be a whole number of days."
     - pl: "Częstotliwość musi być pełną liczbą dni."
   - `cadence_range`
     - en: "Cadence must be between {min} and {max} days."
     - pl: "Częstotliwość musi wynosić od {min} do {max} dni."
4. **The widget is unchanged.** `precision=0` would still store a float and
   would round on blur, so it fixes nothing. The service fix is the real fix:
   other callers, such as tests or a future API route, do not go through the
   widget. A fractional value cannot be reached from the UI, because
   `format="%d"` truncates it on blur. That is why the fractional case has a
   unit test and no e2e test.

Tests:

- Unit tests in `tests/unit/services/test_subscription_service.py`:
  - `test_parse_form_accepts_float_cadence`: `cadence_value=365.0` gives
    `cadence_days == 365`. Docstring `Covers: KAL-SUB-011`.
  - `test_parse_form_accepts_numeric_string_cadence`: `"365"`, `"365.0"`,
    `"365,0"` and `" 365 "` each give 365.
  - `test_parse_form_rejects_fractional_cadence`: `365.5` and `"365,5"` raise
    `SubscriptionFormError` with
    `message_key == "errors.subscription.cadence_whole_days"`.
  - `test_parse_form_rejects_non_numeric_cadence`: `"abc"`, `True`, `float("nan")`.
  - `test_parse_form_rejects_out_of_range_cadence`: `0` and `401` raise an error
    with `message_key == "errors.subscription.cadence_range"` and
    `params == {"min": 1, "max": 400}`.
  - `test_parse_form_default_cadence`: `None` and `""` give 30.
- E2E tests in `tests/e2e/test_subscriptions.py`, each with the docstring
  `Covers: KAL-SUB-011`:
  - `test_add_yearly_subscription`: add "Domain renewal", amount `120.00`,
    cadence `365`, then save.
    - The new row shows the yearly cadence label
      (`subscriptions.detector_cadence_yearly`, rendered by `cadence_label`).
    - No warning toast appears.
  - `test_edit_subscription_cadence`: seed "Disney+" with amount `49.99` and
    cadence `30`. Edit it to amount `599.90` and cadence `365`, then save.
    - The row shows the yearly cadence label.
    - The header's monthly total shows `49.99`.
    - No warning toast appears.
- BDD: add a new scenario to `docs/bdd.md`.

  ```gherkin
  KAL-SUB-011 @automated
  Scenario: Subscription cadence can be changed to any whole number of days
    Given a subscription "Disney+" of 49.99 every 30 days
    When I edit it to amount 599.90 and cadence 365 and save
    Then no warning is shown
    And the subscription is listed as yearly
    And the monthly total shows 49.99
  ```

Out of scope (added to `docs/plans/chores.md`):

- Re-projecting `next_expected_at` when the cadence changes. `update()`
  copies the payload field by field, so the user must edit the date as well.
- Write endpoints for subscriptions in the REST API.
- The detector suggesting "Track" again for a tracked subscription after its
  name or amount is edited.
- Personal loans. `parse_repayment_form` (`personal_loan_service.py:432–441`)
  uses the same `int(str(...))` pattern, but all three link values come from
  `ui.select` widgets (`views/personal_loans/dialogs.py:161,172,182`), which
  return integer option keys. The only `ui.number` there (`rep_amount`, :141)
  goes through `Decimal(str(...))`, which accepts floats. No change; note this
  under "Implementation notes".

## Acceptance criteria

- `uv run pytest tests/unit/services/test_subscription_service.py -q -k "parse_form"`.
  This selects only the new tests; it exits with status 5 if they are missing.
- `uv run pytest tests/unit/services/test_subscription_service.py -q -k "parse_subscription_form"`.
  The existing tests must stay green.
- `uv run pytest tests/e2e/test_subscriptions.py -q -k "add_yearly_subscription or edit_subscription_cadence"`
- `grep -qE "KAL-SUB-011 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` On a running instance:
  1. Edit a subscription of 49.99 every 30 days to 599.90 every 365 days and save.
  2. Check that no toast appears.
  3. Check that the row says yearly.
  4. Check that this subscription's share of the "/ month" header stays at 49.99.

## Touchpoints

- `src/kaleta/services/subscription_service.py`: `SubscriptionFormError`,
  the new `_parse_cadence_days`, and `parse_subscription_form`.
- `src/kaleta/exceptions.py`: read only (the `ValidationError` base class).
- `src/kaleta/views/subscriptions/dialogs.py`: the toast in `save_sub`
  resolves `message_key`.
- `src/kaleta/i18n/locales/en.json` and `pl.json`: two keys.
- `tests/unit/services/test_subscription_service.py` and
  `tests/e2e/test_subscriptions.py`.
- `docs/bdd.md` (`KAL-SUB-011`) and `docs/plans/chores.md` (three entries).

## Open questions

None.

## Implementation notes

## Implementation (filled by plan-archiver)
