# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for NiceguiStorageService: environment, permissions, sweep."""

from __future__ import annotations

import logging
import os
import stat
import time
import types
from collections.abc import Generator
from pathlib import Path

import pytest

from kaleta.services import nicegui_storage_service as svc_mod
from kaleta.services.nicegui_storage_service import NiceguiStorageService


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("NICEGUI_STORAGE_PATH", "NICEGUI_REDIS_URL", "NICEGUI_REDIS_KEY_PREFIX"):
        monkeypatch.delenv(key, raising=False)


class TestConfigureEnvironment:
    def test_creates_the_directory_owner_only(self, tmp_path: Path, clean_env: None) -> None:
        target = tmp_path / "nicegui"
        path = NiceguiStorageService.configure_environment(target)
        assert path == target.resolve()
        assert _mode(target) == 0o700
        assert os.environ["NICEGUI_STORAGE_PATH"] == str(target.resolve())

    def test_without_redis_leaves_nicegui_on_files(self, tmp_path: Path, clean_env: None) -> None:
        NiceguiStorageService.configure_environment(tmp_path / "nicegui")
        assert "NICEGUI_REDIS_URL" not in os.environ
        assert "NICEGUI_REDIS_KEY_PREFIX" not in os.environ

    def test_redis_url_moves_nicegui_storage_to_redis(
        self, tmp_path: Path, clean_env: None
    ) -> None:
        NiceguiStorageService.configure_environment(
            tmp_path / "nicegui", redis_url="redis://cache:6379/0"
        )
        assert os.environ["NICEGUI_REDIS_URL"] == "redis://cache:6379/0"
        assert os.environ["NICEGUI_REDIS_KEY_PREFIX"] == "kaleta:"

    def test_explicit_nicegui_env_still_wins(
        self, tmp_path: Path, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NICEGUI_REDIS_URL", "redis://explicit:6379/1")
        custom = tmp_path / "custom"
        monkeypatch.setenv("NICEGUI_STORAGE_PATH", str(custom))
        path = NiceguiStorageService.configure_environment(
            tmp_path / "ignored", redis_url="redis://cache:6379/0"
        )
        assert path == custom.resolve()
        assert os.environ["NICEGUI_REDIS_URL"] == "redis://explicit:6379/1"


class TestStorageDir:
    def test_defaults_to_the_path_nicegui_writes_to(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NICEGUI_STORAGE_PATH", str(tmp_path / "override"))
        assert NiceguiStorageService().storage_dir == (tmp_path / "override").resolve()

    def test_an_explicit_dir_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NICEGUI_STORAGE_PATH", str(tmp_path / "override"))
        service = NiceguiStorageService(storage_dir=tmp_path / "explicit")
        assert service.storage_dir == (tmp_path / "explicit").resolve()


class TestTightenPermissions:
    def test_restricts_directory_and_files(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        root = tmp_path / "nicegui"
        root.mkdir(mode=0o755)
        root.chmod(0o755)
        loose = root / "storage-user-a.json"
        loose.write_text("{}", encoding="utf-8")
        loose.chmod(0o644)
        tight = root / "storage-user-b.json"
        tight.write_text("{}", encoding="utf-8")
        tight.chmod(0o600)

        with caplog.at_level(logging.INFO, logger=svc_mod.__name__):
            fixed = NiceguiStorageService(storage_dir=root).tighten_permissions()

        assert fixed == 2
        assert _mode(root) == 0o700
        assert _mode(loose) == 0o600
        assert _mode(tight) == 0o600
        assert len([r for r in caplog.records if "Restricted permissions" in r.message]) == 1

    def test_says_nothing_when_nothing_needed_fixing(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        root = tmp_path / "nicegui"
        root.mkdir()
        root.chmod(0o700)
        (root / "storage-user-a.json").write_text("{}", encoding="utf-8")
        (root / "storage-user-a.json").chmod(0o600)

        with caplog.at_level(logging.INFO, logger=svc_mod.__name__):
            fixed = NiceguiStorageService(storage_dir=root).tighten_permissions()

        assert fixed == 0
        assert not [r for r in caplog.records if "Restricted permissions" in r.message]

    def test_missing_directory_is_a_no_op(self, tmp_path: Path) -> None:
        assert NiceguiStorageService(storage_dir=tmp_path / "absent").tighten_permissions() == 0

    def test_windows_is_a_no_op(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = tmp_path / "nicegui"
        root.mkdir()
        root.chmod(0o755)
        monkeypatch.setattr(svc_mod, "os", types.SimpleNamespace(name="nt", environ=os.environ))
        assert NiceguiStorageService(storage_dir=root).tighten_permissions() == 0
        assert _mode(root) == 0o755


class TestRestrictNewFiles:
    @pytest.fixture(autouse=True)
    def _restore_umask(self) -> Generator[None]:
        original = os.umask(0o022)
        os.umask(original)
        yield
        os.umask(original)

    def test_new_files_are_owner_only(self, tmp_path: Path) -> None:
        os.umask(0o022)
        NiceguiStorageService.restrict_new_files()
        created = tmp_path / "storage-user-new.json"
        created.write_text("{}", encoding="utf-8")
        # How NiceGUI saves: write a temp file, rename it over the real one.
        tmp = tmp_path / "storage-user-new.json.tmp"
        tmp.write_text('{"a": 1}', encoding="utf-8")
        tmp.replace(created)
        assert _mode(created) == 0o600

    def test_a_stricter_umask_stays(self) -> None:
        os.umask(0o277)
        NiceguiStorageService.restrict_new_files()
        assert os.umask(0o022) == 0o277


class TestSweepStale:
    def test_removes_only_files_past_the_window(self, tmp_path: Path) -> None:
        root = tmp_path / "nicegui"
        root.mkdir()
        fresh = root / "storage-fresh.json"
        stale = root / "storage-stale.json"
        fresh.write_text("{}", encoding="utf-8")
        stale.write_text("{}", encoding="utf-8")
        old = time.time() - 31 * 24 * 60 * 60
        os.utime(stale, (old, old))

        removed = NiceguiStorageService(storage_dir=root).sweep_stale()

        assert removed == 1
        assert fresh.is_file()
        assert not stale.exists()

    def test_missing_directory_is_a_no_op(self, tmp_path: Path) -> None:
        assert NiceguiStorageService(storage_dir=tmp_path / "absent").sweep_stale() == 0
