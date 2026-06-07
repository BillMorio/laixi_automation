"""
Full IG post run (publishes — permission granted) that captures EVERY screen's
uiautomator selectors: pre-share, post-share cascade, AND the profile screen
(+ pull-to-refresh) for post-confirmation.

Fixes vs prior runs:
  - find_center prefers the CLICKABLE element (avoids tapping a dead label)
  - verifies the Share tap actually advanced (retries once)
  - runs to completion (no artificial timeout); python -u for live output
Merges into selectors/ig_flow.json.
"""
import asyncio
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
OUT_DIR = os.path.join(os.path.dirname(__file__), "selectors")
RAW_DIR = os.path.join(OUT_DIR, "raw")
os.makedirs(RAW_DIR, exist_ok=True)
PLUS_XY = (66, 167)

flow_path = os.path.join(OUT_DIR, "ig_flow.json")
flow = json.load(open(flow_path, encoding="utf-8")) if os.path.exists(flow_path) else {}


async def adb(ws, cmd, timeout=20):
    await ws.send(json.dumps({"action": "adb", "comm": {"deviceIds": DEVICE, "command": cmd}}))
    r = await asyncio.wait_for(ws.recv(), timeout=timeout)
    try:
        inner = json.loads(r).get("result")
    except json.JSONDecodeError:
        return []
    if isinstance(inner, str) and inner:
        try:
            return json.loads(inner).get(DEVICE, [])
        except json.JSONDecodeError:
            return [inner]
    return []


async def tap(ws, x, y):
    await adb(ws, f"input tap {x} {y}")


async def uidump(ws, retries=3):
    for _ in range(retries):
        await adb(ws, "uiautomator dump /sdcard/window_dump.xml")
        await asyncio.sleep(0.3)
        xml = "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))
        if xml.strip():
            return xml
        await asyncio.sleep(0.6)
    return ""


def center(b):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return [(x1 + x2) // 2, (y1 + y2) // 2]


def parse_elements(xml):
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for n in root.iter("node"):
        a = n.attrib
        text, desc = a.get("text", ""), a.get("content-desc", "")
        if not (a.get("clickable") == "true" or text or desc):
            continue
        out.append({"text": text, "resource_id": a.get("resource-id", ""),
                    "content_desc": desc, "class": a.get("class", ""),
                    "clickable": a.get("clickable") == "true",
                    "bounds": a.get("bounds", ""), "center": center(a.get("bounds", ""))})
    return out


def find_center(els, label, exact=True):
    """Prefer a clickable match so we never tap a dead label."""
    w = label.lower()
    matches = []
    for e in els:
        t, d = e["text"].lower(), e["content_desc"].lower()
        if ((t == w or d == w) if exact else (w in t or w in d)) and e["center"]:
            matches.append(e)
    if not matches:
        return None
    clickable = [e for e in matches if e["clickable"]]
    return (clickable[0] if clickable else matches[0])["center"]


def find_newest_video(els):
    best, best_dt = None, None
    for e in els:
        m = re.search(r"Video thumbnail created on (.+)$", e["content_desc"])
        if not m or not e["center"]:
            continue
        try:
            dt = datetime.strptime(m.group(1).strip(), "%d %B %Y %H:%M")
        except ValueError:
            continue
        if best_dt is None or dt > best_dt:
            best, best_dt = e, dt
    return best


async def capture(ws, name, xml=None):
    if xml is None:
        xml = await uidump(ws)
    open(os.path.join(RAW_DIR, f"{name}.xml"), "w", encoding="utf-8").write(xml)
    els = parse_elements(xml)
    sig = sorted({(e["text"] or e["content_desc"]) for e in els
                  if e["clickable"] and (e["text"] or e["content_desc"])})
    flow[name] = {"signature": sig, "elements": els}
    json.dump(flow, open(flow_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"=== {name} === ({len(els)} elements)", flush=True)
    for s in sig[:22]:
        print("   -", s, flush=True)
    return els, xml


async def dismiss(ws):
    for _ in range(2):
        els = parse_elements(await uidump(ws))
        for lbl in ["While using the app", "Continue", "OK", "Done", "Allow access"]:
            c = find_center(els, lbl, exact=True)
            if c:
                print(f"   [dismiss] {lbl}", flush=True)
                await tap(ws, *c); await asyncio.sleep(1.2); break
        else:
            break


async def main():
    async with websockets.connect(URL) as ws:
        for p in ["CAMERA", "RECORD_AUDIO", "READ_MEDIA_VIDEO", "READ_MEDIA_IMAGES"]:
            await adb(ws, f"pm grant com.instagram.android android.permission.{p}")
        await adb(ws, "am force-stop com.instagram.android")
        await asyncio.sleep(1.5)
        await adb(ws, "monkey -p com.instagram.android -c android.intent.category.LAUNCHER 1")
        await asyncio.sleep(6)
        await dismiss(ws)

        await tap(ws, *PLUS_XY)        # + (the one coordinate)
        await asyncio.sleep(3)
        await dismiss(ws)

        # Composer — select newest video by content-desc unless already selected
        comp = parse_elements(await uidump(ws))
        if not find_center(comp, "Selected Video thumbnail", exact=False):
            v = find_newest_video(comp)
            if v:
                print(f"   select video: {v['content_desc']} @ {v['center']}", flush=True)
                await tap(ws, *v["center"]); await asyncio.sleep(1.5)
        c = find_center(parse_elements(await uidump(ws)), "Next")
        if c: await tap(ws, *c); print(f"   Next @ {c}", flush=True)
        await asyncio.sleep(4); await dismiss(ws)

        # Editor — Next
        c = find_center(parse_elements(await uidump(ws)), "Next")
        if c: await tap(ws, *c); print(f"   Next @ {c}", flush=True)
        await asyncio.sleep(3); await dismiss(ws)

        # Caption — Share, verified
        for attempt in range(2):
            xml = await uidump(ws)
            c = find_center(parse_elements(xml), "Share")
            if not c:
                break
            print(f"   Share @ {c} (attempt {attempt+1}) — PUBLISHING", flush=True)
            await tap(ws, *c)
            await asyncio.sleep(3)
            if "write a caption" not in (await uidump(ws)).lower():
                print("   advanced past caption", flush=True); break
            print("   still on caption — retrying Share", flush=True)

        # Post-share cascade
        for i in range(10):
            await asyncio.sleep(2.5)
            xml = await uidump(ws)
            els = parse_elements(xml); low = xml.lower()
            if find_center(els, "Not now", exact=True):
                if "06_fb_crosspost" not in flow: await capture(ws, "06_fb_crosspost", xml)
                print("   [post] FB prompt -> Not now", flush=True)
                await tap(ws, *find_center(els, "Not now", exact=True)); continue
            if find_center(els, "Share", exact=True):
                if "06b_about_reels" not in flow: await capture(ws, "06b_about_reels", xml)
                print("   [post] About Reels -> Share", flush=True)
                await tap(ws, *find_center(els, "Share", exact=True)); continue
            if any(s in low for s in ["sharing to", "posting", "uploading"]):
                if "07_sharing_progress" not in flow: await capture(ws, "07_sharing_progress", xml)
                print("   [post] uploading...", flush=True); continue
            if "08_after_post" not in flow: await capture(ws, "08_after_post", xml)
            print("   [post] cascade done", flush=True); break

        # Profile — go confirm
        await asyncio.sleep(2)
        prof = find_center(parse_elements(await uidump(ws)), "Profile", exact=True)
        if prof:
            print(f"   Profile tab @ {prof}", flush=True)
            await tap(ws, *prof); await asyncio.sleep(4)
            await capture(ws, "09_profile")
            # pull-to-refresh
            await adb(ws, "input swipe 540 700 540 1750 400")
            await asyncio.sleep(4)
            await capture(ws, "10_profile_refreshed")
        else:
            print("   Profile tab not found on current screen", flush=True)

        print(f"\nSaved selector map: selectors/ig_flow.json ({len(flow)} screens)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
