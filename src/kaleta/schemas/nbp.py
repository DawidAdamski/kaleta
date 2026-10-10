# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class NbpFetchResult(BaseModel):
    """Outcome of importing one NBP Table A publication into ``public.nbp_rates``.

    ``rows_written`` counts the currencies new for that date; a second fetch
    of the same table writes none.
    """

    effective_date: datetime.date
    table_no: str = ""
    currencies_stored: int = Field(..., ge=0)
    rows_written: int = Field(..., ge=0)
