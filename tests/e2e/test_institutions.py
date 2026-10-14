# SPDX-License-Identifier: AGPL-3.0-or-later
"""E2E tests for Feature: Institution Management — logo upload.

Covers: KAL-INS-009

Guards the NiceGUI 3.x upload event API: the add/edit logo handlers used
the removed 2.x `e.name` / `e.content.read()` shape, so the upload silently
failed and no preview or list avatar ever appeared. This walks the real
upload path end to end.
"""

from __future__ import annotations

import base64
from pathlib import Path

from playwright.sync_api import Page, expect

# A 1x1 transparent PNG — enough to exercise save_logo + the static mount.
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_upload_logo_when_adding_institution(page: Page, base_url: str, tmp_path: Path) -> None:
    """Covers: KAL-INS-009

    Uploading a PNG in the Add Institution dialog shows a preview, and the
    saved institution renders that logo (an ``/logos/..`` image) in the list.
    """
    logo = tmp_path / "revolut.png"
    logo.write_bytes(_PNG_1x1)

    page.goto(f"{base_url}/institutions")
    add_button = page.get_by_role("button", name="Add Institution")
    expect(add_button).to_be_visible(timeout=5000)

    add_button.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible(timeout=5000)

    dialog.get_by_label("Name").fill("Revolut E2E Logo")
    dialog.locator('input[type="file"]').set_input_files(str(logo))

    # The handler ran only if the preview image got a /logos/ source.
    expect(dialog.locator('img[src^="/logos/"]')).to_be_visible(timeout=5000)

    dialog.get_by_role("button", name="Save").click()
    expect(dialog).to_be_hidden(timeout=5000)

    main = page.get_by_role("main")
    expect(main.get_by_text("Revolut E2E Logo", exact=True)).to_be_visible(timeout=5000)
    expect(main.locator('img[src^="/logos/"]').first).to_be_visible(timeout=5000)
