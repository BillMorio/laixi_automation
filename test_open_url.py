import asyncio
import json
import websockets

URL = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
TARGET = "https://claude.ai"

async def main():
    print(f"Connecting to {URL} ...")
    async with websockets.connect(URL) as ws:
        print("[open] connected")
        payload = {
            "action": "adb",
            "comm": {
                "command": f"am start -a android.intent.action.VIEW -d {TARGET}",
                "deviceIds": DEVICE,
            },
        }
        await ws.send(json.dumps(payload))
        print(f"[sent] open {TARGET} on {DEVICE}")
        reply = await asyncio.wait_for(ws.recv(), timeout=10)
        print("[recv]", reply)
        print("\nCheck your phone — it should be loading the URL.")

if __name__ == "__main__":
    asyncio.run(main())
