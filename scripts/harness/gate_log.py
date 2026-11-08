#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only, tamper-evident run log for the gate and the critic (ADR-39).

One JSON object per line in ``docs/harness/runs/<plan_id>.jsonl``. Every
record carries ``seq``, ``prev`` (the previous record's ``sha``) and its own
``sha`` — the sha256 of the record without ``sha``, serialised canonically.
Editing, deleting or reordering a line breaks the chain, and ``verify`` says
where.

    gate_log.py append <plan_id> --kind gate|review [--json FILE|-]
    gate_log.py verify [<plan_id>]
    gate_log.py report [--since YYYY-MM-DD]
    gate_log.py show <plan_id> [--last N]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

RUNS = Path("docs/harness/runs")
GENESIS = "0" * 64
PLAN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
KINDS = ("gate", "review", "fidelity", "canary")


def canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "sha"}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def log_path(root: Path, plan_id: str) -> Path:
    if not PLAN_ID.match(plan_id):
        raise ValueError(f"invalid plan id: {plan_id!r}")
    return root / RUNS / f"{plan_id}.jsonl"


def read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def records(root: Path, plan_id: str) -> list[dict[str, Any]]:
    return read(log_path(root, plan_id))


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _last_record(path: Path) -> dict[str, Any] | None:
    """The last parsable record; a broken log still gets appended to (verify flags it)."""
    if not path.exists():
        return None
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and "sha" in rec and "seq" in rec:
            return rec
    return None


def append(root: Path, plan_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown record kind: {kind!r}")
    path = log_path(root, plan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    last = _last_record(path)
    record = {
        **payload,
        "kind": kind,
        "plan_id": plan_id,
        "seq": (last["seq"] + 1) if last else 1,
        "prev": last["sha"] if last else GENESIS,
        "ts": payload.get("ts") or now(),
    }
    record["sha"] = _sha(record)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(canonical(record) + "\n")
    return record


def verify_file(path: Path) -> list[str]:
    errors: list[str] = []
    prev, seq = GENESIS, 0
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{n}: not JSON ({exc})")
            break
        if rec.get("sha") != _sha(rec):
            errors.append(f"{path}:{n}: record was modified (sha mismatch)")
        if rec.get("prev") != prev:
            errors.append(f"{path}:{n}: chain broken (prev does not match line {n - 1})")
        if rec.get("seq") != seq + 1:
            errors.append(f"{path}:{n}: seq {rec.get('seq')} after {seq} (deleted or reordered)")
        prev, seq = rec.get("sha", ""), rec.get("seq", seq + 1)
    return errors


def verify(root: Path, plan_id: str | None = None) -> list[str]:
    paths = [log_path(root, plan_id)] if plan_id else sorted((root / RUNS).glob("*.jsonl"))
    errors: list[str] = []
    for p in paths:
        if p.exists():
            errors.extend(verify_file(p))
    return errors


def _summary(recs: list[dict[str, Any]]) -> dict[str, Any]:
    gates = [r for r in recs if r["kind"] == "gate" and not r.get("dry")]
    reviews = [r for r in recs if r["kind"] == "review"]
    cost = sum(float(r.get("cost_usd") or 0) for r in reviews)
    return {
        "attempts": max((int(r.get("attempt") or 0) for r in gates), default=0),
        "outcome": gates[-1].get("outcome", "?") if gates else "-",
        "mode": gates[-1].get("decision", {}).get("mode") if gates else None,
        "reviews": len(reviews),
        "cost_usd": cost,
        "first": recs[0]["ts"] if recs else "",
        "last": recs[-1]["ts"] if recs else "",
    }


def report(root: Path, since: str | None = None) -> str:
    rows = []
    for path in sorted((root / RUNS).glob("*.jsonl")):
        recs = [r for r in read(path) if not since or r.get("ts", "") >= since]
        if recs:
            rows.append((path.stem, _summary(recs)))
    if not rows:
        return "gate_log: no runs recorded yet"
    out = [f"{'PLAN':40} {'OUTCOME':10} {'MODE':4} {'ATT':>3} {'REV':>3} {'COST':>8}  LAST"]
    for plan, s in rows:
        out.append(
            f"{plan[:40]:40} {s['outcome']:10} {s['mode'] or '-':4} {s['attempts']:>3}"
            f" {s['reviews']:>3} {s['cost_usd']:>8.2f}  {s['last']}"
        )
    finished = [s for _, s in rows if s["outcome"] in ("done", "exhausted", "escalated")]
    outcomes: dict[str, int] = {}
    for _, s in rows:
        outcomes[s["outcome"]] = outcomes.get(s["outcome"], 0) + 1
    done = [s for s in finished if s["outcome"] == "done"]
    out.append("")
    out.append("outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(outcomes.items())))
    if finished:
        out.append(
            f"median attempts (finished): {statistics.median(s['attempts'] for s in finished)}"
        )
    if done:
        total = sum(s["cost_usd"] for s in done)
        out.append(f"critic cost per done plan: {total / len(done):.2f} USD")
    return "\n".join(out)


def _load_json(arg: str) -> dict[str, Any]:
    text = sys.stdin.read() if arg == "-" else Path(arg).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit("gate_log: payload must be a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append")
    a.add_argument("plan_id")
    a.add_argument("--kind", required=True, choices=KINDS)
    a.add_argument("--json", default="-")
    v = sub.add_parser("verify")
    v.add_argument("plan_id", nargs="?")
    r = sub.add_parser("report")
    r.add_argument("--since")
    s = sub.add_parser("show")
    s.add_argument("plan_id")
    s.add_argument("--last", type=int, default=5)
    args = ap.parse_args(argv)

    if args.cmd == "append":
        rec = append(args.root, args.plan_id, args.kind, _load_json(args.json))
        print(f"gate_log: {args.plan_id} #{rec['seq']} {args.kind}")
        return 0
    if args.cmd == "verify":
        errors = verify(args.root, args.plan_id)
        for e in errors:
            print(e, file=sys.stderr)
        n = len(list((args.root / RUNS).glob("*.jsonl")))
        print(f"gate_log: {'BROKEN' if errors else 'OK'} ({n} log file(s))")
        return 1 if errors else 0
    if args.cmd == "report":
        print(report(args.root, args.since))
        return 0
    for rec in records(args.root, args.plan_id)[-args.last :]:
        print(json.dumps(rec, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
