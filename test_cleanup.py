import asyncio
import json
import sys
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
CAM = "/storage/emulated/0/DCIM/Camera"

async def adb(ws, cmd):
    await ws.send(json.dumps({
        "action": "adb",
        "comm": {"deviceIds": DEVICE, "command": cmd},
    }))
    r = await asyncio.wait_for(ws.recv(), timeout=20)
    inner = json.loads(r).get("result")
    if isinstance(inner, str):
        try:
            return json.loads(inner).get(DEVICE, [])
        except json.JSONDecodeError:
            return [inner]
    return []

async def main():
    async with websockets.connect(URL) as ws:
        print("=== Newest 15 in DCIM/Camera ===")
        for line in (await adb(ws, f"ls -lt {CAM}"))[:16]:
            print(" ", line)
        print("\n=== laixi_ anywhere in /storage/emulated/0 ===")
        for line in await adb(ws, "find /storage/emulated/0 -name laixi_landing_probe.mp4 -o -name laixi_1779953214215.mp4 -o -name laixi_1779953777326.mp4"):
            print(" ", line)

if __name__ == "__main__":
    asyncio.run(main())
