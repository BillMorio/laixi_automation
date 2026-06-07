# FarmOps

Local-only dashboard for orchestrating Instagram automations across a phone farm managed by **Laixi**.

> ⚠️ **Private repo only.** This contains real proxy IPs, references the on-device automation workflow, and is built for Instagram automation. **Do not publish.**

## What it does

- **Dashboard** at `http://127.0.0.1:8000/` showing every phone Laixi sees, each with a positional label (`01`, `02`, …) and a live status badge.
- **Account warming** — scroll Reels, like + save randomly for N minutes per device.
- **Smart comments** — read a post's caption from the on-device UI dump, send to Gemini for a one-liner, post it once with paste-verification (no doubling, no spam).
- **Instagram posting** — upload a video to the PC, re-mux for a valid duration header (fixes the IG-rejects-it bug), push to a phone, post a Reel.
- **Multi-device concurrency** — click two or more device cards, click Warm, both warm in parallel; each script gets its own subprocess + its own log; per-card status badges; multiplexed log view.
- **Settings UI** — edit `.env` (Gemini key, Apify token, …) from the browser; subprocesses pick up changes on next run, no server restart needed.

## Architecture (one sentence each)

- **`app.py`** — Python stdlib HTTP server (port 8000). Serves the dashboard, dispatches automations as subprocesses, exposes `/settings/env`.
- **`index.html`** — vanilla HTML/JS dashboard. Talks to the Laixi WebSocket (`ws://127.0.0.1:22221/`) directly for device list + live ADB; talks to `app.py` for spawning automations and editing settings.
- **`warm_account.py`, `comment_on_post.py`** — automation workers. Each takes `--device` so they can run on different phones in parallel.
- **`smart_comment.py`** — captioned-comment helper. Reads on-device caption from the uiautomator dump, asks Gemini, falls back to a generic comment list when there's no caption.

## Get started

See [SETUP.md](SETUP.md) for the new-machine install. TL;DR for a fresh clone:

```powershell
.\setup.bat            # one-time: pip install deps, seed .env from template
# Edit .env to paste your GEMINI_API_KEY, OR set it via the Settings tab in the dashboard
.\dashboard.bat start  # launch the server in a new console window
```

Then open <http://127.0.0.1:8000/index.html>.

**Make sure the Laixi desktop app is running first** — it provides the WebSocket at `ws://127.0.0.1:22221/` that the dashboard talks to.

## Layout

```
.
├── app.py                 # HTTP server + automation dispatcher
├── index.html             # dashboard UI
├── warm_account.py        # per-device warming automation
├── comment_on_post.py     # per-device commenting automation
├── smart_comment.py       # Gemini-based comment generation
├── selectors/             # captured UI maps (selectors + raw XML dumps for reference)
├── proxy-times.html       # live local-time table for each proxy SSID
├── device-times.html      # device -> proxy mapping with live local times
├── device-times.csv       # CSV snapshot of device times (for Google Sheets)
├── device_proxy_map.json  # source of truth: device number -> proxy slot
├── ig-accounts.csv        # scaffold for IG account credentials (Google Sheets)
├── dashboard.bat          # server lifecycle (start/stop/restart/status/urls)
├── setup.bat              # one-time installer
├── requirements.txt       # Python deps (websockets, requests)
├── .env.example           # template for GEMINI_API_KEY / APIFY / etc.
├── SETUP.md               # full deployment guide
├── ARCHITECTURE.md        # high-level architecture notes
├── SYSTEM-DESIGN.md       # 3-tier system design (local runner + online backend)
├── POSTING-WORKFLOW.md    # discovery notes for the IG posting flow
├── WARMING-WORKFLOW.md    # discovery notes for the warming flow
└── laixi-context.md       # original Laixi WS API notes
```

## Day-to-day commands

```
.\dashboard.bat start      # default — kills any old instance, launches the server
.\dashboard.bat stop
.\dashboard.bat restart
.\dashboard.bat status
.\dashboard.bat urls
```

For everything else, the dashboard is the UI.
