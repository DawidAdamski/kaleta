# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the KALETA_DEMO feature flag."""

from __future__ import annotations

from kaleta.config.settings import Settings


def test_demo_defaults_false() -> None:
    settings = Settings.model_validate({"debug": True})
    assert settings.demo is False


def test_demo_enabled_from_env_shape() -> None:
    settings = Settings.model_validate({"debug": True, "demo": True})
    assert settings.demo is True
