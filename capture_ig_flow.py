"""
Walk the Instagram posting flow using uiautomator and SAVE every screen's
interactive elements (text / resource-id / content-desc / bounds) to a reusable
selector map. Stops BEFORE tapping Share so nothing is published.

Output:
  selectors/raw/<NN_name>.xml      raw uiautomator dump per screen
  selectors/ig_flow.json           parsed selector map keyed by screen
"""
import asyncio
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
RES_W, RES_H = 1080, 2400
OUT_DIR = os.path.join(os.path.dirname(__file__), "selectors")
RAW_DIR = os.path.join(OUT_DIR, "raw")
os.makedirs(RAW_DIR, exist_ok=True)

# Coordinate fallbacks for the icon buttons that have no text (calibrated earlier).
PLUS_XY = (55, 175)
THUMB2_XY = (405, 1656)

flow = {}  # screen_name -> {signature, elements}


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
    lines = await adb(ws, "cat /sdcard/window_dump.xml")
    return "\n".join(lines)


def center(bounds):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return [(x1 + x2) // 2, (y1 + y2) // 2]


def parse_elements(xml):
    """Return interactive/labeled elements with their selectors + tap center."""
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for n in root.iter("node"):
        a = n.attrib
        text = a.get("text", "")
        desc = a.get("content-desc", "")
        rid = a.get("resource-id", "")
        clickable = a.get("clickable") == "true"
        if not (clickable or text or desc):
            continue
        out.append({
            "text": text,
            "resource_id": rid,
            "content_desc": desc,
            "class": a.get("class", ""),
            "clickable": clickable,
            "bounds": a.get("bounds", ""),
            "center": center(a.get("bounds", "")),
        })
    return out


def find_center(elements, label, exact=True):
    want = label.lower()
    for e in elements:
        t, d = e["text"].lower(), e["content_desc"].lower()
        hit = (t == want or d == want) if exact else (want in t or want in d)
        if hit and e["center"]:
            return e["center"]
    return None


async def capture(ws, name):
    xml = await uidump(ws)
    with open(os.path.join(RAW_DIR, f"{name}.xml"), "w", encoding="utf-8") as f:
        f.write(xml)
    els = parse_elements(xml)
    # signature = the labeled, clickable buttons on this screen
    sig = sorted({(e["text"] or e["content_desc"]) for e in els
                  if e["clickable"] and (e["text"] or e["content_desc"])})
    flow[name] = {"signature": sig, "elements": els}
    print(f"\n=== {name} === ({len(els)} elements)")
    for s in sig[:25]:
        print("   •", s)
    return els


async def dismiss_notices(ws):
    safe = ["While using the app", "Continue", "OK", "Not now", "Done", "Allow access"]
    for _ in range(2):
        els = parse_elements(await uidump(ws))
        tapped = False
        for lbl in safe:
            c = find_center(els, lbl, exact=True)
            if c:
                print(f"   [dismiss] {lbl}")
                await tap(ws, *c)
                tapped = True
                await asyncio.sleep(1.2)
                break
        if not tapped:
            break


async def main():
    async with websockets.connect(URL) as ws:
        # Pre-grant perms so dialogs don't block capture
        for p in ["CAMERA", "RECORD_AUDIO", "READ_EXTERNAL_STORAGE",
                  "READ_MEDIA_VIDEO", "READ_MEDIA_IMAGES"]:
            await adb(ws, f"pm grant com.instagram.android android.permission.{p}")

        # Cold start
        await adb(ws, "am force-stop com.instagram.android")
        await asyncio.sleep(1.5)
        await adb(ws, "monkey -p com.instagram.android -c android.intent.category.LAUNCHER 1")
        await asyncio.sleep(6)
        await dismiss_notices(ws)

        # 1. HOME
        home = await capture(ws, "01_home")
        plus = find_center(home, "new post", exact=False) or find_center(home, "create", exact=False)
        await tap(ws, *(plus or PLUS_XY))
        print(f"   tapped + at {plus or PLUS_XY} {'(selector)' if plus else '(coord fallback)'}")
        await asyncio.sleep(3)
        await dismiss_notices(ws)

        # 2. COMPOSER (media grid)
        await capture(ws, "02_composer")
        await tap(ws, *THUMB2_XY)  # newest video (2nd cell; cell 1 = camera)
        print(f"   tapped thumbnail at {THUMB2_XY} (coord fallback)")
        await asyncio.sleep(2.5)
        await dismiss_notices(ws)

        # 3. After selecting media
        sel = await capture(ws, "03_media_selected")
        nxt = find_center(sel, "Next", exact=True)
        if nxt:
            await tap(ws, *nxt); print(f"   tapped Next at {nxt}")
        await asyncio.sleep(4)
        await dismiss_notices(ws)

        # 4. EDITOR
        ed = await capture(ws, "04_editor")
        nxt = find_center(ed, "Next", exact=True)
        if nxt:
            await tap(ws, *nxt); print(f"   tapped Next at {nxt}")
        await asyncio.sleep(3)
        await dismiss_notices(ws)

        # 5. CAPTION (has Share) — capture and STOP (do not publish)
        cap = await capture(ws, "05_caption")
        share = find_center(cap, "Share", exact=True)
        print(f"\n   Share button {'FOUND at ' + str(share) if share else 'NOT found'} — NOT tapping (safe stop)")

        # Back out so we don't leave a draft mid-air
        await adb(ws, "input keyevent 3")  # Home

        with open(os.path.join(OUT_DIR, "ig_flow.json"), "w", encoding="utf-8") as f:
            json.dump(flow, f, indent=2, ensure_ascii=False)
        print(f"\nSaved selector map: selectors/ig_flow.json ({len(flow)} screens)")


if __name__ == "__main__":
    asyncio.run(main())
