# Contributing to Kaleta

Thank you for your interest in Kaleta. This file is a short guide to how we
work; the authoritative details live in the linked documents below.

## How work is organised

Every change should trace to **one plan** in [`docs/plans/`](docs/plans/). Use
the template and lifecycle in [`docs/plans/README.md`](docs/plans/README.md).
Keep PRs focused on a single plan (or a clearly named section of one).

## Working Agreement

The **Definition of Done** in [`AGENTS.md`](AGENTS.md#working-agreement-definition-of-done)
applies to human contributors and AI agents alike. Read it before your first PR.
Highlights:

- Scope comes from the plan — do not expand silently.
- Architecture contracts (`lint-imports`) and BDD coverage
  (`scripts/spec_coverage.py`) are CI-enforced.
- New user-facing behaviour needs a `KAL-` scenario in
  [`docs/bdd.md`](docs/bdd.md).

## Development setup

```bash
uv sync --group dev
```

Run the full gate before opening a PR:

```bash
./scripts/verify.sh
```

Add `--e2e` when you change anything under `src/kaleta/views/`:

```bash
./scripts/verify.sh --e2e
```

See [`docs/getting-started.md`](docs/getting-started.md) for installation,
environment variables, Docker, and optional extras.

## Contributor License Agreement

Kaleta uses an open-core model under AGPL-3.0-or-later. External contributors
must sign the [Individual Contributor License Agreement](docs/cla.md) before
their first pull request is merged. The CLA Assistant bot will comment on your
PR with signing instructions.

## Questions

- **Product / architecture:** [documentation site](https://dawidadamski.github.io/kaleta/)
- **Security issues:** see [`SECURITY.md`](SECURITY.md) — do not open public
  issues for vulnerabilities.
