"""
Smart comments. Reads the post's caption straight from the on-device uiautomator
dump (no extra scraper/token), then asks Gemini for ONE very short, casual
comment. If there's no caption to work from (or Gemini is unavailable), it falls
back to a generic comment — a generic comment is always safe to post.

Used by comment_on_post.py --smart. The caption is taken from the same dump the
comment flow already captures, so this adds no extra taps or screen reads.
"""
import json
import os
import random
import re
from pathlib import Path

import requests

GEMINI_MODEL = "gemini-2.5-flash-lite"
GENERIC = ["love this", "this is great", "so good", "nice one", "amazing",
           "so cool", "love it", "great stuff", "this is awesome", "obsessed with this"]


def _load_key():
    """GEMINI_API_KEY from the environment, falling back to a local .env line."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key.strip()
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY=") and "=" in line:
                return line.split("=", 1)[1].strip()
    return ""


GEMINI_KEY = _load_key()


def _txt(e):
    return (e.get("text") or "").strip()


def _rid(e):
    return (e.get("resource_id") or e.get("rid") or "").lower()


def _desc(e):
    return (e.get("content_desc") or e.get("desc") or "").strip()


def poster_from(els):
    """The post author's username, read from the feed header content-desc
    (e.g. 'morio_kamau posted a video 6 hours ago')."""
    for e in els:
        m = re.match(r"^(\S+) posted\b", _desc(e))
        if m:
            return m.group(1)
    return None


def extract_caption(els):
    """Best-effort caption from the post-open dump. '' if none is found.

    Layered so it degrades safely: an explicit caption resource-id wins; failing
    that, the caption renders as '<poster> <caption text>', so we take the
    longest poster-prefixed text node that isn't the 'Original audio'
    attribution. Anything unsure -> '' (caller posts a generic comment)."""
    # 1) explicit caption resource-id (most reliable when present)
    for e in els:
        if "caption" in _rid(e) and len(_txt(e)) >= 2:
            return _normalize(_strip_user(_txt(e), poster_from(els)))

    # 2) poster-prefixed text node (distinguishes the caption from comment
    #    previews, which are prefixed with the COMMENTER's name, not the poster's)
    poster = poster_from(els)
    if poster:
        cands = []
        for e in els:
            t = _txt(e)
            low = t.lower()
            if (low.startswith(poster.lower() + " ")
                    and "original audio" not in low
                    and "·" not in t and "•" not in t and "•" not in t
                    and len(t) > len(poster) + 3):
                cands.append(t)
        if cands:
            return _normalize(_strip_user(max(cands, key=len), poster))

    return ""


def _strip_user(t, poster):
    if poster and t.lower().startswith(poster.lower() + " "):
        t = t[len(poster) + 1:]
    return t


def _normalize(t):
    return re.sub(r"\s+", " ", t or "").strip()


def _clean(s):
    """Force a Gemini reply down to a short, bare comment."""
    s = (s or "").strip()
    if not s:
        return ""
    s = s.splitlines()[0].strip().strip('"').strip("'")
    words = s.split()
    if len(words) > 8:
        s = " ".join(words[:8])
    return s.strip(" .!…").strip()


def _gemini(prompt):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 30},
    }
    r = requests.post(url, json=body, timeout=20)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def generate_comment(caption):
    """Return (comment, source). source in {gemini, generic, generic-fallback}."""
    caption = (caption or "").strip()
    if not caption or not GEMINI_KEY:
        return random.choice(GENERIC), "generic"
    prompt = (
        "Write ONE very short, casual Instagram comment reacting to this post. "
        "2 to 5 words. Sound like a real, chill person. No hashtags, no emojis, "
        "no quotes, no @mentions, no trailing punctuation. Output only the comment.\n\n"
        f"Caption: {caption}"
    )
    try:
        out = _clean(_gemini(prompt))
        if out:
            return out, "gemini"
    except Exception as e:  # network / quota / shape — never block on it
        print(f"   smart_comment: Gemini unavailable ({e}) -> generic", flush=True)
    return random.choice(GENERIC), "generic-fallback"


def smart_comment_for(els):
    """Convenience: caption -> comment. Returns (comment, caption, source)."""
    cap = extract_caption(els)
    text, source = generate_comment(cap)
    return text, cap, source


if __name__ == "__main__":
    # Offline smoke test: generate from a sample caption (no posting involved).
    import sys
    sample = " ".join(sys.argv[1:]) or "sunset hikes hit different when you bring the whole crew"
    txt, src = generate_comment(sample)
    print(f"caption: {sample!r}")
    print(f"comment ({src}): {txt!r}")
