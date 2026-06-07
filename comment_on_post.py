"""
Discover + perform the Instagram "comment on a post" flow, screen by screen,
using uiautomator. Opens a post URL, captures each screen's elements (saving to
selectors/comment_flow.json and printing them), finds the right selector at each
step, posts a comment via clipboard paste, and confirms it landed.
"""
import asyncio
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import websockets

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL_WS = "ws://127.0.0.1:22221/"
DEVICE = "77329d80ddbc"
POST_URL = "https://www.instagram.com/p/DY4BRQitUK9/"
COMMENT = "nice one"
SMART = False  # when True, generate COMMENT from the post's caption (smart_comment.py)

OUT_DIR = os.path.join(os.path.dirname(__file__), "selectors")
RAW_DIR = os.path.join(OUT_DIR, "raw")
os.makedirs(RAW_DIR, exist_ok=True)
flow_path = os.path.join(OUT_DIR, "comment_flow.json")
flow = json.load(open(flow_path, encoding="utf-8")) if os.path.exists(flow_path) else {}


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


async def ws_send(ws, action, comm):
    await ws.send(json.dumps({"action": action, "comm": comm}))
    return await asyncio.wait_for(ws.recv(), timeout=15)


async def tap(ws, x, y):
    await adb(ws, f"input tap {x} {y}")


async def uidump(ws, retries=3):
    for _ in range(retries):
        await adb(ws, "uiautomator dump /sdcard/window_dump.xml")
        await asyncio.sleep(0.3)
        xml = "\n".join(await adb(ws, "cat /sdcard/window_dump.xml"))
        if xml.strip():
            return xml
        await asyncio.sleep(0.6)
    return ""


def center(b):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return [(x1 + x2) // 2, (y1 + y2) // 2]


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
        out.append({"text": t, "resource_id": a.get("resource-id", ""), "content_desc": d,
                    "class": a.get("class", ""), "clickable": a.get("clickable") == "true",
                    "bounds": a.get("bounds", ""), "center": center(a.get("bounds", ""))})
    return out


def find_center(els, label, exact=True):
    w = label.lower()
    ms = [e for e in els if ((e["text"].lower() == w or e["content_desc"].lower() == w)
          if exact else (w in e["text"].lower() or w in e["content_desc"].lower())) and e["center"]]
    if not ms:
        return None
    cl = [e for e in ms if e["clickable"]]
    return (cl[0] if cl else ms[0])["center"]


def find_by_rid(els, rid_substr):
    """Find an element by resource-id (ignores clickable — tapping the label's
    center still hits the clickable parent at that coordinate)."""
    for e in els:
        if rid_substr in e["resource_id"] and e["center"]:
            return e["center"]
    return None


def field_text_from(els):
    """Current typed text in the comment edit field (empty string if placeholder)."""
    for e in els:
        if "comment_thread_edittext" in e["resource_id"]:
            return (e["text"] or "").strip()
    return ""


async def clear_field(ws, n):
    """Clear the focused field: jump to end, then backspace n times."""
    await adb(ws, "input keyevent 123")  # MOVE_END
    for _ in range(n):
        await adb(ws, "input keyevent 67")  # DEL


async def capture(ws, name):
    xml = await uidump(ws)
    open(os.path.join(RAW_DIR, f"{name}.xml"), "w", encoding="utf-8").write(xml)
    els = parse(xml)
    flow[name] = {"elements": els}
    json.dump(flow, open(flow_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n=== {name} === ({len(els)} elements) — clickable/labeled:", flush=True)
    for e in els:
        lbl = e["text"] or e["content_desc"]
        if e["clickable"] and lbl:
            print(f"   [{e['resource_id'].split('/')[-1]}] {lbl!r} @ {e['center']}", flush=True)
    return els, xml


def comment_count(els):
    for e in els:
        m = re.search(r"comment number is (\d[\d,]*)", e["content_desc"], re.I)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


async def main():
    async with websockets.connect(URL_WS) as ws:
        # 1. Open the post via deep link, handling the "Open with" chooser if it appears
        print(f"Opening {POST_URL}", flush=True)
        await adb(ws, f'am start -a android.intent.action.VIEW -d "{POST_URL}"')
        await asyncio.sleep(4)
        els = parse(await uidump(ws))
        if any("open with" in (e["text"] + e["content_desc"]).lower() for e in els):
            print("   'Open with' chooser -> Remember my choice + Instagram", flush=True)
            rem = find_center(els, "Remember my choice", exact=False)
            if rem:
                await tap(ws, *rem); await asyncio.sleep(0.5)
            ig = find_center(els, "Instagram", exact=True)
            if ig:
                await tap(ws, *ig); await asyncio.sleep(5)
        await asyncio.sleep(2)
        post_els, _ = await capture(ws, "c01_post_open")

        # SMART mode: read the caption off this same dump and let Gemini write a
        # short comment (generic fallback when there's no caption). Set BEFORE the
        # paste/verify step so the existing "field must equal COMMENT exactly,
        # post once" guard applies unchanged.
        global COMMENT
        if SMART:
            from smart_comment import smart_comment_for
            COMMENT, cap, source = smart_comment_for(post_els)
            print(f"   SMART ({source}) — caption {cap[:80]!r}", flush=True)
            print(f"   SMART comment -> {COMMENT!r}", flush=True)

        base_comments = comment_count(post_els)
        print(f"\nBASELINE comment count = {base_comments}", flush=True)

        # 2. Find + tap the comment button (rid row_feed_button_comment; the label
        #    is non-clickable but its center hits the clickable parent)
        cbtn = find_by_rid(post_els, "row_feed_button_comment") or find_center(post_els, "Comment", exact=True)
        if not cbtn:
            print("   !! comment button not found — stopping for review", flush=True); return
        print(f"   comment button @ {cbtn}", flush=True)
        await tap(ws, *cbtn)
        await asyncio.sleep(2.5)

        # 3. Comments sheet — input is rid layout_comment_thread_edittext_multiline;
        #    placeholder is "Start the conversation…" (no comments yet) or "Add a comment…"
        sheet, _ = await capture(ws, "c02_comments_sheet")
        field = (find_by_rid(sheet, "comment_thread_edittext")
                 or find_center(sheet, "start the conversation", exact=False)
                 or find_center(sheet, "add a comment", exact=False))
        if not field:
            print("   !! comment input field not found — stopping for review", flush=True); return
        print(f"   comment field @ {field}", flush=True)

        # 4. Focus the field (tap ONCE)
        await tap(ws, *field)
        await asyncio.sleep(1.5)
        await capture(ws, "c03_input_focused")

        # 5. Paste, then VERIFY the field is EXACTLY the comment (guards against the
        #    paste-doubling bug). If wrong, clear & retry; if it never matches, DO
        #    NOT post — better no comment than a malformed/duplicated one.
        print(f"   writeclipboard: {COMMENT!r}", flush=True)
        await ws_send(ws, "writeclipboard", {"deviceIds": DEVICE, "content": COMMENT})
        await asyncio.sleep(0.6)
        ok = False
        for attempt in range(3):
            await adb(ws, "input keyevent 279")   # KEYCODE_PASTE
            await asyncio.sleep(1.2)
            cur = field_text_from(parse(await uidump(ws)))
            print(f"   field after paste (attempt {attempt + 1}): {cur!r}", flush=True)
            if cur == COMMENT:
                ok = True
                break
            print("   field != comment -> clearing and retrying", flush=True)
            await clear_field(ws, len(cur) + 6)
            await asyncio.sleep(0.6)
        await capture(ws, "c04_text_entered")
        if not ok:
            print("   !! field never matched the comment exactly — NOT posting (no spam)", flush=True)
            return

        # 6. Post — only because the field is verified == the comment, exactly once
        typed = parse(await uidump(ws))
        postbtn = find_by_rid(typed, "comment_thread_post_button") or find_center(typed, "Post", exact=True)
        if not postbtn:
            print("   !! Post button not found — NOT posting", flush=True); return
        print(f"   Post @ {postbtn} — submitting ONE comment", flush=True)
        await tap(ws, *postbtn)
        await asyncio.sleep(3)

        # 7. Confirm
        after, axml = await capture(ws, "c05_after_post")
        present = COMMENT.lower() in axml.lower()
        after_count = comment_count(after)
        print("\n==============================", flush=True)
        print(f"comment text visible in list: {present}", flush=True)
        print(f"comment count: {base_comments} -> {after_count}", flush=True)
        if present or (base_comments is not None and after_count is not None and after_count > base_comments):
            print("RESULT: COMMENT POSTED ✓", flush=True)
        else:
            print("RESULT: UNCONFIRMED", flush=True)
        print("==============================", flush=True)

        # Exit pattern: back out of the comment sheet / reel with the phone's NATIVE
        # Back button (keyevent 4), then leave IG with Home. Don't strand the app in a
        # deep/modal state — symmetric with the open/entry pattern.
        print("   exit: native Back x3 -> Home", flush=True)
        for _ in range(3):
            await adb(ws, "input keyevent 4")   # KEYCODE_BACK (phone's native back)
            await asyncio.sleep(1.2)
        await adb(ws, "input keyevent 3")        # KEYCODE_HOME (leave IG)


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser()
    _ap.add_argument("--url", default=POST_URL)
    _ap.add_argument("--text", default=COMMENT)
    _ap.add_argument("--smart", action="store_true",
                     help="generate the comment from the post's caption via Gemini")
    _ap.add_argument("--device", default=DEVICE,
                     help="target Laixi device id (defaults to the module-level DEVICE constant)")
    _a = _ap.parse_args()
    POST_URL = _a.url        # override module defaults; main() reads these globals
    COMMENT = _a.text
    SMART = _a.smart
    DEVICE = _a.device
    asyncio.run(main())
