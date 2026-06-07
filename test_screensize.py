import asyncio
import json
import websockets

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"

async def main():
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({
            "action": "adb",
            "comm": {"deviceIds": DEVICE, "command": "wm size; wm density"},
        }))
        print(await asyncio.wait_for(ws.recv(), timeout=5))

if __name__ == "__main__":
    asyncio.run(main())
