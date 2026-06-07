import asyncio
import json
import re
import sys
import xml.etree.ElementTree as ET
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEVICE = "77329d80ddbc"
POST_COUNT_RID = "profile_header_post_count_front_familiar"

async def adb(ws, cmd):
    await ws.send(json.dumps({"action": "adb", "comm": {"deviceIds": DEVICE, "command": cmd}}))
    r = await asyncio.wait_for(ws.recv(), timeout=15)
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

def parse(xml):
    out = []
    try: root = ET.fromstring(xml)
    except ET.ParseError: return out
    for n in root.iter("node"):
        a = n.attrib
        out.append({"text": a.get("text",""), "rid": a.get("resource-id",""), "desc": a.get("content-desc","")})
    return out

async def uidump(ws):
    for _ in range(3):
        await adb(ws, "uiautomator dump /sdcard/window_dump.xml"); await asyncio.sleep(0.4)
        xml = "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))
        if xml.strip(): return xml
    return ""

def read_count(els):
    for e in els:
        if POST_COUNT_RID in e["rid"]:
            m = re.search(r"(\d[\d,]*)", e["desc"]);  return int(m.group(1).replace(",","")) if m else None
    for e in els:
        m = re.search(r"(\d[\d,]*)\s*post", e["desc"], re.I)
        if m: return int(m.group(1).replace(",",""))
    return None

async def main():
    async with websockets.connect("ws://127.0.0.1:22221/") as ws:
        # Exit immersive reels -> Home feed, then Profile tab
        await adb(ws, "input keyevent 4"); await asyncio.sleep(1.5)   # Back
        await adb(ws, "input tap 108 2159"); await asyncio.sleep(2)   # Home tab
        await adb(ws, "input tap 972 2159"); await asyncio.sleep(4)   # Profile tab
        for r in range(4):
            els = parse(await uidump(ws))
            on_profile = any("profile_header" in e["rid"] for e in els)
            c = read_count(els)
            print(f"  attempt {r+1}: on_profile={on_profile} post_count={c}")
            if c is not None: break
            await adb(ws, "input swipe 540 700 540 1650 450"); await asyncio.sleep(3)
        print("RESULT post count:", read_count(parse(await uidump(ws))))

if __name__ == "__main__":
    asyncio.run(main())
