#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The judge: a pure function of the evidence and the owner's profile (ADR-39).

    decide(inputs, profile) -> Decision

No I/O, no clock, no randomness: the same inputs and profile give the same
decision, and every gate record in docs/harness/runs/ stores both, so

    judge.py replay docs/harness/runs/<plan_id>.jsonl

recomputes every recorded decision and fails on any difference. Order:

1. vetoes                       -> escalate, mode D
2. failed checks, green-washing, missing/stale/broken critic,
   p >= block, first-round uncertainty   -> block (the implementer fixes it)
3. uncertainty that outlived `uncertain_rounds`, a required cross-family
   sample that could not run   -> escalate, mode C
4. otherwise done, with the mode of the change's risk class, capped at
   `uncalibrated_cap` while any applicable question is uncalibrated
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tomllib
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import gitutil

PROFILE = Path("docs/harness/profile.toml")
MODES = ("A", "B", "C", "D")
CLASSES = ("low", "medium", "high")
MODE_TEXT = {
    "A": "eligible to merge with audit only",
    "B": "the owner merges after reading this note",
    "C": "owner approval required; cross-family critic sample; PR labelled needs-owner-review",
    "D": "stop: a veto was hit",
}


class ProfileError(ValueError):
    pass


# ── profile ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Profile:
    raw: dict[str, Any]

    @property
    def version(self) -> int:
        return int(self.raw["meta"]["version"])

    def threshold(self, qid: str) -> tuple[float, float]:
        t = self.raw["thresholds"]
        per = t.get("question", {}).get(qid, {})
        return float(per.get("block", t["block"])), float(per.get("uncertain", t["uncertain"]))

    @property
    def uncertain_rounds(self) -> int:
        return int(self.raw["thresholds"].get("uncertain_rounds", 1))

    @property
    def autonomy(self) -> dict[str, Any]:
        return self.raw["autonomy"]

    @property
    def risk(self) -> dict[str, Any]:
        return self.raw["risk"]

    @property
    def vetoes(self) -> dict[str, Any]:
        return self.raw.get("vetoes", {})


def _req(cond: bool, msg: str) -> None:
    if not cond:
        raise ProfileError(msg)


def validate(raw: dict[str, Any]) -> Profile:
    meta = raw.get("meta", {})
    _req(
        all(k in meta for k in ("version", "owner", "signed")),
        "[meta] needs version, owner and signed — an unsigned profile is not law",
    )
    t = raw.get("thresholds", {})
    _req("block" in t and "uncertain" in t, "[thresholds] needs block and uncertain")
    for qid, per in [("default", t), *t.get("question", {}).items()]:
        b, u = float(per.get("block", t["block"])), float(per.get("uncertain", t["uncertain"]))
        _req(0 < u <= b <= 1, f"thresholds for {qid}: need 0 < uncertain <= block <= 1")
    a = raw.get("autonomy", {})
    for c in CLASSES:
        _req(a.get(c) in MODES[:3], f"[autonomy] {c} must be A, B or C")
    _req(a.get("uncalibrated_cap", "B") in MODES[:3], "[autonomy] uncalibrated_cap must be A-C")
    _req(isinstance(a.get("allow_auto_merge"), bool), "[autonomy] allow_auto_merge must be a bool")
    r = raw.get("risk", {})
    _req(
        isinstance(r.get("high"), list) and isinstance(r.get("low"), list), "[risk] needs high/low"
    )
    for key in ("no_executable_criteria", "harness_plan"):
        _req(r.get(key, "high") in CLASSES, f"[risk] {key} must be low, medium or high")
    for g in raw.get("green_washing", []):
        _req(g.get("outcome") in ("block", "warn"), f"green_washing {g.get('id')}: outcome")
        _req(g.get("lines") in ("added", "removed"), f"green_washing {g.get('id')}: lines")
    return Profile(raw)


def load_profile(root: Path, base: str | None = None) -> Profile:
    """The owner's profile — as merged on ``base`` when given, else the working tree.

    The gate passes the merge-base: the law is what the owner merged, not what
    the diff under judgement says it is. Maintainer sessions read the working
    tree (they may be changing the profile on purpose).
    """
    text = gitutil.read_at(root, base, PROFILE)
    if text is None:
        raise ProfileError(f"{PROFILE} is missing")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{PROFILE} is not valid TOML: {exc}") from exc
    return validate(_jsonable(raw))


def _jsonable(obj: Any) -> Any:
    """TOML dates -> ISO strings, so the profile can be stored in the run log."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (dt.date, dt.datetime, dt.time)):
        return obj.isoformat()
    return obj


# ── risk ─────────────────────────────────────────────────────────────────
def _match(path: str, globs: list[str]) -> bool:
    return any(fnmatchcase(path, g) for g in globs)


def risk_class(paths: list[str], plan: dict[str, Any], profile: Profile) -> tuple[str, list[str]]:
    """The change's risk class and the paths that put it there."""
    r = profile.risk
    order = {c: i for i, c in enumerate(CLASSES)}
    cls, why = "low", []
    for p in paths:
        if _match(p, r.get("ignore", [])):
            continue
        c = "high" if _match(p, r["high"]) else "low" if _match(p, r["low"]) else "medium"
        if order[c] > order[cls]:
            cls, why = c, [p]
        elif c == cls and c != "low":
            why.append(p)
    floors = []
    if plan.get("exec_criteria", 0) == 0:
        floors.append((r.get("no_executable_criteria", "high"), "plan has no executable criteria"))
    if plan.get("harness"):
        floors.append((r.get("harness_plan", "high"), "harness plan"))
    for c, reason in floors:
        if order[c] > order[cls]:
            cls, why = c, [reason]
        elif c == cls:
            why.append(reason)
    return cls, why


def stricter(a: str, b: str) -> str:
    return a if MODES.index(a) >= MODES.index(b) else b


# ── decision ─────────────────────────────────────────────────────────────
@dataclass
class Decision:
    outcome: str  # done | block | escalate
    mode: str | None
    risk_class: str
    risk_paths: list[str] = field(default_factory=list)
    reasons: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    would_change: list[str] = field(default_factory=list)
    profile_version: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "mode": self.mode,
            "risk_class": self.risk_class,
            "risk_paths": self.risk_paths,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "would_change": self.would_change,
            "profile_version": self.profile_version,
        }


def _r(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _qline(q: dict[str, Any]) -> str:
    ev = ", ".join(f"{e['file']}:{e['line']}" for e in q.get("evidence") or []) or "no evidence"
    notes = " / ".join(q.get("notes") or [])
    p = q.get("p_violation")
    ps = "-" if p is None else f"{p:.2f}"
    return f"{q['id']} p={ps} ({q.get('violations', 0)}/{q.get('k_valid', 0)}) at {ev}" + (
        f" — {notes}" if notes else ""
    )


def profile_error_decision(message: str) -> Decision:
    return Decision(
        "escalate",
        "D",
        "high",
        reasons=[_r("veto.profile", f"The owner's profile cannot be used: {message}")],
        would_change=["The owner fixes and re-signs docs/harness/profile.toml."],
    )


def decide(inputs: dict[str, Any], profile: Profile) -> Decision:
    paths = [c["path"] for c in inputs.get("changed", [])]
    cls, why = risk_class(paths, inputs.get("plan", {}), profile)
    d = Decision("done", None, cls, why, profile_version=profile.version)
    v = profile.vetoes
    critic = inputs.get("critic") or {"present": False}
    usable = critic.get("present") and critic.get("fresh") and critic.get("status") == "ok"
    questions = critic.get("questions", []) if usable else []

    # 1. vetoes
    vetoes: list[dict[str, str]] = []
    if (
        v.get("protected_paths", True)
        and inputs.get("protected_touched")
        and not inputs.get("maintainer")
    ):
        vetoes.append(
            _r(
                "veto.protected",
                "Protected paths changed outside maintainer mode: "
                + " ".join(inputs["protected_touched"])
                + ". Only the maintainer changes the harness.",
            )
        )
    if critic.get("fake") and not inputs.get("test_mode"):
        vetoes.append(
            _r(
                "veto.fake_critic",
                "The critic result came from canned answers (KALETA_CRITIC_FAKE), which only"
                " the harness tests may use.",
            )
        )
    if inputs.get("run_log_errors"):
        vetoes.append(
            _r(
                "veto.run_log",
                "The run log docs/harness/runs/ is broken (edited, deleted or reordered lines): "
                + "; ".join(inputs["run_log_errors"]),
            )
        )
    vetoes.extend(
        _r("veto.secret", f"Secret pattern matched at {hit}.")
        for hit in inputs.get("secret_hits", [])
    )
    sq = v.get("secret_question")
    vetoes.extend(
        _r("veto.secret_question", f"The critic reports secret data: {_qline(q)}")
        for q in questions
        if q["id"] == sq and (q.get("violations") or 0) > 0
    )
    if vetoes:
        d.outcome, d.mode, d.reasons = "escalate", "D", vetoes
        d.would_change = [
            "The owner removes the vetoed change (or confirms it in maintainer mode)."
        ]
        return d

    # 2. blockers the implementer can fix
    blocks: list[dict[str, str]] = []
    for c in inputs.get("checks", []):
        if c.get("ok"):
            continue
        if c["kind"] == "hygiene":
            blocks.append(_r("check.hygiene", c["tail"]))
        elif c["kind"] == "criterion":
            blocks.append(
                _r("check.criterion", f"Acceptance criterion failed: `{c['cmd']}`\n{c['tail']}")
            )
        else:
            blocks.append(_r("check.verify", f"{c['cmd']} failed:\n{c['tail']}"))
    for g in inputs.get("green_washing", []):
        msg = f"{g['message']} ({', '.join(g['where'])})"
        if g["outcome"] == "block":
            blocks.append(_r(f"green_washing.{g['id']}", msg))
        else:
            d.warnings.append(msg)
    if inputs.get("plan", {}).get("exec_criteria", 0) == 0:
        d.warnings.append(
            "Plan has no executable acceptance criteria — the change is treated as high risk."
        )

    escalations: list[dict[str, str]] = []
    if not critic.get("present"):
        blocks.append(
            _r(
                "critic.missing",
                "No critic run yet. Run ./scripts/review_gate.sh and fix what it finds.",
            )
        )
    elif not critic.get("fresh"):
        blocks.append(
            _r(
                "critic.stale",
                "Critic run is stale — the diff changed since. Run ./scripts/review_gate.sh again.",
            )
        )
    elif critic.get("status") != "ok":
        if critic.get("error_kind") == "cross_unavailable":
            escalations.append(
                _r(
                    "critic.cross_unavailable",
                    f"A required cross-family critic sample could not run: {critic.get('error')}",
                )
            )
        else:
            blocks.append(
                _r(
                    "critic.error",
                    f"Critic could not run: {critic.get('error') or critic.get('status')}."
                    " Run ./scripts/review_gate.sh again.",
                )
            )

    required = int(profile.autonomy.get("critic_samples", {}).get(cls) or 1)
    if usable and int(critic.get("samples_ok", 0)) < required:
        blocks.append(
            _r(
                "critic.too_few_samples",
                f"The critic ran {critic.get('samples_ok', 0)} sample(s); risk class {cls} needs"
                f" {required}. Run ./scripts/review_gate.sh without lowering --samples or"
                " KALETA_CRITIC_SAMPLES.",
            )
        )

    prior = inputs.get("prior_uncertain", {})
    for q in questions:
        if q["id"] == sq:
            continue
        block_t, unsure_t = profile.threshold(q["id"])
        p = q.get("p_violation")
        if p is None:
            blocks.append(
                _r(
                    f"critic.no_answer.{q['id']}",
                    f"No valid critic answer for {q['id']} (missing or invalid evidence)."
                    " Run ./scripts/review_gate.sh again.",
                )
            )
        elif p >= block_t:
            blocks.append(_r(f"critic.block.{q['id']}", f"Critic found a problem: {_qline(q)}"))
        elif p >= unsure_t:
            if prior.get(q["id"], 0) < profile.uncertain_rounds:
                blocks.append(
                    _r(
                        f"critic.uncertain.{q['id']}",
                        "The critic is unsure — strengthen the evidence (a test, a clearer "
                        f"Implementation note, or a narrower change): {_qline(q)}",
                    )
                )
            else:
                escalations.append(
                    _r(
                        f"critic.uncertain_exhausted.{q['id']}",
                        f"The critic stayed unsure after {prior.get(q['id'], 0)} more review"
                        f" round(s): {_qline(q)}",
                    )
                )
        elif p > 0:
            d.warnings.append(f"Minor critic signal: {_qline(q)}")

    if blocks:
        d.outcome, d.reasons = "block", blocks
        return d
    if escalations:
        d.outcome, d.mode, d.reasons = "escalate", "C", escalations
        d.would_change = ["The owner reads the evidence and decides; the critic cannot settle it."]
        return d

    # 4. done: autonomy for this change
    a = profile.autonomy
    mode = a[cls]
    d.would_change.append(
        f"Risk class {cls} ({', '.join(why[:3]) or 'only low-risk paths'}) sets mode {mode}."
    )
    cal = inputs.get("calibration") or {}
    calibrated = set(cal.get("calibrated", []))
    uncal = [q["id"] for q in questions if q["id"] not in calibrated]
    cap = a.get("uncalibrated_cap", "B")
    if uncal and stricter(cap, mode) != mode:
        mode = cap
        d.would_change.append(
            f"Capped at {cap}: not calibrated yet — {', '.join(uncal)}"
            " (plan critic-calibration-set)."
        )
    if cls in a.get("cross_family_required", []) and not critic.get("cross_family_present"):
        if stricter("C", mode) != mode:
            mode = "C"
        d.warnings.append(f"Risk class {cls} requires a cross-family critic sample; none ran.")
    if mode == "A" and not a.get("allow_auto_merge"):
        d.warnings.append("Mode A is a label only: allow_auto_merge is false in the profile.")
    d.mode = mode
    return d


# ── note for the owner ───────────────────────────────────────────────────
def render_note(decision: Decision, inputs: dict[str, Any], profile_meta: dict[str, Any]) -> str:
    plan = inputs.get("plan", {})
    out = [f"# DoD decision — {plan.get('title') or inputs.get('plan_id')}", ""]
    head = {
        "done": f"**Done — mode {decision.mode}**: {MODE_TEXT.get(decision.mode or '', '')}.",
        "block": "**Not done** — the implementer keeps working on the reasons below.",
        "escalate": (
            f"**Escalated to the owner — mode {decision.mode}**: the gate will not decide this."
        ),
    }[decision.outcome]
    out.append(head)
    out.append("")
    risk = ", ".join(decision.risk_paths[:5])
    out.append(f"Risk class: **{decision.risk_class}**" + (f" ({risk})" if risk else ""))
    out.append("")
    if decision.reasons:
        out.append("## Why" if decision.outcome != "done" else "## Reasons")
        out += [f"- {r['message']}" for r in decision.reasons]
        out.append("")
    if decision.would_change:
        out.append("## What sets the mode / what would change it")
        out += [f"- {w}" for w in decision.would_change]
        out.append("")
    if decision.warnings:
        out.append("## Warnings")
        out += [f"- {w}" for w in decision.warnings]
        out.append("")
    critic = inputs.get("critic") or {}
    if critic.get("questions"):
        out.append("## Critic")
        out.append("| Question | p | yes / valid | Evidence |")
        out.append("|---|---|---|---|")
        for q in critic["questions"]:
            p = q.get("p_violation")
            ev = ", ".join(f"`{e['file']}:{e['line']}`" for e in (q.get("evidence") or [])[:3])
            out.append(
                f"| {q['id']} | {'-' if p is None else f'{p:.2f}'} |"
                f" {q.get('violations', 0)} / {q.get('k_valid', 0)} | {ev or '-'} |"
            )
        out.append("")
    checks = inputs.get("checks", [])
    passed = sum(1 for c in checks if c.get("ok"))
    out.append(
        f"Checks: {passed}/{len(checks)} passed. Manual criteria left for the owner:"
        f" {plan.get('manual_criteria', 0)}."
    )
    out.append(
        f"Profile v{profile_meta.get('version', '?')} signed {profile_meta.get('signed', '?')}"
        f" by {profile_meta.get('owner', '?')} · critic {critic.get('critic_hash') or '-'}"
        f" · diff {inputs.get('diff_hash', '-')}"
    )
    return "\n".join(out) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────
def replay(path: Path) -> tuple[int, int, list[str]]:
    """(checked, skipped, mismatches) over the gate records of one run log."""
    checked = skipped = 0
    bad: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("kind") != "gate":
            continue
        if "profile" not in rec:  # recorded before the judge existed
            skipped += 1
            continue
        try:
            if rec["profile"] is None:
                raise ProfileError(rec.get("profile_error", "profile unreadable"))
            got = decide(rec["inputs"], validate(rec["profile"])).as_dict()
        except ProfileError as exc:
            got = profile_error_decision(str(exc)).as_dict()
        want = rec["decision"]
        keys = ("outcome", "mode", "risk_class")
        same = all(got[k] == want.get(k) for k in keys) and [r["code"] for r in got["reasons"]] == [
            r["code"] for r in want.get("reasons", [])
        ]
        checked += 1
        if not same:
            bad.append(
                f"seq {rec.get('seq')}: recorded {want.get('outcome')}/{want.get('mode')},"
                f" replayed {got['outcome']}/{got['mode']}"
            )
    return checked, skipped, bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    dcmd = sub.add_parser("decide", help="decide from an inputs JSON file and the repo's profile")
    dcmd.add_argument("--inputs", required=True)
    dcmd.add_argument("--profile", type=Path)
    r = sub.add_parser("replay", help="recompute every decision in a run log")
    r.add_argument("logs", nargs="+", type=Path)
    sub.add_parser("check-profile", help="validate docs/harness/profile.toml")
    args = ap.parse_args(argv)

    if args.cmd == "check-profile":
        try:
            p = load_profile(Path.cwd())
        except ProfileError as exc:
            print(f"judge: profile INVALID — {exc}", file=sys.stderr)
            return 1
        print(f"judge: profile v{p.version} OK")
        return 0
    if args.cmd == "decide":
        inputs = json.loads(Path(args.inputs).read_text(encoding="utf-8"))
        profile = (
            validate(_jsonable(tomllib.loads(args.profile.read_text(encoding="utf-8"))))
            if args.profile
            else load_profile(Path.cwd())
        )
        print(json.dumps(decide(inputs, profile).as_dict(), indent=2))
        return 0
    failed = False
    for log in args.logs:
        checked, skipped, bad = replay(log)
        print(
            f"judge: {log}: {checked} decision(s) replayed, {skipped} skipped (no profile recorded)"
        )
        for b in bad:
            print(f"  MISMATCH {b}", file=sys.stderr)
        failed |= bool(bad)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
