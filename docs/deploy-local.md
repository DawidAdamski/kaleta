# Local deployment (launchd / systemd)

Run Kaleta as a localhost web service so it starts with your machine — no
terminal window required. Bind to loopback only; use Docker Compose (see
[getting started](getting-started.md)) when you need a container.

## Prerequisites

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- A clone of this repository (path below is an example — pin
  `WorkingDirectory` / `WorkingDirectory=` to **your** clone)
- First-run setup completed once (`uv run kaleta`, choose a DB, create account)

Recommended env in the unit/plist (or a `.env` in the working directory):

```env
KALETA_MODE=web
KALETA_HOST=127.0.0.1
KALETA_PORT=8080
KALETA_SECRET_KEY=<long-random-string>
```

NiceGUI session files are stored under `~/.kaleta/nicegui/` (not the repo
root). Stale storage files older than 30 days are removed on startup.

## Health probe

Unauthenticated:

```bash
curl -sS http://127.0.0.1:8080/api/v1/health
# alias:
curl -sS http://127.0.0.1:8080/health
```

Example JSON:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database_ok": true,
  "migrations_pending": false
}
```

HTTP **503** when `database_ok` is false. `migrations_pending` is
report-only (startup auto-migrate is separate; see README).

## macOS — launchd

1. Adjust paths in the plist (`REPLACE_WITH_REPO` and the `uv` binary from
   `which uv`).
2. Install and load:

```bash
# Write the plist below to ~/Library/LaunchAgents/pl.kaleta.app.plist, then:
launchctl load ~/Library/LaunchAgents/pl.kaleta.app.plist
```

Example `~/Library/LaunchAgents/pl.kaleta.app.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>pl.kaleta.app</string>
  <key>WorkingDirectory</key>
  <string>/Users/YOU/Projects/kaleta</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOU/.local/bin/uv</string>
    <string>run</string>
    <string>kaleta</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>KALETA_MODE</key>
    <string>web</string>
    <key>KALETA_HOST</key>
    <string>127.0.0.1</string>
    <key>KALETA_PORT</key>
    <string>8080</string>
    <key>KALETA_SECRET_KEY</key>
    <string>REPLACE_WITH_SECRET</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/YOU/Library/Logs/kaleta.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/YOU/Library/Logs/kaleta.err</string>
</dict>
</plist>
```

Unload: `launchctl unload ~/Library/LaunchAgents/pl.kaleta.app.plist`.

## Linux — systemd user unit

Example `~/.config/systemd/user/kaleta.service`:

```ini
[Unit]
Description=Kaleta personal finance (localhost web)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/YOU/Projects/kaleta
Environment=KALETA_MODE=web
Environment=KALETA_HOST=127.0.0.1
Environment=KALETA_PORT=8080
Environment=KALETA_SECRET_KEY=REPLACE_WITH_SECRET
ExecStart=/home/YOU/.local/bin/uv run kaleta
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now kaleta.service
systemctl --user status kaleta.service
curl -sS http://127.0.0.1:8080/api/v1/health
```

Stop: `systemctl --user stop kaleta.service`.

## Notes

- Keep `KALETA_HOST=127.0.0.1` unless you intentionally expose the UI on
  your LAN (see the auth roadmap before doing that).
- Pin `WorkingDirectory` to the clone where `uv run kaleta` works; do not
  rely on a relative shell cwd.
- Upgrades: `git pull && uv sync` in that directory, then restart the
  agent/unit. The app auto-migrates the configured DB on start.
