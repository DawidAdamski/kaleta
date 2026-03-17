"""Unit tests for the PWA module (pwa.py).

Covers:
- PWA_HEAD string contains all required HTML tags and script
- Static files exist on disk (manifest.json, sw.js, icon.svg)
- manifest.json is valid JSON with required PWA fields
- sw.js contains the expected service-worker event listeners and cache identifier
- _STATIC_DIR resolves to the correct absolute path
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kaleta.pwa import PWA_HEAD, _STATIC_DIR


# ---------------------------------------------------------------------------
# PWA_HEAD content
# ---------------------------------------------------------------------------


class TestPwaHead:
    """PWA_HEAD must include every tag required for a PWA-capable page."""

    def test_manifest_link_present(self):
        assert '<link rel="manifest" href="/manifest.json">' in PWA_HEAD

    def test_icon_link_present(self):
        assert 'href="/static/icons/icon.svg"' in PWA_HEAD

    def test_theme_color_meta_present(self):
        assert '<meta name="theme-color" content="#1976d2">' in PWA_HEAD

    def test_mobile_web_app_capable_meta_present(self):
        assert '<meta name="mobile-web-app-capable" content="yes">' in PWA_HEAD

    def test_apple_mobile_web_app_capable_meta_present(self):
        assert '<meta name="apple-mobile-web-app-capable" content="yes">' in PWA_HEAD

    def test_apple_mobile_web_app_status_bar_style_meta_present(self):
        assert (
            '<meta name="apple-mobile-web-app-status-bar-style" content="default">'
            in PWA_HEAD
        )

    def test_apple_mobile_web_app_title_meta_present(self):
        assert '<meta name="apple-mobile-web-app-title" content="Kaleta">' in PWA_HEAD

    def test_apple_touch_icon_link_present(self):
        assert '<link rel="apple-touch-icon" href="/static/icons/icon.svg">' in PWA_HEAD

    def test_service_worker_registration_script_present(self):
        assert "serviceWorker" in PWA_HEAD
        assert "navigator.serviceWorker.register('/sw.js')" in PWA_HEAD

    def test_service_worker_registration_guarded_by_feature_check(self):
        assert "'serviceWorker' in navigator" in PWA_HEAD

    def test_head_is_non_empty_string(self):
        assert isinstance(PWA_HEAD, str)
        assert len(PWA_HEAD) > 0

    def test_head_does_not_start_or_end_with_whitespace(self):
        # .strip() is applied in the module — verify no leading/trailing blank lines
        assert PWA_HEAD == PWA_HEAD.strip()


# ---------------------------------------------------------------------------
# Static directory
# ---------------------------------------------------------------------------


class TestStaticDir:
    """_STATIC_DIR must point to the real static folder inside the package."""

    def test_static_dir_is_path_object(self):
        assert isinstance(_STATIC_DIR, Path)

    def test_static_dir_exists(self):
        assert _STATIC_DIR.exists(), f"_STATIC_DIR does not exist: {_STATIC_DIR}"

    def test_static_dir_is_directory(self):
        assert _STATIC_DIR.is_dir(), f"_STATIC_DIR is not a directory: {_STATIC_DIR}"

    def test_static_dir_named_static(self):
        assert _STATIC_DIR.name == "static"

    def test_static_dir_parent_is_kaleta_package(self):
        # The parent folder should be the kaleta package directory
        assert _STATIC_DIR.parent.name == "kaleta"


# ---------------------------------------------------------------------------
# Static files exist on disk
# ---------------------------------------------------------------------------


class TestStaticFilesExist:
    """Every static asset referenced by the PWA must be present on disk."""

    def test_manifest_json_exists(self):
        assert (_STATIC_DIR / "manifest.json").is_file()

    def test_sw_js_exists(self):
        assert (_STATIC_DIR / "sw.js").is_file()

    def test_icon_svg_exists(self):
        assert (_STATIC_DIR / "icons" / "icon.svg").is_file()

    def test_icons_directory_exists(self):
        assert (_STATIC_DIR / "icons").is_dir()


# ---------------------------------------------------------------------------
# manifest.json content
# ---------------------------------------------------------------------------


class TestManifestJson:
    """manifest.json must be valid JSON containing required PWA fields."""

    @pytest.fixture(scope="class")
    def manifest(self) -> dict:
        raw = (_STATIC_DIR / "manifest.json").read_text(encoding="utf-8")
        return json.loads(raw)

    def test_manifest_is_valid_json(self):
        raw = (_STATIC_DIR / "manifest.json").read_text(encoding="utf-8")
        parsed = json.loads(raw)  # raises json.JSONDecodeError if invalid
        assert isinstance(parsed, dict)

    def test_manifest_has_name(self, manifest: dict):
        assert "name" in manifest
        assert manifest["name"] == "Kaleta"

    def test_manifest_has_short_name(self, manifest: dict):
        assert "short_name" in manifest
        assert isinstance(manifest["short_name"], str)

    def test_manifest_has_start_url(self, manifest: dict):
        assert "start_url" in manifest
        assert manifest["start_url"] == "/"

    def test_manifest_has_display(self, manifest: dict):
        assert "display" in manifest
        assert manifest["display"] == "standalone"

    def test_manifest_has_icons(self, manifest: dict):
        assert "icons" in manifest
        assert isinstance(manifest["icons"], list)
        assert len(manifest["icons"]) >= 1

    def test_manifest_icons_have_required_fields(self, manifest: dict):
        required_icon_keys = {"src", "sizes", "type"}
        for icon in manifest["icons"]:
            missing = required_icon_keys - icon.keys()
            assert not missing, f"Icon entry missing keys: {missing}"

    def test_manifest_has_theme_color(self, manifest: dict):
        assert "theme_color" in manifest
        assert manifest["theme_color"] == "#1976d2"

    def test_manifest_has_background_color(self, manifest: dict):
        assert "background_color" in manifest

    def test_manifest_scope_is_root(self, manifest: dict):
        assert manifest.get("scope") == "/"


# ---------------------------------------------------------------------------
# sw.js content
# ---------------------------------------------------------------------------


class TestServiceWorkerJs:
    """sw.js must contain the cache identifier and all three lifecycle listeners."""

    @pytest.fixture(scope="class")
    def sw_content(self) -> str:
        return (_STATIC_DIR / "sw.js").read_text(encoding="utf-8")

    def test_sw_defines_cache_name(self, sw_content: str):
        assert "CACHE_NAME" in sw_content

    def test_sw_cache_name_has_kaleta_prefix(self, sw_content: str):
        assert "kaleta" in sw_content

    def test_sw_has_install_event_listener(self, sw_content: str):
        assert "addEventListener('install'" in sw_content

    def test_sw_has_activate_event_listener(self, sw_content: str):
        assert "addEventListener('activate'" in sw_content

    def test_sw_has_fetch_event_listener(self, sw_content: str):
        assert "addEventListener('fetch'" in sw_content

    def test_sw_install_opens_cache(self, sw_content: str):
        assert "caches.open" in sw_content

    def test_sw_activate_deletes_old_caches(self, sw_content: str):
        assert "caches.delete" in sw_content

    def test_sw_fetch_uses_caches_match(self, sw_content: str):
        assert "caches.match" in sw_content

    def test_sw_skips_waiting_on_install(self, sw_content: str):
        assert "skipWaiting" in sw_content

    def test_sw_claims_clients_on_activate(self, sw_content: str):
        assert "clients.claim" in sw_content

    def test_sw_guards_api_calls(self, sw_content: str):
        # API requests must bypass the cache
        assert "/api/" in sw_content

    def test_sw_is_non_empty(self, sw_content: str):
        assert len(sw_content.strip()) > 0
