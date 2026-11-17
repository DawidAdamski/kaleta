# SPDX-License-Identifier: AGPL-3.0-or-later
"""``scripts/check_doc_links.py`` sees what ``mkdocs build --strict`` fails on.

Plan ``archive-image-links``: the checker skipped image links, so a broken
``![…](../images/…)`` passed ``verify.sh`` and only the Pages workflow caught it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_doc_links.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_doc_links", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_doc_links"] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def checker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The checker pointed at a throwaway repo: ``docs/images/a.svg``, ``src/x.py``, ``deploy/``."""
    module = _load()
    (tmp_path / "docs" / "images").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "archive").mkdir(parents=True)
    (tmp_path / "docs" / "images" / "a.svg").write_text("<svg/>")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("")
    (tmp_path / "deploy").mkdir()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "DOCS_DIR", tmp_path / "docs")
    return module


def _errors(checker: ModuleType, page: Path, text: str) -> list[str]:
    page.write_text(text, encoding="utf-8")
    cache: dict[Path, set[str]] = {}
    found = [checker.check_link(ref, cache) for ref in checker.extract_links(page)]
    return [err for err in found if err]


def test_a_broken_image_link_is_an_error_with_file_and_line(checker: ModuleType) -> None:
    page = checker.DOCS_DIR / "plans" / "archive" / "p.md"
    errors = _errors(checker, page, "# P\n\nSee:\n\n![flow](../images/a.svg)\n")
    assert errors == [
        "docs/plans/archive/p.md:5: missing target `../images/a.svg` (from `../images/a.svg`)"
    ]


def test_a_working_image_link_passes(checker: ModuleType) -> None:
    page = checker.DOCS_DIR / "plans" / "archive" / "p.md"
    assert _errors(checker, page, "![flow](../../images/a.svg)\n") == []


def test_external_and_data_images_are_skipped(checker: ModuleType) -> None:
    page = checker.DOCS_DIR / "p.md"
    text = "![w](https://example.com/a.png)\n![d](data:image/png;base64,AA)\n"
    assert _errors(checker, page, text) == []


def test_links_inside_code_are_not_links(checker: ModuleType) -> None:
    page = checker.DOCS_DIR / "p.md"
    text = "The pattern `![alt](gone.svg)` is code.\n\n```\n[x](gone.md)\n```\n"
    assert _errors(checker, page, text) == []


def test_a_docs_page_linking_a_file_outside_docs_is_an_error(checker: ModuleType) -> None:
    page = checker.DOCS_DIR / "p.md"
    assert _errors(checker, page, "[code](../src/x.py)\n") == [
        "docs/p.md:1: `../src/x.py` points at a file outside docs/, which mkdocs cannot serve"
    ]


def test_a_directory_outside_docs_stays_allowed(checker: ModuleType) -> None:
    page = checker.DOCS_DIR / "p.md"
    assert _errors(checker, page, "[manifests](../deploy/)\n") == []


def test_a_root_readme_may_still_link_into_the_repo(checker: ModuleType) -> None:
    page = checker.ROOT / "README.md"
    assert _errors(checker, page, "[code](src/x.py)\n![a](docs/images/a.svg)\n") == []
