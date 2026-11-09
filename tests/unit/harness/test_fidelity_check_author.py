# SPDX-License-Identifier: AGPL-3.0-or-later
"""``restyle_fidelity.py check`` accepts only a report the independent critic wrote.

Plan ``fidelity-independent-critic``: ``author: critic``; screenshot hashes
equal to the files in ``.fidelity/<id>/``; tiles above the profile's
``[fidelity] tile_threshold`` - or, while it is unset, the three worst tiles -
named by a ``deviation`` row; and a ``fidelity`` record in the run log. The
critic session itself (``claude -p``) is replaced by a stub runner.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]

#: The artboard picture: white. The app differs in D4 (fully), C3 (half) and
#: A1 (a quarter), so the worst three are D4, C3, A1 in that order.
DIFFERENCES = [(300, 300, 400, 400), (200, 200, 300, 250), (0, 0, 50, 50)]


def _row(element: str, status: str = "match", note: str = "") -> dict[str, str]:
    return {"element": element, "artboard": "12px", "app": "12px", "status": status, "note": note}


def _rows(*extra: dict[str, str]) -> list[dict[str, str]]:
    return [_row(f"Element {n}") for n in range(1, 9)] + list(extra)


NAMING_ALL_THREE = _row(
    "Sample text", "deviation", "tiles D4, C3 and A1: seeded payees, not the artboard's sample"
)


class Stub:
    """A critic runner that returns canned rows and remembers what it was asked."""

    def __init__(self, rows: list[dict[str, str]], run_id: str = "run-1") -> None:
        self.rows = rows
        self.run_id = run_id
        self.calls: list[tuple[str, str, str]] = []

    def __call__(
        self, prompt: str, model: str, tools: str, raw: Path
    ) -> tuple[dict[str, Any], str]:
        self.calls.append((prompt, model, tools))
        return {"rows": self.rows}, self.run_id


@pytest.fixture
def setup(fidelity: ModuleType, picture: Callable[..., Path], tmp_path: Path) -> Callable[..., Any]:
    """``setup(threshold=None)``: shots on disk and a stamped report, for artboard 2a."""

    def make(threshold: float | None = None) -> Any:
        picture("shots/2a/artboard.png")
        picture("shots/2a/app-1360.png", black=DIFFERENCES)
        profile = tmp_path / "profile.toml"
        profile.write_text(
            "[fidelity]\n" + (f"tile_threshold = {threshold}\n" if threshold is not None else ""),
            encoding="utf-8",
        )
        report = fidelity.Report(
            fidelity.BY_ID["2a"],
            report_dir=tmp_path / "reports",
            shot_dir=tmp_path / "shots",
            profile=profile,
        )
        report.stamp(report.measure())
        return report

    return make


def test_a_critic_report_on_the_current_shots_passes(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup()
    stub = Stub(_rows(NAMING_ALL_THREE))

    result = fidelity.Critic("sonnet", runner=stub).critique(report)

    head = report.header(report.path.read_text(encoding="utf-8"))
    assert head["author"] == "critic"
    assert head["critic_run"] == "run-1" == result.run_id
    assert head["critic_model"] == "sonnet"
    assert head["shots"].split()[0].startswith("artboard.png=")
    assert head["diff_whole"] == "10.94"  # (100 + 50 + 25) / 16
    assert "D4=100.00" in head["tiles"]
    assert report.problems() == []


def test_a_freshly_shot_report_is_not_critiqued_yet(setup: Callable[..., Any]) -> None:
    report = setup()

    problems = report.problems()

    assert any("author is 'pending', not 'critic'" in p for p in problems)


def test_a_report_the_implementer_wrote_fails(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup()
    fidelity.Critic("sonnet", runner=Stub(_rows(NAMING_ALL_THREE))).critique(report)
    text = report.path.read_text(encoding="utf-8")
    report.path.write_text(text.replace("author: critic", "author: implementer"), encoding="utf-8")

    problems = report.problems()

    assert problems == [
        (
            "author is 'implementer', not 'critic' - run `critique 2a`; "
            "the implementer does not write the report"
        )
    ]


def test_a_report_from_before_the_critic_has_no_author(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    """The existing hand-written reports carry no ``author`` line at all."""
    report = setup()
    fidelity.Critic("sonnet", runner=Stub(_rows(NAMING_ALL_THREE))).critique(report)
    text = report.path.read_text(encoding="utf-8")
    report.path.write_text(text.replace("author: critic\n", ""), encoding="utf-8")

    assert any("author is 'missing'" in p for p in report.problems())


def test_shots_taken_after_the_critique_fail(
    fidelity: ModuleType, setup: Callable[..., Any], picture: Callable[..., Path]
) -> None:
    report = setup()
    fidelity.Critic("sonnet", runner=Stub(_rows(NAMING_ALL_THREE))).critique(report)
    picture("shots/2a/app-1360.png", black=DIFFERENCES)  # same pixels, re-encoded is fine
    assert report.problems() == []

    picture("shots/2a/app-1360.png", black=[*DIFFERENCES, (0, 300, 100, 400)])
    report.stamp(report.measure())  # a new shoot updates the tiles

    problems = report.problems()

    assert any("not the ones the critic saw" in p for p in problems)


def test_missing_screenshots_fail_with_the_shoot_advice(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup()
    fidelity.Critic("sonnet", runner=Stub(_rows(NAMING_ALL_THREE))).critique(report)
    (report.shots / "app-1360.png").unlink()

    assert any("no app-1360.png" in p and "run `shoot 2a`" in p for p in report.problems())


def test_tiles_edited_in_the_header_fail(fidelity: ModuleType, setup: Callable[..., Any]) -> None:
    report = setup()
    fidelity.Critic("sonnet", runner=Stub(_rows(NAMING_ALL_THREE))).critique(report)
    text = report.path.read_text(encoding="utf-8")
    report.path.write_text(text.replace("D4=100.00", "D4=1.00"), encoding="utf-8")

    assert "the report's tiles do not match the screenshots - shoot and critique" in (
        report.problems()
    )


def test_without_a_threshold_the_three_worst_tiles_must_be_named(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup()
    rows = _rows(_row("Sample text", "deviation", "tile D4: seeded payees"))
    fidelity.Critic("sonnet", runner=Stub(rows)).critique(report)

    problems = report.problems()

    assert problems == [
        "tile C3 differs by 50.00% and no deviation row names it",
        "tile A1 differs by 25.00% and no deviation row names it",
    ]


def test_a_match_row_does_not_name_a_tile(fidelity: ModuleType, setup: Callable[..., Any]) -> None:
    report = setup()
    rows = _rows(_row("Header, tiles D4 C3 A1", "match"))
    fidelity.Critic("sonnet", runner=Stub(rows)).critique(report)

    assert len([p for p in report.problems() if p.startswith("tile ")]) == 3


def test_with_a_threshold_every_tile_above_it_must_be_named(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup(threshold=30.0)
    rows = _rows(_row("Ledger rows", "deviation", "tile D4: seeded payees"))
    fidelity.Critic("sonnet", runner=Stub(rows)).critique(report)

    # C3 (50.00) is above 30 and unnamed; A1 (25.00) is under it and need not be.
    assert report.problems() == ["tile C3 differs by 50.00% and no deviation row names it"]


def test_the_critic_is_told_which_tiles_to_explain_and_may_only_read(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup()
    stub = Stub(_rows(NAMING_ALL_THREE))

    fidelity.Critic("opus", runner=stub).critique(report)

    prompt, model, tools = stub.calls[0]
    assert model == "opus"
    assert 'named by a "deviation" row' in prompt
    assert "D4, C3, A1" in prompt
    assert "artboard.png" in prompt and "app-1360.png" in prompt
    assert "src/kaleta/views/transactions/" in prompt
    assert all(tool.startswith("Read(//") for tool in tools.split(","))
    assert "Bash" in fidelity.CRITIC_DENIED and "Write" in fidelity.CRITIC_DENIED


def test_a_critic_answer_with_an_unknown_status_is_refused(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup()
    before = report.path.read_text(encoding="utf-8")
    stub = Stub(_rows(_row("Title", "fine")))

    with pytest.raises(fidelity.FidelityError, match="status 'fine'"):
        fidelity.Critic("sonnet", runner=stub).critique(report)
    assert report.path.read_text(encoding="utf-8") == before


def test_a_critic_answer_with_too_few_rows_is_refused(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup()
    stub = Stub([_row("Title"), _row("Drawer")])

    with pytest.raises(fidelity.FidelityError, match="compared 2 elements"):
        fidelity.Critic("sonnet", runner=stub).critique(report)


def test_a_pipe_in_a_critic_value_stays_in_its_cell(
    fidelity: ModuleType, setup: Callable[..., Any]
) -> None:
    report = setup()
    rows = _rows(_row("Grid | columns", "deviation", "tiles D4, C3, A1: 1fr | 168px"))
    fidelity.Critic("sonnet", runner=Stub(rows)).critique(report)

    assert report.problems() == []
    assert report.named_tiles(report.path.read_text(encoding="utf-8")) == {"D4", "C3", "A1"}


def test_check_writes_a_fidelity_record_to_the_plans_run_log(
    fidelity: ModuleType, setup: Callable[..., Any], tmp_path: Path
) -> None:
    report = setup()
    fidelity.Critic("sonnet", runner=Stub(_rows(NAMING_ALL_THREE), run_id="run-42")).critique(
        report
    )
    state = tmp_path / "repo" / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "active-plan").write_text("some-plan\n", encoding="utf-8")

    plan_id = fidelity.RunLog(tmp_path / "repo").record(report, [])

    log = tmp_path / "repo" / "docs" / "harness" / "runs" / "some-plan.jsonl"
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert plan_id == "some-plan"
    assert record["kind"] == "fidelity"
    assert record["artboard"] == "2a"
    assert record["ok"] is True
    assert record["critic_run"] == "run-42"
    assert record["tile_threshold"] is None
    sys.path.insert(0, str(REPO / "scripts" / "harness"))
    import gate_log

    assert gate_log.verify(tmp_path / "repo", "some-plan") == []
