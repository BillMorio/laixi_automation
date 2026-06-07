# FarmOps — Setup on a new Windows machine

You need three pieces of software installed on the target Windows box, then one command to install Python deps, then one command to start the server.

## 1. Prerequisites (install once, before this folder is useful)

| What | Why | Get it |
|---|---|---|
| **Python 3.10+** | Runs `app.py` + the automations | https://python.org — **tick "Add python.exe to PATH" during install** |
| **ffmpeg** (optional but recommended) | Re-muxes uploaded videos so Instagram doesn't reject them with a 0:00 duration | `winget install Gyan.FFmpeg` (then restart the terminal so PATH refreshes) |
| **Laixi desktop app** | Provides the WebSocket at `ws://127.0.0.1:22221/` that the dashboard talks to. The dashboard is useless without it | Install it the way you already do on the existing machine |

## 2. Drop the folder on the new machine

Copy the entire `laixi-custom-ui` folder somewhere stable (Desktop, `C:\farmops\`, wherever). Path can contain spaces — the scripts handle it.

## 3. Run setup (once)

Open a terminal **inside the folder**, then:

**PowerShell:**
```
.\setup.bat
```

**cmd.exe:**
```
setup.bat
```

> ⚠️ **PowerShell needs the `.\` prefix.** `dashboard.bat` and `setup.bat` won't run as bare names in PowerShell — type `.\dashboard.bat` and `.\setup.bat`. From cmd.exe both forms work.

`setup.bat`:
- verifies Python is on PATH
- runs `pip install -r requirements.txt` (websockets + requests)
- warns if ffmpeg/ffprobe aren't on PATH (won't fail — just skips video re-mux)
- creates a fresh `.env` from `.env.example` if there isn't one yet

It's safe to re-run; it skips anything already in place.

## 4. Add your Gemini key (only if you want Smart Comment)

Open `.env` in any text editor and fill in:

```
GEMINI_API_KEY=AIza...
```

Get a key at https://aistudio.google.com/apikey. **If you skip this, everything still works** — Smart Comment just falls back to its generic comments list.

## 5. Start the dashboard

Make sure **Laixi is running first** (devices won't appear otherwise).

**PowerShell:**
```
.\dashboard.bat start
```

**cmd.exe:**
```
dashboard.bat start
```

This:
1. kills any old `python app.py` process to free port 8000,
2. opens a **new console window** running the server (you can see live logs there; Ctrl+C in that window also stops it),
3. health-checks `http://127.0.0.1:8000/` and prints either `Server responding (HTTP 200)` or a warning,
4. prints the three URLs you'll use.

Then open in your browser:

- **Dashboard:** http://127.0.0.1:8000/index.html
- **Proxy times:** http://127.0.0.1:8000/proxy-times.html
- **Device times:** http://127.0.0.1:8000/device-times.html

## 6. Day-to-day commands

```
.\dashboard.bat start      # start (default if no arg)
.\dashboard.bat stop       # stop
.\dashboard.bat restart    # stop + start
.\dashboard.bat status     # RUNNING (PID ...) or STOPPED
.\dashboard.bat urls       # just print the URLs
```

### Optional — make it a one-word command from anywhere

If you'd rather type just `dashboard` from any folder, add this to your PowerShell profile (`notepad $PROFILE` in PowerShell, create the file if it doesn't exist):

```powershell
function dashboard { & "C:\full\path\to\laixi-custom-ui\dashboard.bat" @args }
```

Now `dashboard start` works from any folder, any PowerShell window.

## What's actually in this folder

| File | Purpose |
|---|---|
| `app.py` | The HTTP server (port 8000). Serves the dashboard and dispatches automations as subprocesses. |
| `index.html` | The dashboard UI. |
| `warm_account.py` | Per-device account warming (Reels scroll/like/save). Takes `--minutes` and `--device`. |
| `comment_on_post.py` | Per-device commenting. Takes `--url`, `--text` or `--smart`, and `--device`. |
| `smart_comment.py` | Reads caption from the on-device dump, asks Gemini for one short comment, falls back to generic. |
| `proxy-times.html` | Read-only table of proxy IPs → SSID, city, live local time. |
| `device-times.html` | Read-only table of phone-device → SSID → live local time. |
| `device_proxy_map.json` | Device ID → proxy slot mapping (source of truth for `device-times.html` / `device-times.csv`). |
| `selectors/` | Cached uiautomator dumps used to design selectors without poking the real phone. |
| `logs/` | Per-job log files written by app.py when an automation runs. |
| `screenshots/`, `uploads/` | Temporary working directories used at runtime. |
| `dashboard.bat` | Server lifecycle (start/stop/restart/status/urls). |
| `setup.bat` | One-time installer for Python deps + .env. |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `dashboard.bat : The term ... is not recognized` | You're in PowerShell — use `.\dashboard.bat`. |
| `Python is not on PATH` | Reinstall Python with **Add to PATH** ticked, or add it manually. |
| Server window flashes and closes | Check the new console for the Python error. Most common: a missing dep — re-run `.\setup.bat`. |
| Dashboard loads but device cards are empty | Laixi app isn't running, or it's not bound to `127.0.0.1:22221`. |
| Smart Comment always returns "nice one" / "love this" | No `GEMINI_API_KEY` in `.env`, or it's invalid → falls back to generic. |
| Port 8000 already in use | Another process owns it. `.\dashboard.bat stop` kills our server; if something else is on 8000, edit `PORT` near the top of `app.py`. |
