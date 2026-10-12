# SPDX-License-Identifier: AGPL-3.0-or-later
"""Category templates — a described life merged into the tree (``category-templates``).

Slice 1 (the engine): applying a template adds its parent/child categories, several
templates combine by merging under a shared parent, a repeatable template makes one
subtree per named copy, and the Company template seeds its business purposes under the
Subscriptions tree. All idempotent by blind index.
"""

from __future__ import annotations

from sqlalchemy import select

from kaleta.models.category import Category, CategoryType
from kaleta.schemas.category_template import TemplateSelection
from kaleta.services import CategoryService, CategoryTemplateService
from tests.conftest import make_session_factory


async def _roots(session, type: CategoryType = CategoryType.EXPENSE) -> list[Category]:
    # name is an EncryptedText column (random ciphertext), so it cannot be filtered in
    # SQL — load the roots and compare the decrypted name in Python.
    result = await session.execute(
        select(Category).where(Category.parent_id.is_(None), Category.type == type)
    )
    return list(result.scalars().all())


async def _root(session, name: str, type: CategoryType = CategoryType.EXPENSE) -> Category | None:
    return next((c for c in await _roots(session, type) if c.name == name), None)


async def _child_names(session, parent: Category) -> set[str]:
    result = await session.execute(select(Category).where(Category.parent_id == parent.id))
    return {c.name for c in result.scalars().all()}


def _sel(key: str, copy_name: str | None = None) -> TemplateSelection:
    return TemplateSelection(key=key, copy_name=copy_name)


async def test_applying_a_template_creates_its_categories(db_engine) -> None:
    """Covers: KAL-CTP-001"""
    async with make_session_factory(db_engine)() as session:
        result = await CategoryTemplateService(session).apply([_sel("single")])
        assert result.created > 0

        housing = await _root(session, "Mieszkanie")
        assert housing is not None
        assert await _child_names(session, housing) == {"Czynsz", "Media", "Internet i telefon"}
        income = await _root(session, "Przychody", CategoryType.INCOME)
        assert income is not None
        assert await _child_names(session, income) == {"Wynagrodzenie", "Inne przychody"}


async def test_combining_templates_merges_a_shared_parent(db_engine) -> None:
    """Covers: KAL-CTP-002

    Single and Family both file under "Codzienne życie"; applying both leaves one such
    parent with the union of their children (``Żywność`` once).
    """
    async with make_session_factory(db_engine)() as session:
        svc = CategoryTemplateService(session)
        await svc.apply([_sel("single"), _sel("family")])

        everyday = [c for c in await _roots(session) if c.name == "Codzienne życie"]
        assert len(everyday) == 1
        assert await _child_names(session, everyday[0]) == {
            "Żywność",
            "Transport",
            "Zdrowie",
            "Rozrywka",
            "Chemia i higiena",
        }


async def test_applying_twice_adds_nothing(db_engine) -> None:
    """Covers: KAL-CTP-003"""
    async with make_session_factory(db_engine)() as session:
        svc = CategoryTemplateService(session)
        first = await svc.apply([_sel("single")])
        second = await svc.apply([_sel("single")])
        assert first.created > 0
        assert second.created == 0

        housing = [c for c in await _roots(session) if c.name == "Mieszkanie"]
        assert len(housing) == 1


async def test_a_repeatable_template_makes_one_subtree_per_copy(db_engine) -> None:
    """Covers: KAL-CTP-004

    Two cars named Skoda and Toyota give two parents, each with the car children.
    """
    async with make_session_factory(db_engine)() as session:
        svc = CategoryTemplateService(session)
        await svc.apply([_sel("car", "Skoda"), _sel("car", "Toyota")])

        skoda = await _root(session, "Samochód: Skoda")
        toyota = await _root(session, "Samochód: Toyota")
        assert skoda is not None and toyota is not None
        assert "Paliwo" in await _child_names(session, skoda)
        assert "Paliwo" in await _child_names(session, toyota)
        assert await _root(session, "Samochód") is None  # no bare, unnamed copy


async def test_company_seeds_business_subscription_purposes(db_engine) -> None:
    """Covers: KAL-CTP-005

    Company adds its business purposes under the Subscriptions tree; two companies do
    not double them (the purpose is shared across copies).
    """
    async with make_session_factory(db_engine)() as session:
        svc = CategoryTemplateService(session)
        await svc.apply([_sel("company", "A"), _sel("company", "B")])

        root = await CategoryService(session).get_subscriptions_root()
        assert root is not None
        children = await _child_names(session, root)
        business = {
            "Hosting i domeny",
            "Oprogramowanie firmowe",
            "Księgowość i fakturowanie",
            "Marketing i reklama",
        }
        assert business <= children
        # Each business purpose appears exactly once, not once per company.
        rows = (
            (await session.execute(select(Category.name).where(Category.parent_id == root.id)))
            .scalars()
            .all()
        )
        assert len(rows) == len(set(rows))


async def test_preview_reports_additions_without_creating(db_engine) -> None:
    """Covers: KAL-CTP-006"""
    async with make_session_factory(db_engine)() as session:
        svc = CategoryTemplateService(session)
        before = await svc.preview([_sel("single")])
        assert before.to_add > 0
        assert all(not r.exists for r in before.rows)  # nothing exists yet

        # Preview did not write anything.
        count = (await session.execute(select(Category))).scalars().all()
        assert count == []

        await svc.apply([_sel("single")])
        after = await svc.preview([_sel("single")])
        assert after.to_add == 0
        assert all(r.exists for r in after.rows)


async def test_preview_counts_every_child_of_two_car_copies(db_engine) -> None:
    """Covers: KAL-CTP-004

    Regression: two new parents share child names ("Paliwo"), but each copy is its own
    subtree, so every row must read as an addition — not deduped by a null parent id.
    """
    async with make_session_factory(db_engine)() as session:
        preview = await CategoryTemplateService(session).preview(
            [_sel("car", "Skoda"), _sel("car", "Toyota")]
        )
        assert all(not r.exists for r in preview.rows)
        # Two parents + 2 × 6 children, all to add.
        assert preview.to_add == len(preview.rows) == 14


async def test_preview_lists_business_purposes_once_for_two_companies(db_engine) -> None:
    """Covers: KAL-CTP-005"""
    async with make_session_factory(db_engine)() as session:
        preview = await CategoryTemplateService(session).preview(
            [_sel("company", "A"), _sel("company", "B")]
        )
        sub_rows = [r for r in preview.rows if "Subskrypcje" in r.label]
        # The 4 business purposes are shared across copies: added once, not twice.
        assert sum(1 for r in sub_rows if not r.exists) == 4


async def test_blank_copy_name_is_not_suffixed(db_engine) -> None:
    """Covers: KAL-CTP-004 — a whitespace copy name must not make "Samochód: "."""
    async with make_session_factory(db_engine)() as session:
        await CategoryTemplateService(session).apply([_sel("car", "   ")])
        assert await _root(session, "Samochód") is not None
        assert await _root(session, "Samochód: ") is None


async def test_business_purposes_use_the_requested_language(db_engine) -> None:
    """Covers: KAL-CTP-005

    Applying Company in English onto a Polish-seeded Subscriptions tree adds the English
    business purposes beside the Polish defaults — accepted; the Slice 2 view passes the
    family's language so this does not happen in practice.
    """
    async with make_session_factory(db_engine)() as session:
        categories = CategoryService(session)
        await categories.ensure_subscriptions_root_and_children(
            CategoryService.default_purpose_children("pl")
        )
        await CategoryTemplateService(session).apply([_sel("company")], language="en")

        root = await categories.get_subscriptions_root()
        assert root is not None
        children = await _child_names(session, root)
        assert "Hosting & domains" in children  # English business purpose added
        assert "Streaming wideo" in children  # Polish default left in place
