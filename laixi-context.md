# Laixi API — Complete Single-File Reference

**For Custom HTML/CSS/JS Dashboard Development**  
**Last Updated**: May 2026 (Laixi v1.1.5.1+)  
**Your Device Example**: `77329d80ddbc` (from your screenshot)  
**One and only endpoint**: `ws://127.0.0.1:22221/`

Save this entire document as **`LAIXI-API-REFERENCE.md`** — keep it open while coding. Everything you need is here.

---

## 1. Quick Start — Connect in 10 Seconds

```html
<script>
  let ws;

  function connect() {
    ws = new WebSocket("ws://127.0.0.1:22221/");

    ws.onopen = () => {
      console.log("✅ Connected to Laixi API");
      ws.send(JSON.stringify({ action: "List" })); // First test
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("Laixi response →", data);
      // Handle devices, screenshots, etc. here
    };

    ws.onerror = (e) => console.error("WS Error", e);
    ws.onclose = () => console.log("Disconnected");
  }

  // Call on page load
  window.onload = connect;
</script>
```

## 2. Message Format (Every Request)

```json
{
  "action": "ACTION_NAME",
  "comm": {
    "deviceIds": "77329d80ddbc" // or "all"
    // ... other parameters
  }
}
```

Common parameters:

- `deviceIds`: `"all"` or comma-separated IDs (e.g. `"77329d80ddbc,anotherid"`)
- `deviceId`: used by a few commands instead

## 3. Core API Actions (Copy-Paste Ready)

### 5.2 List All Devices (Most Important First Command)

```json
{ "action": "List" }
```

Use this to get real-time device list, status, resolution, connection type, etc.

### 5.3 Screenshot

```json
{
  "action": "screen",
  "comm": {
    "deviceIds": "all",
    "savePath": "D:\\laixi_screenshots" // change to your folder
  }
}
```

### 5.4 Screen Control / Touch / Swipe (pointerEvent)

```json
{
  "action": "pointerEvent",
  "comm": {
    "deviceIds": "77329d80ddbc",
    "mask": "0", // 0 = press, 1 = move, 2 = release, 3 = right click,
    // 4 = wheel up, 5 = wheel down, 6-9 = swipe directions
    "x": "0.5", // 0.0 to 1.0 (percentage of screen)
    "y": "0.5",
    "endx": "0.5", // for swipe only
    "endy": "0.2",
    "delta": "1"
  }
}
```

### 5.5 Get Clipboard (single device only)

```json
{
  "action": "getclipboard",
  "comm": { "deviceIds": "77329d80ddbc" }
}
```

### 5.6 Write to Clipboard

```json
{
  "action": "writeclipboard",
  "comm": {
    "deviceIds": "all",
    "content": "Hello from my custom dashboard!"
  }
}
```

### 5.7 Upload File + Auto Install APK

```json
{
  "action": "beginfilesend",
  "comm": {
    "filePaths": "C:\\myapp.apk",
    "isAutoInstall": "1", // 0 = upload only, 1 = install
    "deviceIds": "all"
  }
}
```

### 5.8 Pull File from Phone to PC

```json
{
  "action": "PullFile",
  "comm": {
    "deviceIds": "77329d80ddbc",
    "phoneFilePath": "/storage/emulated/0/Download/test.png",
    "savePath": "C:\\Downloads\\pulled.png"
  }
}
```

### 5.9 Execute Any ADB Command

```json
{
  "action": "adb",
  "comm": {
    "command": "am start -a android.intent.action.VIEW -d https://google.com",
    "deviceIds": "77329d80ddbc"
  }
}
```

## 4. Additional Powerful Actions (Still Available)

- AutoX.js Scripts: `ExecuteAutoJs`, `StopAutoJs`
- Download file directly to phone: `HttpDown`
- Current running app: `CurrentAppInfo`
- Launch specific app
- Send toast notification
- Input text
- Device grouping, renaming, batch operations

(Full docs at https://docs.laixi.app/en/docs/API/ if you need more)

## 5. Dashboard Building Best Practices

- Always start with `"List"` on connect to populate your device grid.
- Screenshots are saved to disk → use `<img src="file:///D:/laixi_screenshots/deviceID.png">` or run a local static server for that folder.
- Live control: On mouse/touch events, send `pointerEvent` (add small debounce).
- Batch actions: Most commands accept `"all"` or multiple device IDs.
- Error handling: Look for `"success": false` or error messages in responses.
- Reconnection: Add a reconnect button or auto-reconnect on close.
- Local serving: Open your HTML via `http://localhost` (not `file://`) for best compatibility.

## 6. Quick Test Commands (Copy → Paste into console or tester)

```json
{ "action": "List" }
{ "action": "screen", "comm": { "deviceIds": "all", "savePath": "D:\\laixi_screenshots" } }
```

---

This is your single source of truth.  
No more scattered messages. Everything you need to build the full English dashboard (device list, clickable screen, batch controls, file manager, etc.) is right here in this one file.

Copy the entire content above into `LAIXI-API-REFERENCE.md` and you're good to go forever.

Want me to also give you a complete starter `index.html` dashboard that uses this reference (with live device list + screenshot button + basic tap control)? Just say the word and I'll drop it next.

You now have everything in one clean file. Let's build this thing!
