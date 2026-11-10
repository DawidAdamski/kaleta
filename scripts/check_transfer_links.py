#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""List transfer links that do not hold together. Read-only.

Until plan ``import-transfer-pairs-api``, ``PUT /api/v1/transactions/{id}``
wrote ``linked_transaction_id`` on one row without any check. This script
reads every transfer through the API of a running instance and reports:

- ``one_sided``: a row linked to a partner that does not link back;
- ``dangling``: a row linked to a transaction that does not exist;
- ``amount_mismatch``: the two legs' amounts differ by more than a grosz;
- ``currency_mismatch``: the legs sit on accounts in different currencies;
- ``same_direction``: both legs say the money went the same way.

It only sends GET requests. Exit code 1 when anything is found.

    KALETA_API_TOKEN=... uv run python scripts/check_transfer_links.py \\
        --url https://kaleta.example
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

#: Same tolerance as ``TransactionService`` (DEFAULT_TRANSFER_AMOUNT_TOLERANCE).
AMOUNT_TOLERANCE = Decimal("0.01")
PAGE_SIZE = 200


@dataclass(frozen=True)
class Problem:
    kind: str
    transaction_id: int
    partner_id: int | None
    detail: str

    def line(self) -> str:
        partner = "-" if self.partner_id is None else str(self.partner_id)
        return f"{self.kind:18} {self.transaction_id:>8} -> {partner:>8}  {self.detail}"


def find_problems(
    linked: Iterable[Mapping[str, Any]],
    partners: Mapping[int, Mapping[str, Any] | None],
    currency_of: Mapping[int, str],
) -> list[Problem]:
    """Problems among ``linked`` rows (each with a ``linked_transaction_id``).

    ``partners`` maps every linked id to its row, or ``None`` when it does not
    exist; ``currency_of`` maps account ids to currencies. Each pair is
    reported once, from its lower id, except a one-sided link, reported from
    the row that holds it.
    """
    problems: list[Problem] = []
    for row in linked:
        tx_id = int(row["id"])
        partner_id = int(row["linked_transaction_id"])
        partner = partners.get(partner_id)
        if partner is None:
            problems.append(Problem("dangling", tx_id, partner_id, "partner does not exist"))
            continue
        if partner.get("linked_transaction_id") != tx_id:
            back = partner.get("linked_transaction_id")
            problems.append(Problem("one_sided", tx_id, partner_id, f"partner links to {back}"))
            continue
        if tx_id > partner_id:
            continue  # the pair is checked once, from its lower id
        gap = abs(abs(Decimal(str(row["amount"]))) - abs(Decimal(str(partner["amount"]))))
        if gap > AMOUNT_TOLERANCE:
            problems.append(
                Problem(
                    "amount_mismatch",
                    tx_id,
                    partner_id,
                    f"{row['amount']} vs {partner['amount']}",
                )
            )
        cur_a = currency_of.get(int(row["account_id"]), "?")
        cur_b = currency_of.get(int(partner["account_id"]), "?")
        if cur_a != cur_b:
            problems.append(Problem("currency_mismatch", tx_id, partner_id, f"{cur_a} vs {cur_b}"))
        direction = row.get("transfer_direction")
        if direction is not None and direction == partner.get("transfer_direction"):
            problems.append(Problem("same_direction", tx_id, partner_id, f"both '{direction}'"))
    return problems


class _Api:
    def __init__(self, url: str, token: str, timeout: float) -> None:
        self.client = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def pages(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self.client.get(path, params={**params, "page": page, "page_size": PAGE_SIZE})
            resp.raise_for_status()
            body = resp.json()
            items.extend(body["items"])
            if page >= int(body["pages"]):
                return items
            page += 1

    def transaction(self, tx_id: int) -> dict[str, Any] | None:
        resp = self.client.get(f"/api/v1/transactions/{tx_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return dict(resp.json())

    def currencies(self) -> dict[int, str]:
        resp = self.client.get("/api/v1/accounts/")
        resp.raise_for_status()
        body = resp.json()
        rows = body["items"] if isinstance(body, dict) else body
        return {int(a["id"]): str(a["currency"]) for a in rows}


def run(api: _Api) -> list[Problem]:
    transfers = api.pages("/api/v1/transactions/", {"type": "transfer"})
    linked = [row for row in transfers if row.get("linked_transaction_id") is not None]
    by_id: dict[int, dict[str, Any] | None] = {int(row["id"]): row for row in transfers}
    for row in linked:
        partner_id = int(row["linked_transaction_id"])
        if partner_id not in by_id:  # a partner that is not (or no longer) a transfer
            by_id[partner_id] = api.transaction(partner_id)
    print(f"{len(transfers)} transfer rows, {len(linked)} with a link.")
    return find_problems(linked, by_id, api.currencies())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List one-sided, dangling and mismatched transfer links (read-only)."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("KALETA_URL", "http://localhost:8080"),
        help="Base URL of the instance (default: $KALETA_URL or http://localhost:8080)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("KALETA_API_TOKEN"),
        help="Bearer token of the family to check (default: $KALETA_API_TOKEN)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds per request")
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("a bearer token is required (--token or KALETA_API_TOKEN)")
    problems = run(_Api(args.url, args.token, args.timeout))
    for problem in problems:
        print(problem.line())
    print(f"{len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
