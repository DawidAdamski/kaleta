"""Import view constants — bank profiles and queue status colours."""

from __future__ import annotations

_PROFILES: list[tuple[str, str, str, bool]] = [
    ("generic", "import.profile_generic", "table_chart", True),
    ("mbank", "import.profile_mbank", "account_balance", True),
]

STATUS_COLOR: dict[str, str] = {
    "pending": "grey-6",
    "ready": "primary",
    "importing": "amber-7",
    "done": "positive",
    "failed": "negative",
    "skipped": "grey-6",
}
