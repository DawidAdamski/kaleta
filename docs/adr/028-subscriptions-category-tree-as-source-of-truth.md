---
adr_id: "028"
title: "Subscriptions Category Tree as Source of Truth"
status: accepted
---

# ADR-28: Subscriptions Category Tree as Source of Truth

- **Decision**: One `Category` row carries `is_subscriptions_root = True`. That row and its direct children (flat tree, v1) are the authoritative definition of "what is a subscription charge". `CategoryService` exposes `get_subscriptions_root`, `list_subscription_children`, `subscription_category_ids`, and `ensure_subscriptions_root_and_children`. The migration `a4e9b2f1c6d8_add_subscriptions_root_category.py` idempotently creates the root "Subscriptions" + three children (Monthly / Yearly / Other) on existing DBs; `scripts/seed.py` creates the Polish equivalents (Subskrypcje / Miesięczne / Roczne / Inne) for fresh seeds.
- **Rationale**: Storing "is this a subscription?" as a model flag on `Transaction` or `Subscription` would require maintaining a separate classification list in sync with categories. Using an existing category subtree avoids duplication: once a transaction sits under the Subscriptions root, it is by definition a subscription charge — no secondary flag needed.
- **Consequence**: `SubscriptionService.detect_candidates` skips transactions already under the Subscriptions tree (they are already categorised). Tracking a candidate via `create_from_candidate(..., sub_category_id=...)` re-categorises all window-matching historical transactions (same payee or merchant-key + same amount bucket) to the chosen sub-category. The panel's "By category" card calls `subscription_transactions_grouped(window_days=90)` to show sub-category → merchant aggregations for the last 90 days. Multi-level nesting is deferred; only the root + direct children are used in v1.
