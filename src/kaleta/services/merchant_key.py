# SPDX-License-Identifier: AGPL-3.0-or-later
"""Normalise a transaction description to a stable merchant-key.

Shared by the subscription detector, the unplanned-spend radar and the
planned-price-drift service. Kept dependency-free so any of them can import it
without coupling to another service.
"""

from __future__ import annotations

import re

# Strip a trailing location/detail suffix so rows for the same service cluster.
# Tuned from live mBank data: "APPLE.COM/BILL /APPLE.COM/", "HBO Europe S.R.O
# /Prague", "Disney Plus /Hoofddorp", "GOOGLE *YouTube Vid/g.co/helpp".
_MERCHANT_KEY_MAX_LEN = 40


def merchant_key_from_description(desc: str | None) -> str:
    """Normalise a transaction description to a stable merchant-key.

    Keeps the first ``/``-delimited segment (service name before location),
    uppercases, collapses whitespace, and caps length. Returns ``""`` when
    nothing usable remains.
    """
    if not desc:
        return ""
    first = desc.split("/", 1)[0]
    first = re.sub(r"\s+", " ", first).strip().upper()
    return first[:_MERCHANT_KEY_MAX_LEN]
