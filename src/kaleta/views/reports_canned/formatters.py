"""CSV export and amount formatting for canned reports."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from nicegui import ui


def csv_download(filename: str, headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    """Build a CSV in memory and trigger a browser download."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(
            "" if v is None else (f"{v:.2f}" if isinstance(v, Decimal) else v) for v in row
        )
    ui.download(buf.getvalue().encode("utf-8-sig"), filename=filename)


def fmt(amount: Decimal) -> str:
    return f"{amount:,.2f} zł"


def fmt_pct(pct: Decimal | None) -> str:
    return f"{pct:.1f}%" if pct is not None else "—"
