"""
Discovery capture for IG account warming. Opens Reels, captures the viewer's
like/save/comment selectors, then taps Like and Save (re-dumping each time) to
record the state transitions warming needs, swipes to the next reel, and exits.
Saves to selectors/warm_flow.json + raw dumps. Likes/saves a couple reels
(permission granted) — that's required to observe the 'liked'/'saved' states.
"""
import asyncio
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL_WS = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
OUT_DIR = os.path.join(os.path.dirname(__file__), "selectors")
RAW_DIR = os.path.join(OUT_DIR, "raw")
os.makedirs(RAW_DIR, exist_ok=True)
flow_path = os.path.join(OUT_DIR, "warm_flow.json")
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


def find_by_rid(els, rid_substr):
    for e in els:
        if rid_substr in e["resource_id"] and e["center"]:
            return e["center"]
    return None


def find_center(els, label, exact=True):
    w = label.lower()
    ms = [e for e in els if ((e["text"].lower() == w or e["content_desc"].lower() == w)
          if exact else (w in e["text"].lower() or w in e["content_desc"].lower())) and e["center"]]
    if not ms:
        return None
    cl = [e for e in ms if e["clickable"]]
    return (cl[0] if cl else ms[0])["center"]


def desc_by_rid(els, rid_substr):
    for e in els:
        if rid_substr in e["resource_id"]:
            return e["content_desc"] or e["text"]
    return None


async def capture(ws, name):
    xml = await uidump(ws)
    open(os.path.join(RAW_DIR, f"{name}.xml"), "w", encoding="utf-8").write(xml)
    els = parse(xml)
    flow[name] = {"elements": els}
    json.dump(flow, open(flow_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n=== {name} === ({len(els)} elements)", flush=True)
    for rid in ["like_button", "save_button", "comment_button", "clips_viewer", "media_album_art"]:
        d = desc_by_rid(els, rid)
        c = find_by_rid(els, rid)
        if d is not None or c is not None:
            print(f"   [{rid}] desc={d!r} @ {c}", flush=True)
    return els


async def dismiss(ws):
    for _ in range(2):
        els = parse(await uidump(ws))
        for lbl in ["While using the app", "Continue", "OK", "Not now", "Allow access"]:
            c = find_center(els, lbl, exact=True)
            if c:
                print(f"   [dismiss] {lbl}", flush=True)
                await tap(ws, *c); await asyncio.sleep(1.2); break
        else:
            break


async def main():
    async with websockets.connect(URL_WS) as ws:
        # Cold start IG
        await adb(ws, "am force-stop com.instagram.android")
        await asyncio.sleep(1.5)
        await adb(ws, "monkey -p com.instagram.android -c android.intent.category.LAUNCHER 1")
        await asyncio.sleep(6)
        await dismiss(ws)

        # Go to Reels tab
        reels = find_center(parse(await uidump(ws)), "Reels", exact=True)
        if reels:
            print(f"   Reels tab @ {reels}", flush=True)
            await tap(ws, *reels); await asyncio.sleep(4)
        await dismiss(ws)

        # Wait for the reel's action buttons to render (they appear a beat after the
        # viewer opens — that's why the first dump came back empty last run)
        for _ in range(8):
            if find_by_rid(parse(await uidump(ws)), "like_button"):
                break
            await asyncio.sleep(1.5)

        # 1. Reels viewer
        els = await capture(ws, "w01_reels_viewer")
        like = find_by_rid(els, "like_button") or find_center(els, "Like", exact=True)
        save = find_by_rid(els, "save_button") or find_center(els, "Save", exact=True)
        print(f"\n   like @ {like}, save @ {save}", flush=True)

        # 2. Like -> capture state transition
        if like:
            print(f"   tapping Like (was: {desc_by_rid(els, 'like_button')!r})", flush=True)
            await tap(ws, *like); await asyncio.sleep(1.8)
            els2 = await capture(ws, "w02_after_like")
            print(f"   like_button now: {desc_by_rid(els2, 'like_button')!r}", flush=True)

        # 3. Save -> capture state transition
        els2 = parse(await uidump(ws))
        save = find_by_rid(els2, "save_button") or find_center(els2, "Save", exact=True)
        if save:
            print(f"   tapping Save (was: {desc_by_rid(els2, 'save_button')!r})", flush=True)
            await tap(ws, *save); await asyncio.sleep(1.8)
            els3 = await capture(ws, "w03_after_save")
            print(f"   save_button now: {desc_by_rid(els3, 'save_button')!r}", flush=True)

        # 4. Swipe to next reel, confirm selectors persist
        await adb(ws, "input swipe 540 1700 540 500 300")
        await asyncio.sleep(2.5)
        els4 = await capture(ws, "w04_next_reel")
        print(f"\n   next reel: like @ {find_by_rid(els4, 'like_button')}, "
              f"save @ {find_by_rid(els4, 'save_button')}", flush=True)

        # Exit pattern
        print("   exit: native Back x3 -> Home", flush=True)
        for _ in range(3):
            await adb(ws, "input keyevent 4"); await asyncio.sleep(1.2)
        await adb(ws, "input keyevent 3")
        print(f"\nSaved selector map: selectors/warm_flow.json ({len(flow)} screens)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
