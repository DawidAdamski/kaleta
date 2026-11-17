# SPDX-License-Identifier: AGPL-3.0-or-later
"""``scripts/plan_links.py``: a plan's links survive the move into ``docs/plans/archive/``.

Plan ``archive-image-links``: the archiver skipped image links, so three archived plans kept
``../images/import-ui-vs-api.svg`` and ``mkdocs build --strict`` failed on every push.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "plan_links.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("plan_links", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan_links = _load()


@pytest.fixture
def plans_dir(tmp_path: Path) -> Path:
    plans = tmp_path / "docs" / "plans"
    (plans / "archive").mkdir(parents=True)
    (plans / "b.svg").write_text("<svg/>")
    (plans / "sibling-draft.md").write_text("# draft\n")
    (plans / "archive" / "old-plan.md").write_text("# old\n")
    return plans


def _rewrite(plans_dir: Path, text: str) -> str:
    return str(plan_links.PlanLinkRewriter(plans_dir).rewrite(text))


def test_image_links_move_down_one_directory(plans_dir: Path) -> None:
    text = "![x](../images/a.svg)\n![y](b.svg)\n"
    assert _rewrite(plans_dir, text) == "![x](../../images/a.svg)\n![y](../b.svg)\n"


def test_text_links_keep_their_rules(plans_dir: Path) -> None:
    text = (
        "[roadmap](../roadmap.md#q4)\n"
        "[draft](sibling-draft.md)\n"
        "[old](archive/old-plan.md)\n"
        "[same](old-plan.md)\n"
        "[here](#intent)\n"
        "[web](https://example.com/a.svg)\n"
    )
    assert _rewrite(plans_dir, text) == (
        "[roadmap](../../roadmap.md#q4)\n"
        "[draft](../sibling-draft.md)\n"
        "[old](old-plan.md)\n"
        "[same](old-plan.md)\n"
        "[here](#intent)\n"
        "[web](https://example.com/a.svg)\n"
    )


def test_external_and_unknown_image_targets_are_left_alone(plans_dir: Path) -> None:
    text = (
        "![web](https://example.com/a.png)\n![gone](missing.svg)\n![d](data:image/png;base64,AA)\n"
    )
    assert _rewrite(plans_dir, text) == text


def test_roadmap_ref_in_frontmatter_gains_a_level(plans_dir: Path) -> None:
    text = "---\nroadmap_ref: ../roadmap.md\n---\n"
    assert _rewrite(plans_dir, text) == "---\nroadmap_ref: ../../roadmap.md\n---\n"


def test_cli_rewrites_the_plan_in_place(plans_dir: Path) -> None:
    plan = plans_dir / "my-plan.md"
    plan.write_text("![x](../images/a.svg)\n![y](b.svg)\n", encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPT), str(plan)], check=True)
    assert plan.read_text(encoding="utf-8") == "![x](../../images/a.svg)\n![y](../b.svg)\n"
