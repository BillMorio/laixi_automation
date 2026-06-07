"""
Determine how to reliably LIKE a reel (and detect a liked state) for warming.
Compares: tapping like_button vs. double-tapping the reel. Reads the like
button's `selected` attribute and the like count before/after each.
"""
import asyncio
import json
import re
import sys
import xml.etree.ElementTree as ET
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEVICE = "77329d80ddbc"

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

async def uidump(ws):
    for _ in range(4):
        await adb(ws, "uiautomator dump /sdcard/window_dump.xml"); await asyncio.sleep(0.3)
        xml = "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))
        if xml.strip():
            return xml
        await asyncio.sleep(0.6)
    return ""

def root_of(xml):
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        return None

def like_state(xml):
    """Return (selected, count) for the reels like button."""
    root = root_of(xml)
    sel, cnt = None, None
    if root is None:
        return sel, cnt
    for n in root.iter("node"):
        a = n.attrib
        if "like_button" in a.get("resource-id", ""):
            sel = a.get("selected")
        d = a.get("content-desc", "")
        m = re.search(r"like number is (\d[\d,]*)", d, re.I)
        if m:
            cnt = m.group(1)
    return sel, cnt

def like_center(xml):
    root = root_of(xml)
    if root is None:
        return None
    for n in root.iter("node"):
        if "like_button" in n.attrib.get("resource-id", ""):
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.attrib.get("bounds", ""))
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                return [(x1 + x2) // 2, (y1 + y2) // 2]
    return None

async def wait_reel(ws):
    for _ in range(8):
        xml = await uidump(ws)
        if like_center(xml):
            return xml
        await asyncio.sleep(1.5)
    return await uidump(ws)

async def main():
    async with websockets.connect("ws://127.0.0.1:22221/") as ws:
        await adb(ws, "am force-stop com.instagram.android"); await asyncio.sleep(1.5)
        await adb(ws, "monkey -p com.instagram.android -c android.intent.category.LAUNCHER 1")
        await asyncio.sleep(6)
        # Reels tab (content-desc Reels ~ [324,2159])
        await tap(ws, 324, 2159); await asyncio.sleep(4)

        xml = await wait_reel(ws)
        lc = like_center(xml)
        print("reel ready. like_button @", lc)
        print("BEFORE:            selected=%s count=%s" % like_state(xml))

        # Method 1: tap the like button
        if lc:
            await tap(ws, *lc); await asyncio.sleep(1.8)
        print("after TAP like_btn: selected=%s count=%s" % like_state(await uidump(ws)))

        # Move to a fresh (unliked) reel to test double-tap cleanly
        await adb(ws, "input swipe 540 1700 540 500 300"); await asyncio.sleep(3)
        xml = await wait_reel(ws)
        print("\nnext reel BEFORE:  selected=%s count=%s" % like_state(xml))
        # Method 2: double-tap the reel center
        await tap(ws, 540, 1050); await asyncio.sleep(0.12); await tap(ws, 540, 1050)
        await asyncio.sleep(1.8)
        print("after DOUBLE-TAP:   selected=%s count=%s" % like_state(await uidump(ws)))

        # Exit
        for _ in range(3):
            await adb(ws, "input keyevent 4"); await asyncio.sleep(1.2)
        await adb(ws, "input keyevent 3")

if __name__ == "__main__":
    asyncio.run(main())
