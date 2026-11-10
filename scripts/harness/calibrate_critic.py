#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run the critic on the calibration cases and write a calibration report (ADR-39 principle 5).

    calibrate_critic.py --split calib|test --budget-usd N [--max-cases N]
                        [--samples K] [--cross] [--dry-run] [--force --reason TEXT]

Each case (``tests/harness/critic_cases/``, built by ``seed_defects.py``) is
replayed in a temporary worktree: the case's base, with today's critic
questions, profile and hooks laid over it as one commit, then the PR's diff
and the case's mutation on top. ``critic.py --base`` answers on it exactly as
the gate would (real model, *k* samples). The answers are compared with the
gold labels.

- Results go to ``docs/harness/calibration/<critic_hash>-<split>.cases.jsonl``,
  one line per case; a later run resumes from it (same critic hash only).
- ``--budget-usd`` is required. A run stops before a case whose expected cost
  (the mean so far, or ``EST_CASE_USD`` per sample) would cross it.
- The **test split runs once per critic hash**: once its report exists, a
  second run needs ``--force --reason "<text>"``, and the reason is logged.
  The test split's case ids must hash to ``docs/harness/calibration/test-split.sha256``.
- The report, ``<critic_hash>-<split>.json`` and ``.md``, carries per question:
  n, accuracy, miss rate, false-alarm rate, Brier, reliability at the levels a
  k-sample critic reaches, ECE, counterfactual flip rate, invalid-evidence rate,
  all rates with 95% Wilson intervals — plus totals, cost and the critic hash.

The worktree reuses this checkout's virtualenv without syncing it
(``UV_PROJECT_ENVIRONMENT``, ``UV_NO_SYNC``) and puts the case's ``src`` first on
``PYTHONPATH``, so a critic sample that runs ``uv run pytest`` tests the case's
code against today's dependencies.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import calibration  # noqa: E402
import critic  # noqa: E402
import judge  # noqa: E402
import seed_defects  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path("docs/harness/calibration")
FORCED_LOG = OUT / "forced-runs.log"
#: Expected cost of one Claude sample on one case, before any case has run (USD).
EST_CASE_USD = 0.30
LABEL_NOTE = (
    "Clean cases are labelled by a heuristic: no fix commit touched the PR's Python"
    " sources within 30 days of the merge. Latent bugs slip past it, so false alarms"
    " on clean cases may be real findings. Mutant recall (miss rate on seeded"
    " violations) is the trustworthy number."
)


def git(*args: str, cwd: Path, input_text: str | None = None, check: bool = True) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, input=input_text, capture_output=True, text=True,
        errors="replace", check=False,
    )  # fmt: skip
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


# ── what the run is ──────────────────────────────────────────────────────
def critic_models(cross: bool) -> list[str]:
    """The models list ``critic.py`` hashes, for the same environment."""
    model = os.environ.get("KALETA_REVIEW_MODEL", "sonnet")
    cross_model = os.environ.get("KALETA_CROSS_REVIEW_MODEL", "")
    return [model] + ([f"{critic.CROSS_PREFIX}{cross_model or 'auto'}"] if cross else [])


def results_path(split: str) -> Path:
    """Every case result of a split, whatever critic hash it ran under."""
    return OUT / f"{split}.cases.jsonl"


def report_paths(chash: str, split: str) -> dict[str, Path]:
    stem = OUT / f"{chash}-{split}"
    return {"json": stem.with_suffix(".json"), "md": stem.with_suffix(".md")}


def load_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def check_test_pin(root: Path, cases: list[dict[str, Any]]) -> str | None:
    """An error when the test split is not the one pinned, else ``None``."""
    pin = root / seed_defects.TEST_SPLIT_PIN
    if not pin.exists():
        return f"{seed_defects.TEST_SPLIT_PIN} is missing — run seed_defects.py"
    want = pin.read_text(encoding="utf-8").split()[0]
    got = calibration.test_split_hash(c["id"] for c in cases if c["split"] == "test")
    if want != got:
        pin_name = seed_defects.TEST_SPLIT_PIN
        return f"the test split does not match {pin_name} ({got[:16]} != {want[:16]})"
    return None


# ── one case ─────────────────────────────────────────────────────────────
def overlay_files(root: Path) -> list[str]:
    tracked = git("ls-files", cwd=root).splitlines()
    return [p for p in tracked if any(fnmatchcase(p, g) for g in seed_defects.OVERLAY)]


def run_case(root: Path, case: dict[str, Any], k: int, cross: bool) -> dict[str, Any]:
    """Replay *case* in a temporary worktree and return the critic's record."""
    tmp = Path(tempfile.mkdtemp(prefix="kaleta-calib-"))
    work = tmp / "tree"
    git("worktree", "add", "-q", "--detach", str(work), case["base"], cwd=root)
    try:
        for rel in overlay_files(root):
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, work / rel)
        git("add", "-A", cwd=work)
        git(
            "-c", "user.name=calibration", "-c", "user.email=calibration@localhost",
            "commit", "-q", "--no-verify", "--allow-empty", "-m", "calibration overlay",
            cwd=work,
        )  # fmt: skip
        overlay = git("rev-parse", "HEAD", cwd=work).strip()
        diff = git("diff", "--binary", "--no-renames", case["base"], case["head"], cwd=root)
        git("apply", "--index", "--whitespace=nowarn", "-", cwd=work, input_text=diff)
        patch = root / seed_defects.CASES / case["id"] / "mutation.patch"
        if patch.exists():
            git("apply", "--index", "--whitespace=nowarn", str(patch), cwd=work)

        env = dict(os.environ)
        env.update(
            {
                "UV_PROJECT_ENVIRONMENT": str(root / ".venv"),
                "UV_NO_SYNC": "1",
                "PYTHONPATH": str(work / "src"),
            }
        )
        if cross:
            env["KALETA_CROSS_REVIEW"] = "1"
        cmd = [
            sys.executable, str(root / "scripts/harness/critic.py"), case["plan_id"],
            "--base", overlay, "--samples", str(k),
        ]  # fmt: skip
        done = subprocess.run(
            cmd, cwd=work, env=env, capture_output=True, text=True, errors="replace", check=False
        )
        record_path = work / critic.STATE / "critic.json"
        if not record_path.exists():
            return {"status": "error", "error": (done.stderr or done.stdout)[-2000:], "cost_usd": 0}
        record: dict[str, Any] = json.loads(record_path.read_text(encoding="utf-8"))
        return record
    finally:
        git("worktree", "remove", "--force", str(work), cwd=root, check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def result_line(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    by_q = {q["id"]: q for q in record.get("questions", [])}
    answers = {}
    for qid in case["gold"]:
        q = by_q.get(qid)
        answers[qid] = (
            None
            if q is None
            else {
                "p": q.get("p_violation"),
                "k_total": q.get("k_total", 0),
                "invalid": len(q.get("invalid", [])),
                "answers": q.get("answers", []),
                "evidence": q.get("evidence", []),
            }
        )
    return {
        "case_id": case["id"],
        "plan_id": case["plan_id"],
        "kind": case["kind"],
        "operator": case["operator"],
        "target": case["target"],
        "gold": case["gold"],
        "critic_hash": record.get("critic_hash"),
        "status": record.get("status"),
        "error": record.get("error", ""),
        "cost_usd": float(record.get("cost_usd") or 0),
        "at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "answers": answers,
    }


# ── the report ───────────────────────────────────────────────────────────
def observations(results: list[dict[str, Any]]) -> dict[str, list[calibration.Observation]]:
    by_q: dict[str, list[calibration.Observation]] = {}
    for r in results:
        if r.get("status") != "ok":
            continue
        for qid, gold in r["gold"].items():
            a = r["answers"].get(qid)
            if a is None:
                continue  # the critic did not ask it: not scored
            by_q.setdefault(qid, []).append(
                calibration.Observation(
                    case_id=r["case_id"],
                    plan_id=r["plan_id"],
                    question=qid,
                    gold=gold,
                    p=a["p"],
                    samples=a["k_total"],
                    invalid=a["invalid"],
                    target=r["target"],
                    kind=r["kind"],
                )
            )
    return by_q


def build_report(
    results: list[dict[str, Any]],
    *,
    chash: str,
    split: str,
    k: int,
    profile: judge.Profile,
    cases_total: int,
    forced: list[str],
) -> dict[str, Any]:
    questions = {}
    for qid, obs in sorted(observations(results).items()):
        block, uncertain = profile.threshold(qid)
        questions[qid] = calibration.question_metrics(
            obs, calibration.Thresholds(block, uncertain), k
        )
        questions[qid]["thresholds"] = {"block": block, "uncertain": uncertain}
    ok = [r for r in results if r.get("status") == "ok"]
    all_obs = [o for obs in observations(results).values() for o in obs]
    # Brier, reliability and ECE do not depend on thresholds; the rates do, and
    # each question has its own — so the totals' rates are the per-question sums.
    block_d, unsure_d = profile.threshold("")
    totals = calibration.question_metrics(all_obs, calibration.Thresholds(block_d, unsure_d), k)
    for key in ("accuracy", "miss_rate", "block_recall", "false_alarm_rate", "flip_rate"):
        num = sum(m[key]["num"] for m in questions.values())
        den = sum(m[key]["den"] for m in questions.values())
        totals[key] = calibration.rate(num, den)
    totals["miss_rate_upper"] = totals["miss_rate"]["upper"]
    target = float(profile.raw.get("calibration", {}).get("miss_rate_target", 0.10))
    return {
        "version": 1,
        "critic_hash": chash,
        "split": split,
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "k": k,
        "cases_total": cases_total,
        "cases_run": len(results),
        "cases_ok": len(ok),
        "complete": len(ok) == cases_total,
        "cost_usd": round(sum(r["cost_usd"] for r in results), 4),
        "miss_rate_target": target,
        "calibrated": sorted(
            q
            for q, m in questions.items()
            if m["miss_rate_upper"] is not None and m["miss_rate_upper"] <= target
        ),
        "label_note": LABEL_NOTE,
        "forced": forced,
        "questions": questions,
        "totals": totals,
    }


def _fmt(rate: dict[str, Any]) -> str:
    if rate["value"] is None:
        return "-"
    interval = f"[{rate['lower']:.2f}, {rate['upper']:.2f}]"
    return f"{rate['value']:.2f} {interval} ({rate['num']}/{rate['den']})"


def render_md(report: dict[str, Any]) -> str:
    lines = [
        f"# Critic calibration — {report['split']} split",
        "",
        (
            f"Critic `{report['critic_hash']}` · k={report['k']} · "
            f"{report['cases_ok']}/{report['cases_total']} cases"
            f"{'' if report['complete'] else ' (incomplete)'} · "
            f"cost {report['cost_usd']:.2f} USD · {report['generated_at']}"
        ),
        "",
        (
            f"Calibrated (miss-rate upper bound ≤ {report['miss_rate_target']:.2f}): "
            f"{', '.join(report['calibrated']) or 'none'}."
        ),
        "",
        f"> {report['label_note']}",
        "",
        (
            "Miss = a true violation with p under the `uncertain` threshold (it passes"
            " unseen). False alarm = a clean answer with p at or above `block`. Rates"
            " show the 95% Wilson interval and num/den."
        ),
        "",
        (
            "| Question | n | miss rate | false alarms | accuracy | flip | Brier | ECE"
            " | invalid evidence |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    rows = [*report["questions"].items(), ("**all**", report["totals"])]
    for qid, m in rows:
        lines.append(
            f"| {qid} | {m['n']} | {_fmt(m['miss_rate'])} | {_fmt(m['false_alarm_rate'])} | "
            f"{_fmt(m['accuracy'])} | {_fmt(m['flip_rate'])} | "
            f"{'-' if m['brier'] is None else f'{m["brier"]:.3f}'} | "
            f"{'-' if m['ece'] is None else f'{m["ece"]:.3f}'} | "
            f"{_fmt(m['invalid_evidence_rate'])} |"
        )
    levels = report["totals"]["reliability"]
    header = " | ".join(f"p≈{r['level']:.2f}" for r in levels)
    lines += ["", "## Reliability", "", f"| Question | {header} |", "|---|" + "---|" * len(levels)]
    for qid, m in rows:
        cells = [
            "-" if r["n"] == 0 else f"{r['observed']:.2f} (n={r['n']})" for r in m["reliability"]
        ]
        lines.append(f"| {qid} | " + " | ".join(cells) + " |")
    if report["forced"]:
        lines += ["", "## Forced re-runs", ""] + [f"- {r}" for r in report["forced"]]
    return "\n".join(lines) + "\n"


# ── main ─────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--split", choices=("calib", "test"), required=True)
    ap.add_argument("--budget-usd", type=float, required=True)
    ap.add_argument("--max-cases", type=int)
    ap.add_argument("--samples", type=int, help="k (default: the profile's largest critic_samples)")
    ap.add_argument("--cross", action="store_true", help="a local-model sample on every case")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-run a test split that has a report")
    ap.add_argument("--reason", default="", help="why a test split runs again (with --force)")
    args = ap.parse_args(argv)

    root = ROOT
    os.chdir(root)
    profile = judge.load_profile(root)
    samples = profile.autonomy.get("critic_samples", {}) or {"default": 3}
    k = args.samples or max(int(v) for v in samples.values())
    cross = args.cross or os.environ.get("KALETA_CROSS_REVIEW") == "1"
    # The critic adds a local-model sample on its own where the profile requires
    # one (high risk), and that changes its hash: a run can produce two reports.
    plain_hash = critic.critic_hash(root, critic_models(False))
    cross_hash = critic.critic_hash(root, critic_models(True))
    known = {cross_hash} if cross else {plain_hash, cross_hash}

    cases = seed_defects.load_cases(root)
    if not cases:
        print("calibrate: no cases — run scripts/harness/seed_defects.py first", file=sys.stderr)
        return 1
    if error := check_test_pin(root, cases):
        print(f"calibrate: {error}", file=sys.stderr)
        return 1
    in_split = [c for c in cases if c["split"] == args.split]
    split_ids = {c["id"] for c in in_split}

    previous = {
        h: json.loads((root / report_paths(h, args.split)["json"]).read_text(encoding="utf-8"))
        for h in known
        if (root / report_paths(h, args.split)["json"]).exists()
    }
    forced: list[str] = sorted({f for rep in previous.values() for f in rep.get("forced", [])})
    # "Once" is one complete run: a run the budget cut short may resume.
    rerun = args.split == "test" and any(rep.get("complete") for rep in previous.values())
    if rerun:
        if not (args.force and args.reason.strip()):
            print(
                f"calibrate: the test split already ran for this critic"
                f' ({", ".join(sorted(previous))}). A second run needs --force --reason "<text>".',
                file=sys.stderr,
            )
            return 1
        stamp = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
        forced.append(f"{stamp} {'/'.join(sorted(known))}: {args.reason.strip()}")

    results_file = root / results_path(args.split)
    if rerun:
        prior = load_results(results_file)
        kept = [r for r in prior if r.get("critic_hash") not in known]
        results_file.write_text("".join(json.dumps(r) + "\n" for r in kept), encoding="utf-8")
    done_ids = {
        r["case_id"]
        for r in load_results(results_file)
        if r.get("status") == "ok" and r.get("critic_hash") in known
    }
    todo = [c for c in in_split if c["id"] not in done_ids]
    if args.max_cases is not None:
        todo = todo[: args.max_cases]
    est = k * EST_CASE_USD
    print(
        f"calibrate: critic {plain_hash} (with a local sample: {cross_hash})"
        f" · split {args.split} · k={k}{' (+cross on every case)' if cross else ''}"
        f" · {len(in_split)} cases, {len(done_ids)} done, {len(todo)} to run"
        f" · est. {est:.2f} USD/case, budget {args.budget_usd:.2f} USD"
    )
    if args.dry_run:
        for c in todo[:20]:
            print(f"  {c['id']:60} {c['kind']:6} {c['target'] or '-'}")
        if len(todo) > 20:
            print(f"  … and {len(todo) - 20} more")
        print(f"calibrate: dry run — would append to {results_path(args.split)} and write reports")
        return 0

    (root / OUT).mkdir(parents=True, exist_ok=True)
    if rerun:
        with (root / FORCED_LOG).open("a", encoding="utf-8") as fh:
            fh.write(forced[-1] + "\n")
    spent = 0.0
    ran: list[float] = []
    for case in todo:
        expected = (sum(ran) / len(ran)) if ran else est
        if spent + expected > args.budget_usd:
            print(f"calibrate: budget reached ({spent:.2f} USD spent) — stopping, resumable")
            break
        line = result_line(case, run_case(root, case, k, cross))
        if line["status"] == "ok" and line["critic_hash"] not in known:
            print(
                f"calibrate: case {case['id']} ran under critic {line['critic_hash']},"
                f" expected one of {sorted(known)} — the critic changed; stopping",
                file=sys.stderr,
            )
            return 1
        spent += line["cost_usd"]
        ran.append(line["cost_usd"])
        with results_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
        print(f"  {case['id']:60} {line['status']:5} {line['cost_usd']:.2f} USD")

    latest: dict[str, dict[str, Any]] = {}
    for r in load_results(results_file):
        if r.get("case_id") in split_ids and r.get("critic_hash") in known:
            latest[r["case_id"]] = r
    ok = [r for r in latest.values() if r.get("status") == "ok"]
    complete = {r["case_id"] for r in ok} == split_ids
    for chash in sorted({r["critic_hash"] for r in ok}):
        mine = [r for r in ok if r["critic_hash"] == chash]
        report = build_report(
            mine, chash=chash, split=args.split, k=k, profile=profile,
            cases_total=len(mine), forced=forced,
        )  # fmt: skip
        report["complete"] = complete
        report["split_cases_total"] = len(split_ids)
        files = report_paths(chash, args.split)
        (root / files["json"]).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (root / files["md"]).write_text(render_md(report), encoding="utf-8")
        print(
            f"calibrate: critic {chash}: {len(mine)} cases, {report['cost_usd']:.2f} USD"
            f"{'' if complete else ' (split incomplete)'} — {files['json']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
