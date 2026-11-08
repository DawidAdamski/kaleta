# Harness: the owner's rules for goal mode

Everything in this folder is legislation in the sense of
[ADR-39](../adr/039-measurable-critic-deterministic-judge.md): the owner writes
it, the implementer agent cannot change it, and the gate and critic only read
it. See [goal-mode.md](../goal-mode.md) for how the loop uses it.

| Path | What it is |
|---|---|
| `protected-paths.txt` | paths the agent may not change (hook and gate) |
| `critic-questions.toml` | the narrow questions the critic answers, with evidence |
| `profile.toml` | the judge's law: vetoes, green-washing patterns, risk classes, thresholds, autonomy per class, calibration — signed by the owner |
| `runs/` | run logs, one hash-chained JSONL per plan, written by the gate and the critic |

Changes here need maintainer mode (`KALETA_HARNESS_MAINTAINER=1 claude`).
The gate reads `profile.toml` and `protected-paths.txt` as they are on the
merge-base, so a diff cannot change the law it is judged by. Bump
`[meta] version` and `signed` when you change the profile.
