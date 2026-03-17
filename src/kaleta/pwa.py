"""PWA setup — manifest, service worker, static assets."""
from __future__ import annotations

from pathlib import Path

from fastapi import Response
from nicegui import app as nicegui_app

_STATIC_DIR = Path(__file__).parent / "static"

PWA_HEAD = """
<link rel="manifest" href="/manifest.json">
<link rel="icon" type="image/svg+xml" href="/static/icons/icon.svg">
<meta name="theme-color" content="#1976d2">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Kaleta">
<link rel="apple-touch-icon" href="/static/icons/icon.svg">
<script>
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js');
  }
</script>
""".strip()


def setup() -> None:
    """Register static files and PWA endpoints with the NiceGUI/FastAPI app."""
    nicegui_app.add_static_files("/static", str(_STATIC_DIR))

    @nicegui_app.get("/manifest.json", include_in_schema=False)
    async def _manifest() -> Response:
        return Response(
            content=(_STATIC_DIR / "manifest.json").read_text(encoding="utf-8"),
            media_type="application/manifest+json",
        )

    @nicegui_app.get("/sw.js", include_in_schema=False)
    async def _service_worker() -> Response:
        return Response(
            content=(_STATIC_DIR / "sw.js").read_text(encoding="utf-8"),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )
