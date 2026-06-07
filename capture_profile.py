import asyncio
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEVICE = "77329d80ddbc"
OUT_DIR = os.path.join(os.path.dirname(__file__), "selectors")
RAW_DIR = os.path.join(OUT_DIR, "raw")
flow_path = os.path.join(OUT_DIR, "ig_flow.json")
flow = json.load(open(flow_path, encoding="utf-8")) if os.path.exists(flow_path) else {}

async def adb(ws, cmd):
    await ws.send(json.dumps({"action": "adb", "comm": {"deviceIds": DEVICE, "command": cmd}}))
    r = await asyncio.wait_for(ws.recv(), timeout=15)
    try:
        inner = json.loads(r).get("result")
    except json.JSONDecodeError:
        return []
    return json.loads(inner).get(DEVICE, []) if isinstance(inner, str) and inner else []

def center(b):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b or "")
    if not m: return None
    x1, y1, x2, y2 = map(int, m.groups())
    return [(x1 + x2) // 2, (y1 + y2) // 2]

def parse(xml):
    out = []
    for n in ET.fromstring(xml).iter("node"):
        a = n.attrib
        t, d = a.get("text", ""), a.get("content-desc", "")
        if not (a.get("clickable") == "true" or t or d): continue
        out.append({"text": t, "resource_id": a.get("resource-id", ""), "content_desc": d,
                    "class": a.get("class", ""), "clickable": a.get("clickable") == "true",
                    "bounds": a.get("bounds", ""), "center": center(a.get("bounds", ""))})
    return out

async def main():
    async with websockets.connect("ws://127.0.0.1:22221/") as ws:
        for _ in range(3):
            await adb(ws, "uiautomator dump /sdcard/window_dump.xml")
            await asyncio.sleep(0.4)
            xml = "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))
            if xml.strip(): break
        open(os.path.join(RAW_DIR, "09_profile.xml"), "w", encoding="utf-8").write(xml)
        els = parse(xml)
        sig = sorted({(e["text"] or e["content_desc"]) for e in els if e["clickable"] and (e["text"] or e["content_desc"])})
        flow["09_profile"] = {"signature": sig, "elements": els}
        json.dump(flow, open(flow_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print("Saved clean 09_profile.\n")
        print("Count / header elements (the confirmation signals):")
        for e in els:
            blob = (e["text"] + " " + e["content_desc"]).lower()
            if any(k in blob for k in ["post", "follower", "following"]) or re.search(r"resource-id$|tab", e["resource_id"]):
                rid = e["resource_id"].split("/")[-1]
                print(f"  text={e['text']!r} desc={e['content_desc']!r} rid={rid} center={e['center']}")

if __name__ == "__main__":
    asyncio.run(main())
