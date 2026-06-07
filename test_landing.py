import asyncio
import json
import sys
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
PROBE = r"C:\Users\USER\Desktop\desktop\lumina-projects\laixi-custom-ui\uploads\laixi_landing_probe.mp4"

async def adb(ws, cmd, timeout=30):
    await ws.send(json.dumps({
        "action": "adb",
        "comm": {"deviceIds": DEVICE, "command": cmd},
    }))
    r = await asyncio.wait_for(ws.recv(), timeout=timeout)
    print(f"\n$ {cmd}\n{r}")

async def main():
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({
            "action": "beginfilesend",
            "comm": {"deviceIds": DEVICE, "filePaths": PROBE, "isAutoInstall": "0"},
        }))
        # Drain any follow-up / progress messages for ~15s
        print("--- messages after beginfilesend ---")
        end = asyncio.get_event_loop().time() + 15
        while asyncio.get_event_loop().time() < end:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                print("  msg:", msg)
            except asyncio.TimeoutError:
                pass

        # Search everywhere
        await adb(ws, "find /sdcard -name laixi_landing_probe.mp4")
        await adb(ws, "find /storage/emulated/0 -name laixi_landing_probe.mp4")
        await adb(ws, "ls /sdcard/Android/data/")
        await adb(ws, "find /sdcard/Android -name laixi_landing_probe.mp4")

if __name__ == "__main__":
    asyncio.run(main())
