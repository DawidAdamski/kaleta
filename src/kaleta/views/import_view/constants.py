# SPDX-License-Identifier: AGPL-3.0-or-later
"""Import view constants — bank profiles and queue status colours.

Profile keys / labels / enable flags come from
``kaleta.services.import_profiles`` — add banks there (with fixtures), not here.
"""

from __future__ import annotations

from kaleta.services.import_profiles import iter_ui_profiles

_PROFILES: list[tuple[str, str, str, bool]] = iter_ui_profiles()

STATUS_COLOR: dict[str, str] = {
    "pending": "grey-6",
    "ready": "primary",
    "importing": "amber-7",
    "done": "positive",
    "failed": "negative",
    "skipped": "grey-6",
}
