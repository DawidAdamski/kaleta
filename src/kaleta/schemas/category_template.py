# SPDX-License-Identifier: AGPL-3.0-or-later
"""Category templates — a described life (single, family, company, car, …) as a
set of categories to merge into the tree (``category-templates``).

The catalogue is data (TOML under ``kaleta/data/category_templates``), validated
by these schemas. Each template carries both Polish and English names; the caller
picks the language, the way the Subscriptions tree does.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from kaleta.schemas.category import CategoryType

__all__ = [
    "CategoryTemplate",
    "TemplateApplyResult",
    "TemplateGroup",
    "TemplatePreviewResult",
    "TemplatePreviewRow",
    "TemplateSelection",
]


class TemplateSelection(BaseModel):
    """One picked template, with a per-copy name for a repeatable one.

    ``copy_name`` distinguishes copies — "Skoda", "Toyota" for two cars — and is
    ignored for a template that is not ``repeatable``.
    """

    key: str
    copy_name: str | None = None


class TemplateGroup(BaseModel):
    """One parent category of a template and the children filed under it."""

    type: CategoryType
    name: str
    name_en: str
    children: list[str] = Field(default_factory=list)
    children_en: list[str] = Field(default_factory=list)

    def parent_name(self, language: str) -> str:
        return self.name if language.startswith("pl") else self.name_en

    def child_names(self, language: str) -> list[str]:
        return self.children if language.startswith("pl") else self.children_en


class CategoryTemplate(BaseModel):
    """A whole template: its groups, and (Company only) subscription purposes."""

    key: str
    name: str
    name_en: str
    #: Where it sits in the picker; lower first.
    order: int = 100
    #: A repeatable template (a car, a company) takes a per-copy name on apply,
    #: so "Samochód" becomes "Samochód: Skoda" and each copy is its own subtree.
    repeatable: bool = False
    groups: list[TemplateGroup] = Field(default_factory=list)
    #: Purpose children added under the Subscriptions tree (Company — see #219).
    subscriptions: list[str] = Field(default_factory=list)
    subscriptions_en: list[str] = Field(default_factory=list)

    def display_name(self, language: str) -> str:
        return self.name if language.startswith("pl") else self.name_en

    def subscription_children(self, language: str) -> list[str]:
        return self.subscriptions if language.startswith("pl") else self.subscriptions_en


class TemplatePreviewRow(BaseModel):
    """One line of a preview: a category the apply would add, or that already exists."""

    #: ``"Parent"`` for a root, ``"Parent → Child"`` for a child.
    label: str
    type: CategoryType
    exists: bool


class TemplatePreviewResult(BaseModel):
    """What applying the chosen templates (in order) would add to the tree."""

    keys: list[str]
    rows: list[TemplatePreviewRow]

    @property
    def to_add(self) -> int:
        return sum(1 for r in self.rows if not r.exists)


class TemplateApplyResult(BaseModel):
    """How many categories were actually created (idempotent — a re-run adds 0)."""

    keys: list[str]
    created: int
