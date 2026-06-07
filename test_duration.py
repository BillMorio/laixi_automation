import asyncio
import json
import sys
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"

async def adb(ws, cmd, timeout=30):
    await ws.send(json.dumps({"action": "adb", "comm": {"deviceIds": DEVICE, "command": cmd}}))
    r = await asyncio.wait_for(ws.recv(), timeout=timeout)
    inner = json.loads(r).get("result")
    if isinstance(inner, str):
        try:
            return json.loads(inner).get(DEVICE, [])
        except json.JSONDecodeError:
            return [inner]
    return inner or []

async def main():
    async with websockets.connect(URL) as ws:
        rows = await adb(ws, "content query --uri content://media/external/video/media --projection _display_name:duration:_size")
        all_lines = []
        for r in rows:
            all_lines.extend(r.splitlines() if "\n" in r else [r])
        print("Total MediaStore video rows-ish:", len(all_lines))
        hits = [l for l in all_lines if "laixi" in l.lower()]
        print("laixi entries in MediaStore:")
        for h in hits:
            print("  ", h)
        if not hits:
            print("  (none found — file is NOT indexed in MediaStore as a video)")

if __name__ == "__main__":
    asyncio.run(main())
