"""
Full IG post run that ACTUALLY publishes (permission granted), capturing the
post-Share screens: Facebook cross-post prompt (we tap "Not now"), any
"About Reels" confirm, and the "Sharing to Reels" success banner.

Also exercises the uiautomator video-thumbnail selector (newest by content-desc)
instead of a blind coordinate. Merges captures into selectors/ig_flow.json.
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

flow = {}
flow_path = os.path.join(OUT_DIR, "ig_flow.json")
if os.path.exists(flow_path):
    flow = json.load(open(flow_path, encoding="utf-8"))


async def adb(ws, cmd, timeout=20):
    await ws.send(json.dumps({"action": "adb", "comm": {"deviceIds": DEVICE, "command": cmd}}))
    r = await asyncio.wait_for(ws.recv(), timeout=timeout)
    inner = json.loads(r).get("result")
    if isinstance(inner, str):
        try:
            return json.loads(inner).get(DEVICE, [])
        except json.JSONDecodeError:
            return [inner]
    return inner or []


async def tap(ws, x, y):
    await adb(ws, f"input tap {x} {y}")


async def uidump(ws):
    await adb(ws, "uiautomator dump /sdcard/window_dump.xml")
    return "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))


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
    w = label.lower()
    for e in els:
        t, d = e["text"].lower(), e["content_desc"].lower()
        if ((t == w or d == w) if exact else (w in t or w in d)) and e["center"]:
            return e["center"]
    return None


def find_newest_video(els):
    """Pick the video thumbnail with the latest 'created on <date>' content-desc."""
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


async def capture(ws, name, els=None, xml=None):
    if xml is None:
        xml = await uidump(ws)
    open(os.path.join(RAW_DIR, f"{name}.xml"), "w", encoding="utf-8").write(xml)
    if els is None:
        els = parse_elements(xml)
    sig = sorted({(e["text"] or e["content_desc"]) for e in els
                  if e["clickable"] and (e["text"] or e["content_desc"])})
    flow[name] = {"signature": sig, "elements": els}
    print(f"\n=== {name} === ({len(els)} elements)")
    for s in sig[:25]:
        print("   •", s)
    return els


async def dismiss(ws):
    for _ in range(2):
        els = parse_elements(await uidump(ws))
        for lbl in ["While using the app", "Continue", "OK", "Done", "Allow access"]:
            c = find_center(els, lbl, exact=True)
            if c:
                print(f"   [dismiss] {lbl}")
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

        # Home -> + (the one true coordinate)
        await tap(ws, *PLUS_XY)
        await asyncio.sleep(3)
        await dismiss(ws)

        # Composer: select newest video BY SELECTOR (content-desc), unless already selected
        comp = parse_elements(await uidump(ws))
        if find_center(comp, "Selected Video thumbnail", exact=False):
            print("   newest video already auto-selected — not tapping")
        else:
            v = find_newest_video(comp)
            if v:
                print(f"   selecting newest video by content-desc: {v['content_desc']} @ {v['center']}")
                await tap(ws, *v["center"]); await asyncio.sleep(1.5)
        nxt = find_center(parse_elements(await uidump(ws)), "Next", exact=True)
        if nxt:
            await tap(ws, *nxt); print(f"   Next @ {nxt}")
        await asyncio.sleep(4)
        await dismiss(ws)

        # Editor -> Next
        nxt = find_center(parse_elements(await uidump(ws)), "Next", exact=True)
        if nxt:
            await tap(ws, *nxt); print(f"   Next @ {nxt}")
        await asyncio.sleep(3)
        await dismiss(ws)

        # Caption -> Share  (PUBLISHING — permission granted)
        share = find_center(parse_elements(await uidump(ws)), "Share", exact=True)
        if not share:
            print("   !! Share not found — aborting"); return
        print(f"   Share @ {share} — TAPPING (publishing)")
        await tap(ws, *share)

        # Post-share cascade: capture each new screen, handle FB ("Not now"), confirm Share
        seen = set()
        for i in range(9):
            await asyncio.sleep(2.5)
            xml = await uidump(ws)
            els = parse_elements(xml)
            low = xml.lower()
            if find_center(els, "Not now", exact=True):
                if "fb_crosspost" not in seen:
                    await capture(ws, "06_fb_crosspost", els, xml); seen.add("fb_crosspost")
                print("   [post-share] Facebook prompt -> Not now")
                await tap(ws, *find_center(els, "Not now", exact=True)); continue
            if find_center(els, "Share", exact=True):
                if "about_reels" not in seen:
                    await capture(ws, "06b_about_reels", els, xml); seen.add("about_reels")
                print("   [post-share] About Reels -> Share")
                await tap(ws, *find_center(els, "Share", exact=True)); continue
            if any(s in low for s in ["sharing to", "posting", "uploading"]):
                if "progress" not in seen:
                    await capture(ws, "07_sharing_progress", els, xml); seen.add("progress")
                print("   [post-share] upload in progress…"); continue
            # nothing actionable -> we're on the feed
            if "after_post" not in seen:
                await capture(ws, "08_after_post", els, xml); seen.add("after_post")
            print("   [post-share] no more prompts — done")
            break

        json.dump(flow, open(flow_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"\nSaved selector map: selectors/ig_flow.json ({len(flow)} screens)")


if __name__ == "__main__":
    asyncio.run(main())
