"""
Full IG post run with profile-based confirmation.
Reads baseline post count -> posts -> goes to profile -> refreshes -> confirms
the count incremented. Taps Share ONCE (max 2 retries); trusts the post-count
delta, not caption re-detection. python -u, runs to completion.
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
DEVICE = "77329d80ddbc"
PLUS_XY = (66, 167)
POST_COUNT_RID = "profile_header_post_count_front_familiar"


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


def parse(xml):
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for n in root.iter("node"):
        a = n.attrib
        t, d = a.get("text", ""), a.get("content-desc", "")
        if not (a.get("clickable") == "true" or t or d):
            continue
        out.append({"text": t, "resource_id": a.get("resource-id", ""), "content_desc": d,
                    "clickable": a.get("clickable") == "true", "bounds": a.get("bounds", ""),
                    "center": center(a.get("bounds", ""))})
    return out


def find_center(els, label, exact=True):
    w = label.lower()
    matches = [e for e in els if ((e["text"].lower() == w or e["content_desc"].lower() == w)
               if exact else (w in e["text"].lower() or w in e["content_desc"].lower())) and e["center"]]
    if not matches:
        return None
    cl = [e for e in matches if e["clickable"]]
    return (cl[0] if cl else matches[0])["center"]


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


def read_post_count(els):
    for e in els:
        if POST_COUNT_RID in e["resource_id"]:
            m = re.search(r"(\d[\d,]*)", e["content_desc"])
            if m:
                return int(m.group(1).replace(",", ""))
    for e in els:
        m = re.search(r"(\d[\d,]*)\s*posts", e["content_desc"], re.I)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


async def dismiss(ws):
    for _ in range(2):
        els = parse(await uidump(ws))
        for lbl in ["While using the app", "Continue", "OK", "Done", "Allow access"]:
            c = find_center(els, lbl, exact=True)
            if c:
                print(f"   [dismiss] {lbl}", flush=True)
                await tap(ws, *c); await asyncio.sleep(1.2); break
        else:
            break


async def goto_profile(ws):
    c = find_center(parse(await uidump(ws)), "Profile", exact=True)
    if c:
        await tap(ws, *c); await asyncio.sleep(4)
        return True
    return False


async def goto_profile_clean(ws):
    """From anywhere (incl. the immersive reels feed, which swallows a direct
    Profile tap): Back to exit, then element-tap Home -> Profile."""
    await adb(ws, "input keyevent 4")   # Back: exit reels player / dismiss sheet
    await asyncio.sleep(1.5)
    h = find_center(parse(await uidump(ws)), "Home", exact=True)
    if h:
        await tap(ws, *h); await asyncio.sleep(2)
    p = find_center(parse(await uidump(ws)), "Profile", exact=True)
    if p:
        await tap(ws, *p); await asyncio.sleep(4); return True
    return False


async def read_count_robust(ws, tries=5):
    """Wait until we're actually on the profile (header present) before reading."""
    for _ in range(tries):
        els = parse(await uidump(ws))
        if any("profile_header" in e["resource_id"] for e in els):
            c = read_post_count(els)
            if c is not None:
                return c
        await asyncio.sleep(2)
    return None


async def main():
    async with websockets.connect(URL) as ws:
        for p in ["CAMERA", "RECORD_AUDIO", "READ_MEDIA_VIDEO", "READ_MEDIA_IMAGES"]:
            await adb(ws, f"pm grant com.instagram.android android.permission.{p}")
        await adb(ws, "am force-stop com.instagram.android")
        await asyncio.sleep(1.5)
        await adb(ws, "monkey -p com.instagram.android -c android.intent.category.LAUNCHER 1")
        await asyncio.sleep(6)
        await dismiss(ws)

        # Baseline post count
        await goto_profile(ws)
        baseline = await read_count_robust(ws)
        print(f"BASELINE post count = {baseline}", flush=True)

        # Back to home feed, then +
        home = find_center(parse(await uidump(ws)), "Home", exact=True)
        if home:
            await tap(ws, *home); await asyncio.sleep(2)
        await tap(ws, *PLUS_XY); await asyncio.sleep(3); await dismiss(ws)

        # Composer: pick newest video unless auto-selected, Next
        comp = parse(await uidump(ws))
        if not find_center(comp, "Selected Video thumbnail", exact=False):
            v = find_newest_video(comp)
            if v:
                print(f"   select video @ {v['center']}", flush=True)
                await tap(ws, *v["center"]); await asyncio.sleep(1.5)
        c = find_center(parse(await uidump(ws)), "Next")
        if c: await tap(ws, *c); print(f"   Next @ {c}", flush=True)
        await asyncio.sleep(4); await dismiss(ws)

        # Editor: Next
        c = find_center(parse(await uidump(ws)), "Next")
        if c: await tap(ws, *c); print(f"   Next @ {c}", flush=True)
        await asyncio.sleep(3); await dismiss(ws)

        # Caption: Share once
        c = find_center(parse(await uidump(ws)), "Share")
        if c:
            print(f"   Share @ {c} — PUBLISHING", flush=True)
            await tap(ws, *c)

        # The Share tap above publishes — that's it. Do NOT touch any post-share
        # screens. Just wait for it to submit, then go to the profile and refresh
        # while the upload completes.
        await asyncio.sleep(4)

        # Confirm: exit reels -> profile, then poll the post count (refresh while uploading)
        await asyncio.sleep(3)
        await goto_profile_clean(ws)
        final = None
        for r in range(8):
            final = await read_count_robust(ws, tries=2)
            print(f"   profile post count = {final} (baseline {baseline})", flush=True)
            if final is not None and (baseline is None or final > baseline):
                break
            await adb(ws, "input swipe 540 700 540 1650 450")  # pull to refresh
            await asyncio.sleep(5)

        print("\n==============================", flush=True)
        if final is not None and (baseline is None or final > baseline):
            print(f"RESULT: POSTED ✓  (post count {baseline} -> {final})", flush=True)
        else:
            print(f"RESULT: UNCONFIRMED  (baseline={baseline}, final={final})", flush=True)
        print("==============================", flush=True)


URL = "ws://127.0.0.1:22221/"
if __name__ == "__main__":
    asyncio.run(main())
