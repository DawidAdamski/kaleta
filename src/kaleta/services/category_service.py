# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import LoaderOption

from kaleta.db.types import exact_index
from kaleta.exceptions import ConflictError, KaletaError, NotFoundError
from kaleta.models.category import Category, CategoryType
from kaleta.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from kaleta.seeders.catalog import SUBSCRIPTION_CHILDREN as SUBSCRIPTION_PURPOSE_CHILDREN_PL
from kaleta.services.text_order import by_name

# Maximum category nesting depth supported by the UI (root → child).
_CATEGORY_TREE_DEPTH = 2


def _category_tree_load_options(depth: int = _CATEGORY_TREE_DEPTH) -> LoaderOption:
    """Eager-load nested ``children`` up to *depth* levels for safe DTO conversion."""
    loader = selectinload(Category.children)
    for _ in range(depth - 1):
        loader = loader.selectinload(Category.children)
    return loader


#: Billing-period children the Subscriptions tree once shipped
#: (``subscriptions-categories``), English and Polish default names — *only* the
#: ones with no purpose meaning. "Other"/"Inne" are deliberately absent: they are
#: the catch-all in both the old cadence tree and the new purpose tree, so an empty
#: one is kept, not retired. An unreferenced cadence child is retired when the
#: purpose children are ensured.
SUBSCRIPTION_CADENCE_CHILDREN: tuple[str, ...] = (
    "Monthly",
    "Yearly",
    "Miesięczne",
    "Roczne",
)

#: The Subscriptions tree's purpose children (``subscriptions-categories``), English —
#: the default this service ensures for a family. The Polish example data uses
#: ``seeders.catalog.SUBSCRIPTION_CHILDREN``.
SUBSCRIPTION_PURPOSE_CHILDREN: tuple[str, ...] = (
    "Streaming",
    "Music & audio",
    "Software & apps",
    "Phone & internet",
    "News & reading",
    "Fitness & health",
    "Cloud & backup",
    "Other",
)


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, type: CategoryType | None = None) -> builtins.list[Category]:
        """Return all categories (flat), children eagerly loaded."""
        stmt = select(Category).options(_category_tree_load_options())
        if type is not None:
            stmt = stmt.where(Category.type == type)
        result = await self.session.execute(stmt)
        return by_name(result.scalars().all())

    async def list_roots(self, type: CategoryType | None = None) -> builtins.list[Category]:
        """Return only top-level categories with children eagerly loaded."""
        stmt = (
            select(Category)
            .options(_category_tree_load_options())
            .where(Category.parent_id.is_(None))
        )
        if type is not None:
            stmt = stmt.where(Category.type == type)
        result = await self.session.execute(stmt)
        return by_name(result.scalars().all())

    async def list_tree(self, type: CategoryType | None = None) -> builtins.list[CategoryResponse]:
        """Return root categories as response DTOs with nested children fully loaded."""
        roots = await self.list_roots(type=type)
        return [CategoryResponse.model_validate(r) for r in roots]

    async def get(self, category_id: int) -> Category | None:
        result = await self.session.execute(
            select(Category)
            .options(_category_tree_load_options())
            .where(Category.id == category_id)
        )
        return result.scalar_one_or_none()

    async def _assert_type_matches_parent(
        self, *, parent_id: int | None, category_type: CategoryType
    ) -> None:
        """Reject mixed-type subtrees (child type must equal parent type)."""
        if parent_id is None:
            return
        parent = await self.get(parent_id)
        if parent is None:
            raise NotFoundError(f"Parent category id={parent_id} not found")
        if parent.type != category_type:
            raise ConflictError(
                f"Category type '{category_type.value}' must match parent type "
                f"'{parent.type.value}'"
            )

    async def _assert_unique_name(
        self,
        *,
        name: str,
        parent_id: int | None,
        category_type: CategoryType,
        exclude_id: int | None = None,
    ) -> None:
        # A unique constraint treats NULL != NULL, so enforce
        # (name, parent_id, type) uniqueness manually for root categories.
        stmt = select(Category).where(
            Category.name_bidx == exact_index(name),
            Category.type == category_type,
        )
        if parent_id is None:
            stmt = stmt.where(Category.parent_id.is_(None))
        else:
            stmt = stmt.where(Category.parent_id == parent_id)
        if exclude_id is not None:
            stmt = stmt.where(Category.id != exclude_id)
        existing = await self.session.execute(stmt)
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(f"Category name '{name}' already exists under the same parent")

    async def create(self, data: CategoryCreate) -> Category:
        await self._assert_type_matches_parent(parent_id=data.parent_id, category_type=data.type)
        await self._assert_unique_name(
            name=data.name,
            parent_id=data.parent_id,
            category_type=data.type,
        )
        category = Category(**data.model_dump())
        self.session.add(category)
        await self.session.commit()
        # Re-fetch with eager-loaded children so the response serializer never
        # hits a lazy relationship outside of an async context.
        fetched = await self.get(category.id)
        if fetched is None:
            raise KaletaError(f"Category id={category.id} not found after commit")
        return fetched

    async def update(self, category_id: int, data: CategoryUpdate) -> Category | None:
        category = await self.get(category_id)
        if category is None:
            return None
        updates = data.model_dump(exclude_unset=True)
        effective_name = updates.get("name", category.name)
        effective_parent_id = updates.get("parent_id", category.parent_id)
        effective_type = updates.get("type", category.type)
        await self._assert_type_matches_parent(
            parent_id=effective_parent_id,
            category_type=effective_type,
        )
        await self._assert_unique_name(
            name=effective_name,
            parent_id=effective_parent_id,
            category_type=effective_type,
            exclude_id=category_id,
        )
        for field, value in updates.items():
            setattr(category, field, value)
        await self.session.commit()
        # Re-fetch with selectinload so children are available for serialization.
        return await self.get(category_id)

    async def delete(self, category_id: int) -> bool:
        category = await self.get(category_id)
        if category is None:
            return False
        await self.session.delete(category)
        await self.session.commit()
        return True

    @staticmethod
    def sort_with_children(categories: builtins.list[Category]) -> builtins.list[Category]:
        """Return categories sorted so each parent is immediately followed by its children."""
        children_by_parent: dict[int, list[Category]] = {}
        for category in categories:
            if category.parent_id:
                children_by_parent.setdefault(category.parent_id, []).append(category)
        result: builtins.list[Category] = []
        for parent in sorted((c for c in categories if c.parent_id is None), key=lambda c: c.name):
            result.append(parent)
            for child in sorted(children_by_parent.get(parent.id, []), key=lambda c: c.name):
                result.append(child)
        return result

    @staticmethod
    def build_option_labels(categories: builtins.list[Category]) -> dict[int, str]:
        """Build ``{id: label}`` with hierarchical labels like ``Fuel → Toyota``."""
        cats_by_id = {c.id: c for c in categories}
        result: dict[int, str] = {}
        roots = sorted(
            [c for c in categories if c.parent_id is None or c.parent_id not in cats_by_id],
            key=lambda c: c.name,
        )
        for root in roots:
            result[root.id] = root.name
            children = sorted(
                [c for c in categories if c.parent_id == root.id],
                key=lambda c: c.name,
            )
            for child in children:
                result[child.id] = f"{root.name} \u2192 {child.name}"
        return result

    # ── Subscriptions-tree helpers ────────────────────────────────────────

    async def get_subscriptions_root(self) -> Category | None:
        """Return the single root category flagged as the Subscriptions tree."""
        result = await self.session.execute(
            select(Category)
            .options(_category_tree_load_options())
            .where(Category.is_subscriptions_root.is_(True))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_subscription_children(self) -> builtins.list[Category]:
        """Direct children of the Subscriptions root, ordered by name.

        Returns an empty list if the root doesn't exist yet.
        """
        root = await self.get_subscriptions_root()
        if root is None:
            return []
        result = await self.session.execute(select(Category).where(Category.parent_id == root.id))
        return by_name(result.scalars().all())

    async def subscription_category_ids(self) -> set[int]:
        """Return the id set: root + every direct child. Used as a membership test."""
        root = await self.get_subscriptions_root()
        if root is None:
            return set()
        ids = {root.id}
        result = await self.session.execute(
            select(Category.id).where(Category.parent_id == root.id)
        )
        ids.update(result.scalars().all())
        return ids

    #: Blind indexes of the purpose children that are *unique* to the new scheme —
    #: both locales, minus the shared "Other"/"Inne" catch-all. Their presence is the
    #: signal that a tree is already organised by purpose, so a second locale's set is
    #: never added beside it (``subscriptions-categories``).
    @staticmethod
    def _distinct_purpose_bidx() -> set[str | None]:
        shared = {exact_index("Other"), exact_index("Inne")}
        names = (*SUBSCRIPTION_PURPOSE_CHILDREN, *SUBSCRIPTION_PURPOSE_CHILDREN_PL)
        return {exact_index(name) for name in names} - shared

    @staticmethod
    def default_purpose_children(language: str) -> builtins.list[str]:
        """The purpose child names a fresh tree is seeded with, in *language*."""
        if language.startswith("pl"):
            return list(SUBSCRIPTION_PURPOSE_CHILDREN_PL)
        return list(SUBSCRIPTION_PURPOSE_CHILDREN)

    async def ensure_subscriptions_root_and_children(
        self, child_names: builtins.list[str] | None = None
    ) -> Category:
        """Create the Subscriptions root + default children if missing.

        Idempotent — safe to call from seeds. The default children are the English
        purpose names; a caller that knows the family's language passes its own
        (``child_names``). A tree that already carries purpose children in *any*
        language is left as it is — adding a second locale's set would show every
        group twice. Returns the root.
        """
        root = await self.get_subscriptions_root()
        if root is None:
            root = Category(
                name="Subscriptions",
                type=CategoryType.EXPENSE,
                is_subscriptions_root=True,
            )
            self.session.add(root)
            await self.session.commit()
            await self.session.refresh(root)
        defaults = child_names if child_names is not None else list(SUBSCRIPTION_PURPOSE_CHILDREN)
        existing = await self.list_subscription_children()
        # Match by blind index, not the raw name: it is encryption- and
        # case-stable, so a re-run never files a child twice.
        filed = {c.name_bidx for c in existing}
        if not (filed & self._distinct_purpose_bidx()):
            for name in defaults:
                if exact_index(name) not in filed:
                    self.session.add(
                        Category(name=name, type=CategoryType.EXPENSE, parent_id=root.id)
                    )
            await self.session.commit()
        await self._prune_empty_cadence_children(root.id)
        return await self.get(root.id)  # type: ignore[return-value]

    async def _prune_empty_cadence_children(self, root_id: int) -> None:
        """Remove a shipped cadence child nobody renamed, filed a charge under, or nested.

        The old billing-period children (``subscriptions-categories``). A child a
        member edited (a different name), or that anything references, is theirs and
        stays. Matched by blind index, so it works without the name in the clear. The
        shared "Other"/"Inne" catch-all is not a cadence name, so it is never removed.
        """
        cadence = {exact_index(name) for name in SUBSCRIPTION_CADENCE_CHILDREN}
        children = await self.session.execute(select(Category).where(Category.parent_id == root_id))
        removed = False
        for child in children.scalars():
            if child.name_bidx in cadence and not await self._category_is_referenced(child.id):
                await self.session.delete(child)
                removed = True
        if removed:
            await self.session.commit()

    async def _category_is_referenced(self, category_id: int) -> bool:
        """Whether any row anywhere points at this category (so it must not be removed)."""
        from kaleta.models.budget import Budget
        from kaleta.models.categorisation_rule import CategorisationRule
        from kaleta.models.irregular_item import IrregularItem
        from kaleta.models.planned_transaction import PlannedTransaction
        from kaleta.models.reserve_fund import ReserveFund
        from kaleta.models.subscription import Subscription
        from kaleta.models.transaction import Transaction, TransactionSplit

        checks = (
            (Category.id, Category.parent_id == category_id),
            (Transaction.id, Transaction.category_id == category_id),
            (TransactionSplit.id, TransactionSplit.category_id == category_id),
            (Budget.id, Budget.category_id == category_id),
            (PlannedTransaction.id, PlannedTransaction.category_id == category_id),
            (Subscription.id, Subscription.category_id == category_id),
            (CategorisationRule.id, CategorisationRule.category_id == category_id),
            (ReserveFund.id, ReserveFund.backing_category_id == category_id),
            (IrregularItem.id, IrregularItem.category_id == category_id),
        )
        for col, where in checks:
            found = await self.session.execute(select(col).where(where).limit(1))
            if found.first() is not None:
                return True
        return False
