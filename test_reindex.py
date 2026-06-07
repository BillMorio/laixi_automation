import asyncio
import json
import sys
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
CAM = "/storage/emulated/0/DCIM/Camera"
SRC = f"{CAM}/laixi_1779955540266.mp4"
TMP = f"{CAM}/laixi_reindex.tmp"
NEW = f"{CAM}/laixi_reindex_test.mp4"

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
        print("exists SRC:", await adb(ws, f"ls -l {SRC}"))
        # Rename through a temp so the .mp4 appears fresh and complete
        print("mv->tmp:", await adb(ws, f"mv {SRC} {TMP}"))
        print("mv->new:", await adb(ws, f"mv {TMP} {NEW}"))
        print("scan:", await adb(ws, f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{NEW}"))
        await asyncio.sleep(4)
        # Read back what MediaStore now records (try single-quote where clause)
        print("query single-quote:",
              await adb(ws, "content query --uri content://media/external/video/media --projection _display_name:duration --where _display_name='laixi_reindex_test.mp4'"))

if __name__ == "__main__":
    asyncio.run(main())
