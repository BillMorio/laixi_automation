import asyncio
import json
import websockets

URL = "ws://127.0.0.1:22221/"

async def main():
    print(f"Connecting to {URL} ...")
    try:
        async with websockets.connect(URL) as ws:
            print("[open] connected")
            await ws.send(json.dumps({"action": "List"}))
            print("[sent] {\"action\": \"List\"}")
            reply = await asyncio.wait_for(ws.recv(), timeout=5)
            print("[recv]", reply)
            print("\nHandshake OK.")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
