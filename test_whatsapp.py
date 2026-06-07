import asyncio
import json
import urllib.parse
import websockets

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
SAVE = r"C:\Users\USER\Desktop\desktop\lumina-projects\laixi-custom-ui\screenshots"

PHONE = "254740757762"
MESSAGE = "Test from Laixi dashboard"

async def adb(ws, cmd):
    await ws.send(json.dumps({
        "action": "adb",
        "comm": {"deviceIds": DEVICE, "command": cmd},
    }))
    return await asyncio.wait_for(ws.recv(), timeout=5)

async def shot(ws):
    await ws.send(json.dumps({
        "action": "screen",
        "comm": {"deviceIds": DEVICE, "savePath": SAVE},
    }))
    return await asyncio.wait_for(ws.recv(), timeout=10)

async def main():
    async with websockets.connect(URL) as ws:
        # Wake the screen
        print("[wake]", await adb(ws, "input keyevent 224"))
        await asyncio.sleep(0.5)
        # Unlock with menu key (no PIN scenario)
        print("[menu]", await adb(ws, "input keyevent 82"))
        await asyncio.sleep(0.5)

        # Fire wa.me URL via Chrome
        wa_url = f"https://wa.me/{PHONE}?text={urllib.parse.quote(MESSAGE)}"
        cmd = (
            f'am start -a android.intent.action.VIEW '
            f'-d "{wa_url}" '
            f'-n com.android.chrome/com.google.android.apps.chrome.Main'
        )
        print("[open]", await adb(ws, cmd))
        await asyncio.sleep(4)

        print("[shot]", await shot(ws))

if __name__ == "__main__":
    asyncio.run(main())
