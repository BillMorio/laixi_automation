import asyncio
import json
import websockets

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
SAVE = r"C:\Users\USER\Desktop\desktop\lumina-projects\laixi-custom-ui\screenshots"

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
        # Check screen state
        print("[state]", await adb(ws, "dumpsys power | grep 'Display Power'"))
        # Toggle power
        print("[pwr]", await adb(ws, "input keyevent 26"))
        await asyncio.sleep(1.2)
        # Swipe up from bottom to unlock
        print("[unlock]", await adb(ws, "input swipe 500 1800 500 600 200"))
        await asyncio.sleep(1)
        # Press home
        print("[home]", await adb(ws, "input keyevent 3"))
        await asyncio.sleep(1)
        print("[shot]", await shot(ws))

if __name__ == "__main__":
    asyncio.run(main())
