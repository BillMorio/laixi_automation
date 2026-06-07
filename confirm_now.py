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

def center(b):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b or "")
    if not m: return None
    x1,y1,x2,y2 = map(int, m.groups()); return [(x1+x2)//2,(y1+y2)//2]

def parse(xml):
    out=[]
    try: root=ET.fromstring(xml)
    except ET.ParseError: return out
    for n in root.iter("node"):
        a=n.attrib; t,d=a.get("text",""),a.get("content-desc","")
        if not(a.get("clickable")=="true" or t or d): continue
        out.append({"text":t,"resource_id":a.get("resource-id",""),"content_desc":d,
                    "clickable":a.get("clickable")=="true","center":center(a.get("bounds",""))})
    return out

async def uidump(ws):
    for _ in range(3):
        await adb(ws,"uiautomator dump /sdcard/window_dump.xml"); await asyncio.sleep(0.4)
        xml="\n".join(await adb(ws,"cat /sdcard/window_dump.xml"))
        if xml.strip(): return xml
    return ""

def read_count(els):
    for e in els:
        if POST_COUNT_RID in e["resource_id"]:
            m=re.search(r"(\d[\d,]*)",e["content_desc"])
            if m: return int(m.group(1).replace(",",""))
    for e in els:
        m=re.search(r"(\d[\d,]*)\s*posts",e["content_desc"],re.I)
        if m: return int(m.group(1).replace(",",""))
    return None

def find(els,label,exact=True):
    w=label.lower()
    ms=[e for e in els if ((e["text"].lower()==w or e["content_desc"].lower()==w) if exact else (w in e["text"].lower() or w in e["content_desc"].lower())) and e["center"]]
    if not ms: return None
    cl=[e for e in ms if e["clickable"]]
    return (cl[0] if cl else ms[0])["center"]

async def main():
    async with websockets.connect("ws://127.0.0.1:22221/") as ws:
        prof=find(parse(await uidump(ws)),"Profile",exact=True)
        if prof:
            print("tapping Profile @",prof); await adb(ws,f"input tap {prof[0]} {prof[1]}"); await asyncio.sleep(4)
        for r in range(5):
            els=parse(await uidump(ws)); c=read_count(els)
            print(f"  attempt {r+1}: post count = {c}")
            if c is not None: break
            await adb(ws,"input swipe 540 700 540 1650 450"); await asyncio.sleep(3)
        print("FINAL post count:", read_count(parse(await uidump(ws))))

if __name__=="__main__":
    asyncio.run(main())
