import asyncio
import json
import re
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
    return json.loads(inner).get(DEVICE, []) if isinstance(inner, str) else []

def center(b):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return [(x1 + x2) // 2, (y1 + y2) // 2]

async def main():
    async with websockets.connect("ws://127.0.0.1:22221/") as ws:
        await adb(ws, "uiautomator dump /sdcard/window_dump.xml")
        await asyncio.sleep(0.4)
        xml = "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))
        root = ET.fromstring(xml)
        print("Elements matching 'Share':")
        for n in root.iter("node"):
            a = n.attrib
            if a.get("text") == "Share" or a.get("content-desc") == "Share":
                cls = a.get("class", "").split(".")[-1]
                print(f"  text={a.get('text')!r} desc={a.get('content-desc')!r} "
                      f"clickable={a.get('clickable')} class={cls} "
                      f"bounds={a.get('bounds')} center={center(a.get('bounds'))}")

if __name__ == "__main__":
    asyncio.run(main())
