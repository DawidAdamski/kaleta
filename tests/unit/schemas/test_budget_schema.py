"""Unit tests for BudgetCreate and BudgetUpdate Pydantic schemas."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from kaleta.schemas.budget import BudgetCreate, BudgetUpdate


def _base(**kwargs) -> dict:
    defaults = dict(category_id=1, amount=Decimal("500.00"), month=3, year=2026)
    defaults.update(kwargs)
    return defaults


class TestBudgetCreate:

    def test_valid(self):
        schema = BudgetCreate(**_base())
        assert schema.amount == Decimal("500.00")
        assert schema.month == 3
        assert schema.year == 2026

    # ── Amount validation ──────────────────────────────────────────────────

    def test_zero_amount_rejected(self):
        with pytest.raises(ValidationError, match="greater than"):
            BudgetCreate(**_base(amount=Decimal("0.00")))

    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError, match="greater than"):
            BudgetCreate(**_base(amount=Decimal("-100.00")))

    def test_amount_string_rejected(self):
        with pytest.raises(ValidationError):
            BudgetCreate(**_base(amount="free"))  # type: ignore[arg-type]

    def test_very_large_amount_accepted(self):
        schema = BudgetCreate(**_base(amount=Decimal("9999999.99")))
        assert schema.amount == Decimal("9999999.99")

    # ── Month validation ───────────────────────────────────────────────────

    def test_month_zero_rejected(self):
        with pytest.raises(ValidationError):
            BudgetCreate(**_base(month=0))

    def test_month_13_rejected(self):
        with pytest.raises(ValidationError):
            BudgetCreate(**_base(month=13))

    def test_month_negative_rejected(self):
        with pytest.raises(ValidationError):
            BudgetCreate(**_base(month=-1))

    @pytest.mark.parametrize("month", range(1, 13))
    def test_all_valid_months_accepted(self, month: int):
        schema = BudgetCreate(**_base(month=month))
        assert schema.month == month

    # ── Year validation ────────────────────────────────────────────────────

    def test_year_before_2000_rejected(self):
        with pytest.raises(ValidationError):
            BudgetCreate(**_base(year=1999))

    def test_year_after_2100_rejected(self):
        with pytest.raises(ValidationError):
            BudgetCreate(**_base(year=2101))

    def test_year_2000_accepted(self):
        schema = BudgetCreate(**_base(year=2000))
        assert schema.year == 2000

    def test_year_2100_accepted(self):
        schema = BudgetCreate(**_base(year=2100))
        assert schema.year == 2100

    # ── category_id ────────────────────────────────────────────────────────

    def test_category_id_required(self):
        with pytest.raises(ValidationError):
            BudgetCreate(amount=Decimal("100"), month=1, year=2026)  # type: ignore[call-arg]

    def test_category_id_non_integer_rejected(self):
        with pytest.raises(ValidationError):
            BudgetCreate(**_base(category_id="evil"))  # type: ignore[arg-type]

    def test_category_id_sql_injection_rejected(self):
        """category_id is an int — non-integer strings must be rejected."""
        with pytest.raises(ValidationError):
            BudgetCreate(**_base(category_id="1; DROP TABLE budgets--"))  # type: ignore[arg-type]


class TestBudgetUpdate:

    def test_all_optional(self):
        schema = BudgetUpdate()
        assert schema.amount is None
        assert schema.month is None
        assert schema.year is None

    def test_amount_only(self):
        schema = BudgetUpdate(amount=Decimal("800.00"))
        assert schema.amount == Decimal("800.00")

    def test_zero_amount_rejected(self):
        with pytest.raises(ValidationError):
            BudgetUpdate(amount=Decimal("0"))

    def test_month_without_year_rejected(self):
        """Both month and year must be provided together or not at all."""
        with pytest.raises(ValidationError, match="together"):
            BudgetUpdate(month=3)

    def test_year_without_month_rejected(self):
        with pytest.raises(ValidationError, match="together"):
            BudgetUpdate(year=2026)

    def test_month_and_year_together_accepted(self):
        schema = BudgetUpdate(month=6, year=2026)
        assert schema.month == 6
        assert schema.year == 2026

    def test_invalid_month_rejected(self):
        with pytest.raises(ValidationError):
            BudgetUpdate(month=0, year=2026)

    def test_invalid_year_rejected(self):
        with pytest.raises(ValidationError):
            BudgetUpdate(month=1, year=1900)
