#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The critic: an expert witness, not a judge (ADR-39).

Answers the narrow questions in ``docs/harness/critic-questions.toml`` about
the current diff. Each of *k* independent samples (fresh ``claude -p``
contexts, optionally one from another model family via the Cursor CLI)
answers ``yes | no | na`` per question; a ``yes`` must cite ``file:line``
evidence on the new side of the diff, and this script checks that evidence
deterministically. ``p_violation`` is the share of valid samples that found
the problem. There is no verdict: ``scripts/harness/gate.py`` decides.

    critic.py [plan_id] [--samples N] [--dry-run]

Env:
    KALETA_CRITIC_SAMPLES       k (default: profile, else 3)
    KALETA_REVIEW_MODEL         Claude model for the samples (default: sonnet)
    KALETA_CROSS_REVIEW=1       one of the k samples from the Cursor CLI (required)
    KALETA_CROSS_REVIEW_MODEL   Cursor model id (default: gpt-5)
    KALETA_CRITIC_FAKE=<dir>    read canned samples (sample-<i>.json, cross.json) — tests only

Writes ``.claude/state/critic.json`` and a ``review`` record in the run log.
Exit 0 when the critic ran (whatever it found), 1 when it could not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_log  # noqa: E402
import gitutil  # noqa: E402
import judge  # noqa: E402
from planfile import plan_meta  # noqa: E402

QUESTIONS = Path("docs/harness/critic-questions.toml")
PROFILE = Path("docs/harness/profile.toml")
STATE = Path(".claude/state")
EVIDENCE_WINDOW = 5
DEFAULT_SAMPLES = 3
ALLOWED_TOOLS = (
    "Read,Grep,Glob,Bash(git diff *),Bash(git log *),Bash(git show *),"
    "Bash(git status *),Bash(uv run pytest *)"
)

TEMPLATE = """You are an independent expert witness reviewing a code change in this repository.
You did NOT write this code. Do not edit anything. You do not decide whether the
change is merged: you answer narrow questions, and a deterministic judge combines
your answers with thresholds the owner has set.

The change: the working-tree diff against merge-base {base}
  git diff {base} --stat
  git diff {base}
The scope contract: docs/plans/{plan_id}.md (Scope, "Not in scope", Acceptance
criteria, Implementation notes). Context: docs/review-checklist.md and the
Working Agreement in AGENTS.md. You may run `uv run pytest <path> -q` to check a claim.

Answer EVERY question below with exactly one of:
  "yes"  the problem described IS present in this diff. You MUST cite evidence:
         the file and a line number on the NEW side of the diff where it shows.
         A "yes" whose evidence does not point into the diff is discarded.
  "no"   you checked, and it is not present.
  "na"   the question does not apply to this diff.
Answer the question as asked, not a broader one. When unsure, investigate (read
the code, run a test) before answering; do not guess "yes".

Questions:
{questions}

Return ONLY a JSON object:
{{"answers": [{{"id": "Q-…", "answer": "yes|no|na",
               "evidence": [{{"file": "…", "line": 1}}], "note": "…"}}],
 "findings": [{{"file": "…", "line": 1, "summary": "…"}}]}}
"findings" is optional free-form advice for the author; it never decides anything.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "answer": {"type": "string", "enum": ["yes", "no", "na"]},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "line": {"type": "integer"},
                            },
                            "required": ["file", "line"],
                        },
                    },
                    "note": {"type": "string"},
                },
                "required": ["id", "answer"],
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "summary": {"type": "string"},
                },
                "required": ["file", "summary"],
            },
        },
    },
    "required": ["answers"],
}


# ── questions ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Question:
    id: str
    text: str
    section: str = ""
    applies_to: tuple[str, ...] = ()
    evidence: str = ""


def load_questions(root: Path) -> list[Question]:
    data = tomllib.loads((root / QUESTIONS).read_text(encoding="utf-8"))
    out = [
        Question(
            id=q["id"],
            text=" ".join(q["text"].split()),
            section=q.get("section", ""),
            applies_to=tuple(q.get("applies_to", [])),
            evidence=q.get("evidence", ""),
        )
        for q in data.get("question", [])
    ]
    ids = [q.id for q in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question ids in critic-questions.toml")
    return out


def applicable(questions: list[Question], paths: list[str]) -> list[Question]:
    return [
        q
        for q in questions
        if not q.applies_to or any(fnmatchcase(p, g) for p in paths for g in q.applies_to)
    ]


def render_prompt(base: str, plan_id: str, questions: list[Question]) -> str:
    qtext = "\n".join(
        f"- {q.id}: {q.text}" + (f"\n  (evidence for yes: {q.evidence})" if q.evidence else "")
        for q in questions
    )
    return TEMPLATE.format(base=base, plan_id=plan_id, questions=qtext)


def critic_hash(root: Path, models: list[str]) -> str:
    h = hashlib.sha256()
    h.update(TEMPLATE.encode())
    h.update((root / QUESTIONS).read_bytes())
    h.update("|".join(models).encode())
    return h.hexdigest()[:16]


# ── samples ──────────────────────────────────────────────────────────────
@dataclass
class Sample:
    reviewer: str
    model: str
    ok: bool
    answers: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float = 0.0
    turns: int = 0
    error: str = ""


def _first_json_object(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def claude_sample(prompt: str, model: str, idx: int) -> Sample:
    if not shutil.which("claude"):
        return Sample("claude", model, False, error="claude CLI not found")
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--permission-mode", "dontAsk",
        "--allowedTools", ALLOWED_TOOLS,
        "--max-turns", "30",
        "--output-format", "json",
        "--json-schema", json.dumps(SCHEMA),
    ]  # fmt: skip
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    (STATE / f"critic-raw-{idx}.json").write_text(out.stdout or out.stderr, encoding="utf-8")
    raw = _first_json_object(out.stdout) or {}
    payload = raw.get("structured_output")
    if payload is None and isinstance(raw.get("result"), str):
        payload = _first_json_object(raw["result"])
    if not isinstance(payload, dict) or "answers" not in payload:
        return Sample(
            "claude",
            model,
            False,
            error="output could not be parsed",
            cost_usd=float(raw.get("total_cost_usd") or 0),
        )
    return Sample(
        "claude",
        model,
        True,
        answers=list(payload.get("answers") or []),
        findings=list(payload.get("findings") or []),
        cost_usd=float(raw.get("total_cost_usd") or 0),
        turns=int(raw.get("num_turns") or 0),
    )


def cursor_sample(prompt: str, model: str) -> Sample:
    binary = shutil.which("agent") or shutil.which("cursor-agent")
    reviewer = f"cursor:{model}"
    if not binary:
        return Sample(
            reviewer, model, False, error="Cursor CLI (agent / cursor-agent) is not installed"
        )
    out = subprocess.run(
        [binary, "-p", prompt, "--model", model, "--output-format", "text"],
        capture_output=True,
        text=True,
        check=False,
    )
    (STATE / "critic-raw-cross.txt").write_text(out.stdout + out.stderr, encoding="utf-8")
    payload = _first_json_object(out.stdout)
    if not payload or "answers" not in payload:
        return Sample(reviewer, model, False, error="Cursor reviewer output could not be parsed")
    return Sample(
        reviewer,
        model,
        True,
        answers=list(payload["answers"]),
        findings=list(payload.get("findings") or []),
    )


def fake_sample(directory: Path, name: str, reviewer: str, model: str) -> Sample:
    path = directory / name
    if not path.exists():
        return Sample(reviewer, model, False, error=f"fake sample {name} missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Sample(
        reviewer,
        model,
        True,
        answers=list(data.get("answers") or []),
        findings=list(data.get("findings") or []),
        cost_usd=float(data.get("cost_usd") or 0),
        turns=int(data.get("turns") or 0),
    )


# ── evidence and aggregation ─────────────────────────────────────────────
@dataclass
class Answer:
    value: str | None  # yes | no | na, or None when the sample's answer is invalid
    evidence: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    invalid_reason: str = ""


def evidence_ok(ev: dict[str, Any], changed: set[str], new_lines: dict[str, set[int]]) -> bool:
    file = str(ev.get("file", "")).removeprefix("./").removeprefix("b/")
    if file not in changed:
        return False
    lines = new_lines.get(file)
    if not lines:  # untracked, binary or deletion-only: the file itself is the evidence
        return True
    try:
        line = int(ev.get("line", -1))
    except (TypeError, ValueError):
        return False
    return any(abs(line - n) <= EVIDENCE_WINDOW for n in lines)


def validate(
    sample: Sample, qids: list[str], changed: set[str], new_lines: dict[str, set[int]]
) -> dict[str, Answer]:
    by_id: dict[str, dict[str, Any]] = {}
    for a in sample.answers:
        if isinstance(a, dict) and a.get("id") in qids and a["id"] not in by_id:
            by_id[a["id"]] = a
    out: dict[str, Answer] = {}
    for qid in qids:
        a = by_id.get(qid)
        if a is None:
            out[qid] = Answer(None, invalid_reason="no answer")
            continue
        value = str(a.get("answer", "")).lower()
        note = str(a.get("note", ""))[:500]
        if value not in ("yes", "no", "na"):
            out[qid] = Answer(None, note=note, invalid_reason=f"answer {value!r}")
        elif value == "yes":
            good = [
                {"file": str(e.get("file")).removeprefix("./"), "line": e.get("line")}
                for e in (a.get("evidence") or [])
                if isinstance(e, dict) and evidence_ok(e, changed, new_lines)
            ]
            out[qid] = (
                Answer("yes", good, note)
                if good
                else Answer(None, note=note, invalid_reason="evidence does not point into the diff")
            )
        else:
            out[qid] = Answer(value, note=note)
    return out


def aggregate(questions: list[Question], answers: list[dict[str, Answer]]) -> list[dict[str, Any]]:
    out = []
    for q in questions:
        per = [a[q.id] for a in answers]
        valid = [a for a in per if a.value is not None]
        yes = [a for a in valid if a.value == "yes"]
        k_valid = len(valid)
        evidence: list[dict[str, Any]] = []
        for a in yes:
            for e in a.evidence:
                if e not in evidence:
                    evidence.append(e)
        out.append(
            {
                "id": q.id,
                "section": q.section,
                "p_violation": round(len(yes) / k_valid, 4) if k_valid else None,
                "violations": len(yes),
                "k_valid": k_valid,
                "k_total": len(per),
                "invalid": [a.invalid_reason for a in per if a.value is None],
                "agreement": round(max(len(yes), k_valid - len(yes)) / k_valid, 4)
                if k_valid
                else None,
                "evidence": evidence[:10],
                "notes": [a.note for a in yes if a.note][:3],
            }
        )
    return out


# ── profile: how many samples, and whether another model family must be one ──
def profile_settings(
    root: Path, paths: list[str], plan_text: str
) -> tuple[str | None, int | None, bool]:
    """(risk class, samples, cross_family_required) from the owner's profile, if it is usable."""
    try:
        maintainer = os.environ.get("KALETA_HARNESS_MAINTAINER") == "1"
        profile = judge.load_profile(root, base=None if maintainer else gitutil.merge_base("main"))
    except judge.ProfileError:
        return None, None, False
    meta = plan_meta(plan_text)
    cls, _ = judge.risk_class(
        paths, {"exec_criteria": len(meta["criteria"]), "harness": meta["harness"]}, profile
    )
    autonomy = profile.autonomy
    samples = autonomy.get("critic_samples", {}).get(cls)
    return (
        cls,
        (int(samples) if samples else None),
        cls in autonomy.get("cross_family_required", []),
    )


# ── main ─────────────────────────────────────────────────────────────────
def run(plan_id: str, samples: int | None, dry: bool) -> int:
    root = gitutil.toplevel()
    os.chdir(root)
    STATE.mkdir(parents=True, exist_ok=True)
    plan = Path("docs/plans") / f"{plan_id}.md"
    if not plan.exists():
        print(f"critic: {plan} not found", file=sys.stderr)
        return 1
    base = gitutil.merge_base("main")
    if not gitutil.diff_text(base).strip() and not any(c.untracked for c in gitutil.changed(base)):
        print(f"critic: no diff against {base} — nothing to review", file=sys.stderr)
        return 1
    changed = gitutil.changed(base)
    paths = [c.path for c in changed if not c.path.startswith("docs/harness/runs/")]
    questions = applicable(load_questions(root), paths)

    risk_class, prof_samples, cross_required = profile_settings(
        root, paths, plan.read_text(encoding="utf-8")
    )
    k = samples or int(os.environ.get("KALETA_CRITIC_SAMPLES") or prof_samples or DEFAULT_SAMPLES)
    cross = os.environ.get("KALETA_CROSS_REVIEW") == "1" or cross_required
    model = os.environ.get("KALETA_REVIEW_MODEL", "sonnet")
    cross_model = os.environ.get("KALETA_CROSS_REVIEW_MODEL", "gpt-5")
    models = [model] + ([f"cursor:{cross_model}"] if cross else [])
    chash = critic_hash(root, models)
    prompt = render_prompt(base, plan_id, questions)
    n_claude = max(k - 1, 1) if cross else k

    if dry:
        print(f"critic: plan {plan_id}, base {base[:12]}, critic hash {chash}, risk {risk_class}")
        print(
            f"critic: {n_claude} Claude sample(s) ({model})"
            + (f" + 1 cross ({cross_model})" if cross else "")
        )
        for q in questions:
            print(f"  {q.id:20} {q.section}")
        return 0

    fake = os.environ.get("KALETA_CRITIC_FAKE")
    with ThreadPoolExecutor(max_workers=n_claude + 1) as pool:
        if fake:
            futures = [
                pool.submit(fake_sample, Path(fake), f"sample-{i}.json", "claude", model)
                for i in range(1, n_claude + 1)
            ]
            cross_future = (
                pool.submit(
                    fake_sample, Path(fake), "cross.json", f"cursor:{cross_model}", cross_model
                )
                if cross
                else None
            )
        else:
            futures = [pool.submit(claude_sample, prompt, model, i) for i in range(1, n_claude + 1)]
            cross_future = pool.submit(cursor_sample, prompt, cross_model) if cross else None
        results = [f.result() for f in futures]
        cross_result = cross_future.result() if cross_future else None

    status, error_kind, error = "ok", "", ""
    if cross_result is not None:
        results.append(cross_result)
        if not cross_result.ok:
            status, error_kind = "error", "cross_unavailable"
            error = f"cross-family sample required but failed: {cross_result.error}"
    ok_samples = [s for s in results if s.ok]
    if not any(s.ok and not s.reviewer.startswith("cursor:") for s in results):
        status, error_kind = "error", "no_samples"
        error = "; ".join(sorted({s.error for s in results if s.error})) or "no sample succeeded"

    diff_hash = gitutil.diff_hash(base)
    new_lines = gitutil.new_side_lines(base)
    qids = [q.id for q in questions]
    validated = [validate(s, qids, set(paths), new_lines) for s in ok_samples]
    qresults = aggregate(questions, validated)
    findings = [
        {**f, "reviewer": s.reviewer} for s in ok_samples for f in s.findings if isinstance(f, dict)
    ][:30]
    record = {
        "version": 2,
        "plan_id": plan_id,
        "diff_hash": diff_hash,
        "base": base,
        "critic_hash": chash,
        "at": gate_log.now(),
        "status": status,
        "error_kind": error_kind,
        "error": error,
        "risk_class": risk_class,
        "cross_family_present": any(s.ok and s.reviewer.startswith("cursor:") for s in results),
        "samples": [
            {
                "reviewer": s.reviewer,
                "model": s.model,
                "ok": s.ok,
                "error": s.error,
                "cost_usd": s.cost_usd,
                "turns": s.turns,
            }
            for s in results
        ],
        "cost_usd": round(sum(s.cost_usd for s in results), 4),
        "questions": qresults,
        "findings": findings,
    }
    (STATE / "critic.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    gate_log.append(root, plan_id, "review", record)

    print(
        f"critic: {status} — {len(ok_samples)}/{len(results)} samples, critic {chash},"
        f" diff {diff_hash}, cost {record['cost_usd']:.2f} USD"
    )
    if error:
        print(f"critic: {error}", file=sys.stderr)
    for q in qresults:
        p = "-" if q["p_violation"] is None else f"{q['p_violation']:.2f}"
        ev = ", ".join(f"{e['file']}:{e['line']}" for e in q["evidence"][:3])
        print(f"  {q['id']:20} p={p} ({q['violations']}/{q['k_valid']}){'  ' + ev if ev else ''}")
    return 0 if status == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("plan_id", nargs="?")
    ap.add_argument("--samples", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    plan_id = args.plan_id
    if not plan_id:
        path = gitutil.toplevel() / STATE / "active-plan"
        plan_id = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    if not plan_id:
        print(
            "usage: critic.py <plan_id> (or arm a plan with scripts/plan_goal.sh start)",
            file=sys.stderr,
        )
        return 1
    return run(plan_id, args.samples, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
