# SPDX-License-Identifier: AGPL-3.0-or-later
"""The shipped container images must run as a non-root user.

Covers: KAL-SEC-005 (assessment F-6 / Trivy DS-0002).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINERFILES = ("Containerfile", "Containerfile.full")
DEPLOYMENT = REPO_ROOT / "deploy" / "k3s" / "templates" / "deployment.yaml"
COMPOSE_FILES = ("docker-compose.yml", "compose.hosted-dev.yml")


def _user_directives(dockerfile_text: str) -> list[str]:
    """Every ``USER <arg>`` directive, in order, with its argument."""
    users: list[str] = []
    for line in dockerfile_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("USER "):
            users.append(stripped.split(maxsplit=1)[1].strip())
    return users


def _useradd_uid(dockerfile_text: str) -> int:
    """The uid pinned by the image's ``useradd --uid N``."""
    match = re.search(r"--uid\s+(\d+)", dockerfile_text)
    assert match, "no `useradd --uid N` in the Containerfile"
    return int(match.group(1))


@pytest.mark.parametrize("name", CONTAINERFILES)
def test_containerfile_declares_a_non_root_user(name: str) -> None:
    """Each image declares a non-root USER before its start command.

    Covers: KAL-SEC-005
    """
    text = (REPO_ROOT / name).read_text(encoding="utf-8")
    users = _user_directives(text)
    assert users, f"{name} declares no USER — the image would run as root"
    # The effective user is the last USER directive; strip any ``:group``.
    final_user = users[-1].split(":", 1)[0]
    assert final_user not in {"root", "0"}, f"{name} still runs as {final_user!r}"
    assert _useradd_uid(text) != 0, f"{name} pins uid 0"


def test_deployment_pins_run_as_non_root() -> None:
    """The k3s Deployment pins runAsNonRoot so the cluster refuses a root container.

    A line-anchored match so a commented-out ``# runAsNonRoot`` does not pass.

    Covers: KAL-SEC-005
    """
    text = DEPLOYMENT.read_text(encoding="utf-8")
    assert re.search(r"^\s*runAsNonRoot: true\s*$", text, re.MULTILINE)


def test_deployment_run_as_user_matches_the_image_uid() -> None:
    """runAsUser is non-root and matches the uid baked into the images.

    A `runAsNonRoot` pod whose `runAsUser` disagreed with the image user would
    fail at pod start, so the two must stay in lock-step.

    Covers: KAL-SEC-005
    """
    deployment = DEPLOYMENT.read_text(encoding="utf-8")
    run_as_user = re.search(r"^\s*runAsUser:\s*(\d+)\s*$", deployment, re.MULTILINE)
    assert run_as_user, "the Deployment does not pin runAsUser"
    uid = int(run_as_user.group(1))
    assert uid != 0, "runAsUser is root"

    image_uids = {
        _useradd_uid((REPO_ROOT / name).read_text(encoding="utf-8")) for name in CONTAINERFILES
    }
    assert image_uids == {uid}, f"runAsUser {uid} must match the image uid(s) {image_uids}"


def test_sessions_volume_is_mounted_under_the_user_home_not_root() -> None:
    """The session volume is mounted under the user's home, not /root — in the
    Deployment and in both Compose files, so none silently stops persisting.

    Covers: KAL-SEC-005
    """
    for rel in (DEPLOYMENT.relative_to(REPO_ROOT), *COMPOSE_FILES):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "/root/.kaleta" not in text, f"{rel} still mounts sessions under root"
        assert "/home/app/.kaleta" in text, f"{rel} does not mount the home sessions path"
