import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8000
ROOT = Path(__file__).parent
SCREENSHOT_DIR = ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = ROOT / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
ENV_PATH = ROOT / ".env"

# Triggerable automations -> argv builder from params. Args are passed as a list
# (no shell), so user inputs (url/text) can't inject shell commands.
PY = sys.executable
def _dev_args(p):
    """Forward --device to the worker only if the dashboard supplied one;
    omit otherwise so the script falls back to its module-level DEVICE constant."""
    d = p.get("device")
    return ["--device", str(d)] if d else []

ACTIONS = {
    "warm": lambda p: [PY, "-u", str(ROOT / "warm_account.py"),
                       "--minutes", str(p.get("minutes", 5)),
                       *_dev_args(p)],
    "comment": lambda p: [PY, "-u", str(ROOT / "comment_on_post.py"),
                          "--url", str(p.get("url", "")),
                          *(["--smart"] if p.get("smart")
                            else ["--text", str(p.get("text", ""))]),
                          *_dev_args(p)],
}
JOBS = {}  # job_id -> {proc, log (Path), logf, action}


def _ffprobe(path, entries):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", entries, "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def ffprobe_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _parse_env(path):
    """Read .env into an ordered list of entries (kv / comment / blank). Used to
    round-trip comment lines through the Settings editor so user notes survive a
    Save."""
    if not path.exists():
        return []
    entries = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip()
        if not s:
            entries.append({"type": "blank"})
        elif s.startswith("#") or "=" not in raw:
            entries.append({"type": "comment", "text": raw})
        else:
            k, _, v = raw.partition("=")
            entries.append({"type": "kv", "key": k.strip(), "value": v.strip()})
    return entries


def _kv_only(entries):
    return [{"key": e["key"], "value": e["value"]} for e in entries if e["type"] == "kv"]


def _rewrite_env(path, incoming_kv):
    """Atomically rewrite .env. Existing keys keep their position relative to
    surrounding comments; new keys append at the bottom; missing keys are dropped."""
    original = _parse_env(path)
    incoming_map = {e["key"]: e.get("value", "") for e in incoming_kv if e.get("key")}
    used, out_lines = set(), []
    for e in original:
        if e["type"] == "kv":
            if e["key"] in incoming_map:
                out_lines.append(f"{e['key']}={incoming_map[e['key']]}")
                used.add(e["key"])
            # else: row deleted in the UI -> drop it
        elif e["type"] == "comment":
            out_lines.append(e["text"])
        else:
            out_lines.append("")
    for e in incoming_kv:
        k = (e.get("key") or "").strip()
        if not k or k in used:
            continue
        out_lines.append(f"{k}={e.get('value', '')}")
        used.add(k)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def normalize_video(raw, out):
    """Make a video safe for Android/Instagram: rewrite the MP4 header so the
    duration field is correct (the #1 cause of 0:00 / rejected uploads), ensure
    faststart and AAC audio. H.264 video is copied losslessly (fast); other
    codecs are re-encoded to H.264."""
    codec = _ffprobe(raw, "stream=codec_name")
    if codec == "h264":
        cmd = ["ffmpeg", "-y", "-i", raw, "-c:v", "copy", "-c:a", "aac",
               "-b:a", "128k", "-movflags", "+faststart", out]
        mode = "remux"
    else:
        cmd = ["ffmpeg", "-y", "-i", raw, "-c:v", "libx264", "-profile:v", "high",
               "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k",
               "-movflags", "+faststart", out]
        mode = "reencode"
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(out):
        shutil.copy(raw, out)  # fallback: ship the original rather than nothing
        mode = "copy-fallback"
    return mode


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        m = re.match(r"^/latest/([a-zA-Z0-9_-]+)", self.path.split("?")[0])
        if m:
            device_id = m.group(1)
            matches = sorted(
                SCREENSHOT_DIR.glob(f"{device_id}*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not matches:
                self.send_error(404, "No screenshot yet")
                return
            # Cleanup: keep the 2 newest frames per device (room for pipeline)
            for old in matches[2:]:
                try: old.unlink()
                except OSError: pass
            data = matches[0].read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/settings/env":
            self._send_json({"ok": True, "entries": _kv_only(_parse_env(ENV_PATH))})
            return
        if self.path.startswith("/runlog"):
            job = JOBS.get(parse_qs(urlparse(self.path).query).get("job", [""])[0])
            if not job:
                self._send_json({"ok": False, "error": "unknown job"})
                return
            running = job["proc"].poll() is None
            try:
                log = job["log"].read_text(encoding="utf-8", errors="replace")
            except OSError:
                log = ""
            if not running:
                try: job["logf"].close()
                except Exception: pass
            self._send_json({"ok": True, "running": running, "log": log, "action": job["action"]})
            return
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/upload"):
            qs = parse_qs(urlparse(self.path).query)
            name = os.path.basename(qs.get("name", ["upload.bin"])[0])
            raw = UPLOADS_DIR / ("_raw_" + name)
            dest = UPLOADS_DIR / name
            length = int(self.headers.get("Content-Length", 0))
            remaining = length
            with open(raw, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            # Normalize so the file's duration header is valid (fixes 0:00 / IG reject)
            mode = normalize_video(str(raw), str(dest))
            try:
                raw.unlink()
            except OSError:
                pass
            size = dest.stat().st_size if dest.exists() else 0
            duration = round(ffprobe_duration(str(dest)), 1)
            body = json.dumps({
                "ok": True, "path": str(dest), "size": size,
                "duration": duration, "mode": mode,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/settings/env":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "invalid JSON"}); return
            incoming = body.get("entries", [])
            if not isinstance(incoming, list):
                self._send_json({"ok": False, "error": "entries must be a list"}); return
            for e in incoming:
                if not isinstance(e, dict) or not isinstance(e.get("key"), str):
                    self._send_json({"ok": False, "error": "each entry needs a 'key' string"}); return
            _rewrite_env(ENV_PATH, incoming)
            self._send_json({"ok": True, "saved": len(incoming)})
            return
        if self.path.startswith("/run/"):
            action = urlparse(self.path).path.split("/run/")[1].strip("/")
            if action not in ACTIONS:
                self.send_error(404, "unknown action")
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                params = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                params = {}
            job_id = uuid.uuid4().hex[:8]
            logpath = LOGS_DIR / f"{action}_{job_id}.log"
            logf = open(logpath, "w", encoding="utf-8")
            proc = subprocess.Popen(ACTIONS[action](params), stdout=logf,
                                    stderr=subprocess.STDOUT, cwd=str(ROOT))
            JOBS[job_id] = {"proc": proc, "log": logpath, "logf": logf, "action": action}
            self._send_json({"ok": True, "job_id": job_id, "action": action})
            return
        self.send_error(404)

    def _send_json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # quiet


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.allow_reuse_address = True
        print(f"Dashboard:   http://127.0.0.1:{PORT}/index.html")
        print(f"Screenshots: {SCREENSHOT_DIR}")
        print("Ctrl+C to stop.")
        httpd.serve_forever()
