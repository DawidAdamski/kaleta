# SPDX-License-Identifier: AGPL-3.0-or-later
"""The category-template catalogue loads and is well-formed (``category-templates``).

Covers: KAL-CTP-001
"""

from __future__ import annotations

from kaleta.services import CategoryTemplateService

_EXPECTED_KEYS = {
    "single",
    "family",
    "company",
    "car",
    "home",
    "rental",
    "pets",
    "student",
}


def test_catalogue_loads_every_template() -> None:
    """Covers: KAL-CTP-001"""
    keys = {t.key for t in CategoryTemplateService.list()}
    assert keys == _EXPECTED_KEYS


def test_templates_are_ordered_and_named_in_both_languages() -> None:
    templates = CategoryTemplateService.list()
    assert [t.order for t in templates] == sorted(t.order for t in templates)
    for t in templates:
        assert t.name and t.name_en
        assert t.groups, f"{t.key} has no groups"
        for group in t.groups:
            # Every group names the same count of children in both languages.
            assert len(group.children) == len(group.children_en), t.key


def test_company_carries_business_subscription_purposes() -> None:
    """Covers: KAL-CTP-005"""
    company = CategoryTemplateService.get("company")
    assert company.repeatable is True
    assert len(company.subscription_children("pl")) == 4
    assert len(company.subscription_children("en")) == 4


def test_only_car_and_company_are_repeatable() -> None:
    repeatable = {t.key for t in CategoryTemplateService.list() if t.repeatable}
    assert repeatable == {"car", "company"}
