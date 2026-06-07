import asyncio
import json
import websockets

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
SAVE = r"C:\Users\USER\Desktop\desktop\lumina-projects\laixi-custom-ui"

async def main():
    print(f"Connecting to {URL} ...")
    async with websockets.connect(URL) as ws:
        print("[open] connected")
        payload = {
            "action": "screen",
            "comm": {"deviceIds": DEVICE, "savePath": SAVE},
        }
        await ws.send(json.dumps(payload))
        print(f"[sent] screenshot {DEVICE} -> {SAVE}")
        reply = await asyncio.wait_for(ws.recv(), timeout=15)
        print("[recv]", reply)

if __name__ == "__main__":
    asyncio.run(main())
