import asyncio
import json
import sys
import xml.etree.ElementTree as ET
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEVICE = "77329d80ddbc"

async def adb(ws, cmd):
    await ws.send(json.dumps({"action": "adb", "comm": {"deviceIds": DEVICE, "command": cmd}}))
    r = await asyncio.wait_for(ws.recv(), timeout=15)
    try:
        inner = json.loads(r).get("result")
    except json.JSONDecodeError:
        return []
    if isinstance(inner, str):
        try:
            return json.loads(inner).get(DEVICE, [])
        except json.JSONDecodeError:
            return [inner]
    return []

async def main():
    async with websockets.connect("ws://127.0.0.1:22221/") as ws:
        await adb(ws, "uiautomator dump /sdcard/window_dump.xml")
        await asyncio.sleep(0.5)
        xml = "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))
        if not xml.strip():
            print("empty dump"); return
        root = ET.fromstring(xml)
        labels = sorted({(n.attrib.get("text") or n.attrib.get("content-desc"))
                         for n in root.iter("node")
                         if n.attrib.get("clickable") == "true" and (n.attrib.get("text") or n.attrib.get("content-desc"))})
        print("CURRENT SCREEN clickable labels:")
        for l in labels[:30]:
            print("  -", l)
        low = xml.lower()
        for marker in ["not now", "sharing to", "share your reels", "about reels", "your reel"]:
            if marker in low:
                print("  >> MARKER:", marker)

if __name__ == "__main__":
    asyncio.run(main())
