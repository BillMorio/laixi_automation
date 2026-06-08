"""
Account warming (Instagram Reels). Scrolls reel after reel for a set duration,
watching each a short, varied amount, liking ~randomly, saving ~rarely.
Everything randomized so it doesn't look robotic. The whole session (open +
scroll + exit) fits within the requested minutes, and the real duration is logged.

Usage:  python warm_account.py --minutes 5

Selectors (confirmed in discovery, see WARMING-WORKFLOW.md):
  Reels tab  -> content-desc "Reels"  ~ [324,2159]
  like_button -> [997,975]   (like = count+1; liked state = `selected` attr true)
  save_button -> [997,1715]
  next reel   -> swipe up
"""
import argparse
import asyncio
import json
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEVICE = "77329d80ddbc"

# Behaviour tuning (all randomized around these)
P_LIKE = 0.25      # like ~1 in 4 reels
P_SAVE = 0.08      # save rarely


async def adb(ws, cmd, timeout=20):
    await ws.send(json.dumps({"action": "adb", "comm": {"deviceIds": DEVICE, "command": cmd}}))
    r = await asyncio.wait_for(ws.recv(), timeout=timeout)
    try:
        inner = json.loads(r).get("result")
    except json.JSONDecodeError:
        return []
    if isinstance(inner, str) and inner:
        try:
            return json.loads(inner).get(DEVICE, [])
        except json.JSONDecodeError:
            return [inner]
    return []


async def tap(ws, x, y):
    await adb(ws, f"input tap {x} {y}")


async def uidump(ws, retries=3):
    for _ in range(retries):
        await adb(ws, "uiautomator dump /sdcard/window_dump.xml")
        await asyncio.sleep(0.3)
        xml = "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))
        if xml.strip():
            return xml
        await asyncio.sleep(0.5)
    return ""


def parse(xml):
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for n in root.iter("node"):
        a = n.attrib
        t, d = a.get("text", ""), a.get("content-desc", "")
        if not (a.get("clickable") == "true" or t or d):
            continue
        b = a.get("bounds", "")
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
        c = [(int(m.group(1)) + int(m.group(3))) // 2,
             (int(m.group(2)) + int(m.group(4))) // 2] if m else None
        out.append({"rid": a.get("resource-id", ""), "text": t, "desc": d,
                    "selected": a.get("selected") == "true", "center": c})
    return out


def by_rid(els, rid):
    for e in els:
        if rid in e["rid"] and e["center"]:
            return e
    return None


def find_center(els, label):
    w = label.lower()
    for e in els:
        if (e["text"].lower() == w or e["desc"].lower() == w) and e["center"]:
            return e["center"]
    return None


async def dismiss(ws):
    for _ in range(2):
        els = parse(await uidump(ws))
        for lbl in ["While using the app", "Continue", "OK", "Not now", "Allow access"]:
            c = find_center(els, lbl)
            if c:
                await tap(ws, *c); await asyncio.sleep(1.2); break
        else:
            break


async def get_screen(ws):
    """Read the phone's screen resolution via `wm size`. The original selectors
    were calibrated on a 1080x2160 phone; on a 1440x2960 Samsung S8 the same
    pixel coordinates miss the Reels tab and can land on Samsung's Recent-Apps
    nav button (which lives at the bottom-LEFT, not bottom-right). Scaling fixes
    that."""
    res = await adb(ws, "wm size")
    for line in res:
        m = re.search(r"(\d+)x(\d+)", line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 1080, 2160  # fallback to the original calibration size


async def main(minutes):
    async with websockets.connect("ws://127.0.0.1:22221/") as ws:
        t_start = time.time()                               # wall clock, for real duration
        m_deadline = time.monotonic() + minutes * 60 - 8    # whole session (open+scroll+exit) fits in `minutes`

        # Resolution-aware scaling. BASE_* is what every hard-coded coord in this
        # file was originally calibrated against; sx/sy convert to the real device.
        BASE_W, BASE_H = 1080, 2160
        w, h = await get_screen(ws)
        sx = lambda x: int(x * w / BASE_W)
        sy = lambda y: int(y * h / BASE_H)
        print(f"WARMING device {DEVICE} | screen {w}x{h} (scale {w/BASE_W:.2f}x)", flush=True)

        # Open IG -> Reels
        await adb(ws, "am force-stop com.instagram.android")
        await asyncio.sleep(1.5)
        await adb(ws, "monkey -p com.instagram.android -c android.intent.category.LAUNCHER 1")
        await asyncio.sleep(6)
        await dismiss(ws)

        # Reels tab. Order of preference, most specific first:
        #   1) resource-id 'clips_tab' (IG's internal name for Reels). The ONLY
        #      element with this rid is the real bottom-nav Reels button.
        #   2) content-desc 'Reels' AND in the bottom 20% of the screen. The
        #      desc 'Reels' also appears on in-content labels (story circles,
        #      profile sections); the y-filter rules those out.
        #   3) scaled fixed coordinate (last resort, may miss).
        els = parse(await uidump(ws))
        reels, src = None, None
        for e in els:
            if "clips_tab" in (e["rid"] or "") and e["center"]:
                reels, src = e["center"], "rid clips_tab"; break
        if not reels:
            for e in els:
                d = (e["desc"] or "").lower()
                t = (e["text"] or "").lower()
                if (d == "reels" or t == "reels") and e["center"] and e["center"][1] >= h * 0.8:
                    reels, src = e["center"], "desc Reels (bottom nav)"; break
        if reels:
            print(f"  Reels tab via {src} @ {reels}", flush=True)
        else:
            reels = [sx(324), sy(2159)]
            print(f"  Reels tab NOT found by selector; using scaled coords {reels}", flush=True)
        await tap(ws, *reels); await asyncio.sleep(4)
        await dismiss(ws)
        await asyncio.sleep(3)  # let the first reel settle

        # Verify we actually landed on the Reels feed. like_button is the
        # signature element of a reel; if it's not on screen, our tap missed
        # and the script would otherwise scroll the wrong feed silently.
        verify_els = parse(await uidump(ws))
        on_reels = any("like_button" in (e["rid"] or "") for e in verify_els)
        if on_reels:
            print("  Reels feed confirmed (like_button present)", flush=True)
        else:
            print("  WARNING: Reels feed NOT confirmed (no like_button on screen)", flush=True)
            print("           tap likely missed the Reels nav; script will continue but may scroll the wrong feed.", flush=True)

        watched = liked = saved = 0
        print(f"WARMING for {minutes} min — scrolling reels...", flush=True)

        while time.monotonic() < m_deadline:
            # WATCH a SHORT, varied amount — mostly 2-6s, occasionally up to ~10s.
            # Never a long pause on any single reel.
            dwell = random.uniform(6, 10) if random.random() < 0.15 else random.uniform(2, 6)
            watched += 1
            remaining = int(m_deadline - time.monotonic())
            print(f"  reel #{watched}: watch {dwell:.0f}s   ({remaining}s left)", flush=True)
            await asyncio.sleep(dwell)

            # LIKE (~P_LIKE): the only screen-read in the loop — one quick dump to
            # check the `selected` attribute so we never accidentally UN-like an
            # already-liked reel. The like button is found by rid, so the tap
            # coordinate is the element's actual center on THIS device.
            if random.random() < P_LIKE:
                lb = by_rid(parse(await uidump(ws)), "like_button")
                if lb and lb["selected"] is False:
                    await tap(ws, *lb["center"]); await asyncio.sleep(1.0)
                    liked += 1; print("    -> liked", flush=True)
                elif lb and lb["selected"]:
                    print("    (already liked, skip)", flush=True)
            # SAVE (~P_SAVE): scaled coord (no dump, fewer reads per loop).
            if random.random() < P_SAVE:
                await tap(ws, sx(997), sy(1715)); await asyncio.sleep(0.8)
                saved += 1; print("    -> saved", flush=True)

            # SCROLL to the next reel (randomized distance + speed). All coords
            # scaled so the swipe stays inside the content area (not the nav bar)
            # regardless of phone resolution.
            y1 = sy(1650) + random.randint(-40, 40)
            y2 = sy(480)  + random.randint(-60, 60)
            await adb(ws, f"input swipe {sx(540)} {y1} {sx(540)} {y2} {random.randint(250, 430)}")
            await asyncio.sleep(random.uniform(1.0, 2.0))  # let next reel load

        # Clean exit
        print("   exit: native Back x3 -> Home", flush=True)
        for _ in range(3):
            await adb(ws, "input keyevent 4"); await asyncio.sleep(1.2)
        await adb(ws, "input keyevent 3")

        actual = (time.time() - t_start) / 60
        print(f"\n=== WARMING DONE === watched {watched} reels, liked {liked}, "
              f"saved {saved}  |  requested {minutes} min, ACTUAL {actual:.1f} min", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=5)
    ap.add_argument("--device", default=DEVICE,
                    help="target Laixi device id (defaults to the module-level DEVICE constant)")
    args = ap.parse_args()
    DEVICE = args.device  # override the module-level constant for adb()/tap()
    asyncio.run(main(args.minutes))
