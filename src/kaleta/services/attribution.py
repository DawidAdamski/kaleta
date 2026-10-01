# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stamp new user-owned rows with the member who created them.

In a hosted household (ADR-35) every member has a ``users`` row in the tenant
schema, and ``TenantContext.member_user_id`` says which one is acting. The
``user_id`` column of ``UserOwnedMixin`` tables records *who added this* — it
is attribution, not access control: every member of a household sees every row.

One flush hook rather than a line in each service's ``create``: a service that
forgot would silently lose attribution, and nothing would notice. A row whose
``user_id`` was set explicitly keeps it. Without a tenant context (every
single-tenant install) this does nothing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from kaleta.db.tenant_context import current_tenant
from kaleta.models.mixins import UserOwnedMixin


@event.listens_for(Session, "before_flush")
def _attribute_new_rows(session: Session, _flush_context: Any, _instances: Any) -> None:
    new_owned = [obj for obj in session.new if isinstance(obj, UserOwnedMixin)]
    if not new_owned:
        return
    ctx = current_tenant()
    if ctx is None or ctx.member_user_id is None:
        return
    for obj in new_owned:
        if obj.user_id is None:
            obj.user_id = ctx.member_user_id
