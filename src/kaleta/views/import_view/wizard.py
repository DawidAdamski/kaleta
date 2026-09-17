# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which step the import page shows, and how you move between them.

``state.current_step`` answers *where the work is*: the step the file is
waiting on. This module answers *where the reader is* — which is not the
same thing, because a wizard you cannot walk back through is a wizard you
restart to fix a typo.

The two are tied by one rule, and it is the whole of the navigation: you
may look at any step up to and including the one the work is on, and
``Continue`` is what moves you forward, so it is enabled exactly while
there is a finished step in front of you.
"""

from __future__ import annotations

from kaleta.i18n import t
from kaleta.views.import_view.state import (
    STEP_CONFIRM,
    STEP_FORMAT,
    STEP_MAPPING,
    STEP_PREVIEW,
    STEP_SETTINGS,
    STEP_UPLOAD,
    QueuedFile,
)

#: Every step, in order. The tuple the progress line numbers.
ALL_STEPS: tuple[int, ...] = (
    STEP_FORMAT,
    STEP_UPLOAD,
    STEP_MAPPING,
    STEP_SETTINGS,
    STEP_PREVIEW,
    STEP_CONFIRM,
)

#: The i18n key naming each step, by step number.
STEP_LABEL_KEYS: dict[int, str] = {
    STEP_FORMAT: "import.step_format",
    STEP_UPLOAD: "import.step_upload",
    STEP_MAPPING: "import.step_mapping",
    STEP_SETTINGS: "import.step_settings",
    STEP_PREVIEW: "import.step_preview",
    STEP_CONFIRM: "import.step_confirm",
}


def steps_for(active: QueuedFile | None) -> tuple[int, ...]:
    """The steps this file actually has.

    A bank profile (mbank, pko, wise) has no mapping step — its columns are
    the profile's, not the user's — so ``Continue`` from Upload lands on
    Settings and ``Back`` from Settings returns to Upload. The node stays
    ticked, which is what ``current_step`` already claims for it: the
    columns *were* mapped, by the profile rather than by hand.
    """
    if active is None or active.profile == "generic":
        return ALL_STEPS
    return tuple(step for step in ALL_STEPS if step != STEP_MAPPING)


def next_step(viewed: int, steps: tuple[int, ...]) -> int:
    """The step after *viewed*, or *viewed* when it is the last one."""
    later = [step for step in steps if step > viewed]
    return later[0] if later else viewed


def prev_step(viewed: int, steps: tuple[int, ...]) -> int:
    """The step before *viewed*, or *viewed* when it is the first one."""
    earlier = [step for step in steps if step < viewed]
    return earlier[-1] if earlier else viewed


def clamp_viewed(viewed: int, reachable: int, steps: tuple[int, ...]) -> int:
    """Keep the reader on a step that exists and that the work has reached.

    Two things move under a reader who is standing still: a profile change
    can take the mapping step away beneath them, and an edit can send the
    work backwards — unmapping a column on a file that was ready drops
    ``current_step`` from Preview to Mapping, and a Preview card for a file
    that no longer parses is a page lying about itself.

    The nearest allowed step *forward* wins where there is one, which is the
    profile case: switching the file switcher from a generic file on Mapping
    to a bank-profile file lands on Settings rather than dropping back to
    Upload, where the switcher they just used is not even shown. Falling
    back is for the other case, where there is nothing ahead to fall to.
    """
    allowed = [step for step in steps if step <= reachable]
    if not allowed:
        return steps[0]
    if viewed in allowed:
        return viewed
    later = [step for step in allowed if step > viewed]
    if later:
        return later[0]
    earlier = [step for step in allowed if step < viewed]
    return earlier[-1] if earlier else allowed[0]


def can_continue(viewed: int, reachable: int, steps: tuple[int, ...]) -> bool:
    """Is there a finished step in front of the reader?

    ``viewed < reachable`` and not already on the last step. Nothing here
    decides readiness of its own: ``current_step`` is what knows whether a
    step is done, and it is the same answer the progress line draws.
    """
    return viewed < reachable and next_step(viewed, steps) != viewed


def continue_blocked_reason(
    active: QueuedFile | None,
    viewed: int,
    reachable: int,
    *,
    settings_reason: str | None = None,
) -> str | None:
    """Why ``Continue`` cannot leave this step, in the page's own words.

    ``None`` when it can. Otherwise the message that is already the answer —
    "Choose an account" on Settings, "Date column is required." on Mapping —
    because a button that refuses without saying why is the thing this
    wizard would be worst at. The settings message comes from the caller:
    it is the service's own readiness check, which is what decides whether
    the step is finished in the first place.
    """
    if viewed < reachable:
        return None
    if viewed >= ALL_STEPS[-1]:
        return None
    if active is None:
        return t("import.blocked_no_file")
    if viewed == STEP_SETTINGS and settings_reason is not None:
        return settings_reason
    if active.status_msg:
        return active.status_msg
    return t("import.blocked_step")
