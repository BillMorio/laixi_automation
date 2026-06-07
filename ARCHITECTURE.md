# Laixi Custom Dashboard — Architecture

A locally-run web dashboard that automates Android phones (live control + Instagram
posting) by driving the **Laixi** desktop app's WebSocket API. Built to run on the
same computer that has the phones connected.

---

## 1. High-level picture

```
┌─────────────┐   HTTP (8000)    ┌──────────────────┐
│   Browser   │ ───────────────► │   app.py          │  Python stdlib HTTP server
│ (dashboard) │ ◄─────────────── │  - serves UI      │   + ffmpeg (video normalize)
│  index.html │   screenshots,   │  - /upload        │
│             │   video uploads  │  - /latest/<id>   │
└─────┬───────┘                  └──────────────────┘
      │
      │ WebSocket (22221)  — all device commands
      ▼
┌──────────────────┐   USB + ADB   ┌──────────────┐
│   Laixi app      │ ────────────► │  Phone(s)     │  Android devices
│ (3rd-party)      │ ◄──────────── │              │
│  WS API :22221   │   responses   └──────────────┘
└──────────────────┘
```

Two independent connections from the browser:
- **HTTP to `app.py`** (our server): loads the dashboard, serves device screenshots, receives video uploads.
- **WebSocket to Laixi** (`ws://127.0.0.1:22221/`): every device action (tap, swipe, screenshot, adb, file push). The browser talks to Laixi *directly* — `app.py` is not involved in device commands.

Laixi itself owns the USB/ADB connection to the phones; we never call ADB directly — we send Laixi an `adb` action and it runs the shell command on the device.

---

## 2. Technology stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | **Vanilla HTML/CSS/JS** | Single `index.html`, no framework, no build step |
| Backend | **Python 3.10+ stdlib** (`http.server`) | No Flask/Django; ~120 lines |
| Video processing | **ffmpeg / ffprobe 7.0** | Must be installed and on PATH |
| Device bridge | **Laixi v1.1.5.1+** | Provides the WebSocket API on port 22221 |
| Device comms | **ADB** | Used *by Laixi* internally; we send shell commands through Laixi's `adb` action |
| Screen reading | **uiautomator** (built into Android) | Dumps the on-screen element tree for screen-aware automation |

No external Python packages required for the server. (Dev/test scripts use the
`websockets` package, but the dashboard itself uses the browser's native WebSocket.)

---

## 3. Components

### `app.py` — local HTTP server (port 8000)
- **Static files**: serves `index.html` and assets.
- **`GET /latest/<deviceId>`**: returns the newest screenshot PNG for a device from
  `screenshots/`, and deletes older frames (keeps the live mirror disk usage bounded).
- **`POST /upload?name=<file>`**: receives a raw video upload, then **normalizes it with
  ffmpeg** and returns `{path, size, duration, mode}`. Normalization is critical —
  see §5.
- Threaded server so screenshot polling and uploads don't block each other.

### `index.html` — the dashboard (all client logic)
- **WebSocket client**: connects to Laixi, auto-reconnects, logs all traffic.
- **Live mirror**: polls the `screen` action in a tight loop, loads frames as blob URLs
  (double-buffered) for a ~5–10 fps mirror. (Laixi has no real video-stream API.)
- **Touch control**: an invisible overlay (`#touchLayer`) captures pointer events and
  sends `pointerEvent` press/move/release with normalized 0–1 coords.
- **Hardware buttons**: Home/Back/Recent/Vol/Power via `adb input keyevent`.
- **Helpers**: `adbCmd` (fire-and-forget), `adbQuery` (promise that resolves with a
  command's stdout), organic `oTap`/`oSwipe` (jittered taps + human-like delays).
- **Screen-awareness**: `uiDump` (uiautomator → XML), `findCenter` (locate a button by
  its text/description and return its tap center), `tapByText`, `dismissNotices`.
- **Feature flows**: Instagram posting, WhatsApp sender, clipboard, quick actions.

### Laixi (third-party, not ours)
- Desktop app that manages USB-connected phones and exposes a JSON WebSocket API.
- All messages: `{ "action": "<name>", "comm": { ... } }`; responses
  `{ "StatusCode": 200, "result": <null | stringified-JSON> }`.
- Key actions we use: `List`, `screen`, `pointerEvent`, `adb`, `beginfilesend`,
  `writeclipboard`. (`adb` is the escape hatch for everything Laixi doesn't expose.)

---

## 4. Instagram posting pipeline (the core flow)

1. **Upload** (browser → `app.py`): video is uploaded and **normalized** (ffmpeg).
2. **Push** (browser → Laixi `beginfilesend`): the normalized file is sent to the phone's
   `DCIM/Camera/`. The transfer is async + slow, so the dashboard **polls the file size**
   until it matches the full upload, then triggers a media scan.
3. **Safety check**: before posting, verify the newest file in `DCIM/Camera` is the one we
   pushed (aborts if a screenshot or other file slipped in).
4. **Pre-grant permissions**: `pm grant` IG's camera/photos perms so system dialogs don't appear.
5. **Cold-start IG**: `am force-stop` then launch, so it always opens to a known screen.
6. **Navigate (screen-aware)**: tap `+` and the newest-video thumbnail (pixel coords, since
   they're icons), then an **adaptive loop** — read the screen each step and tap **Share**
   if present (publish) or **Next** (advance), dismissing notices in between.
7. **Post-share cascade**: decline the Facebook cross-post ("Not now"), confirm any second
   Share, dismiss "Sharing posts"/"OK"/"Continue".
8. **Confirm**: watch the "Sharing to Reels…" banner lifecycle to report a per-post verdict
   (posted / uploading / failed).

**Coordinate-based** steps (`+`, thumbnail) are resolution-specific (calibrated for
**1080×2400**). **Text-based** steps (Next/Share/notices) are robust to layout shifts
because they find the button by its label via uiautomator.

---

## 5. Why video normalization matters

Videos ripped/downloaded from social media often have a **zeroed duration field in the
MP4 header** (`mvhd` atom). Players compute the real length from the stream, so they play
fine — but Android's media indexer and Instagram read the header directly, see `0`, and
treat it as a 0-second video → it shows **0:00** and **Instagram rejects it**.

`app.py` fixes this on every upload:
- **H.264 video** → fast lossless **re-mux** (`ffmpeg -c:v copy -c:a aac -movflags +faststart`) — rewrites a correct header in well under a second.
- **Other codecs** → re-encode to H.264.

This is the single most important reliability fix in the system.

---

## 6. File / directory layout

```
laixi-custom-ui/
├── app.py                 # HTTP server + ffmpeg video normalization
├── index.html             # the entire dashboard (UI + all client logic)
├── ARCHITECTURE.md         # this document
├── laixi-context.md       # Laixi API reference
├── screenshots/           # live-mirror frames (auto-managed, safe to empty)
├── uploads/               # normalized videos staged for pushing
└── test_*.py              # dev/diagnostic scripts (not needed at runtime)
```

---

## 7. Deploying to the computer that runs the phones

That machine already has **Laixi** + **ADB** + the **phones connected**. To add this dashboard:

1. **Install Python 3.10+** — ensure `python` is on PATH.
2. **Install ffmpeg** — ensure `ffmpeg` and `ffprobe` are on PATH (`ffmpeg -version` to check).
3. **Copy `app.py` and `index.html`** into a folder (e.g. `laixi-custom-ui/`).
4. **Start Laixi**, confirm the phones appear and the **API is enabled** (WebSocket on `22221`).
5. **Run the server**: `python app.py` (from that folder).
6. **Open** `http://127.0.0.1:8000/index.html` in a browser on that same machine.

Requirements summary: Python 3.10+, ffmpeg/ffprobe, Laixi (running, API on), a browser.
No internet required except for the phones' own network access (to actually post).

---

## 8. Current limitations & next steps for scale (20+ phones)

- **Single active device**: the dashboard drives one selected device at a time. Scaling to
  many phones needs a **device picker + per-phone status grid** and running flows in
  parallel/queued across devices.
- **Resolution-coupled coordinates**: the `+` and thumbnail taps assume 1080×2400. Other
  phone models need their own coordinates (store a coord set per device model).
- **IG UI drift**: Instagram changes its flow periodically. New surprise screens are handled
  by adding their button label to `dismissNotices()` — cheap to extend.
- **Mirror FPS**: ~5–10 fps (PNG polling; Laixi has no true video stream). Fine for control
  and verification, not for smooth viewing.
- **No persistence/scheduling yet**: no job queue, scheduling, content rotation, or
  per-account history — these are the natural additions for a real posting operation.
