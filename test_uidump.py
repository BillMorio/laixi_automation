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
        print("dump:", await adb(ws, "uiautomator dump /sdcard/window_dump.xml"))
        lines = await adb(ws, "cat /sdcard/window_dump.xml")
        full = "\n".join(lines)
        print("response lines:", len(lines))
        print("total chars:", len(full))
        print("ends with </hierarchy>?:", full.rstrip().endswith("</hierarchy>"))
        # Does it expose tappable button text + bounds?
        for kw in ["text=", "bounds=", "Allow", "Continue", "Share", "Next", "OK"]:
            print(f"  contains {kw!r}:", kw in full)
        print("--- first 400 chars ---")
        print(full[:400])

if __name__ == "__main__":
    asyncio.run(main())
