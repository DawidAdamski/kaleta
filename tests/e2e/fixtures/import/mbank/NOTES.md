# mBank export variants (dogfood)

Anonymized samples from real mBank **Elektroniczne zestawienie operacji**
exports (Windows-1250 on disk; stored here as UTF-8).

| File | Account type | Notes |
|---|---|---|
| `credit-card-sample.csv` | Credit card (`WORLD MASTERCARD…`) | Extra `#Numer karty` column |
| `current-account-sample.csv` | Current/savings (`MKONTO INTENSIVE`) | `#Saldo po operacji`, transfer `Numer konta` |

Both use the existing `mbank` profile — no separate registry key.

Original exports trimmed to ~12 rows; names/IBANs/account numbers replaced
per the parent [README](../README.md) checklist.
