# Instagram Posting Workflow — Progress & Status

_Last updated: 2026-05-28_

Status of the automated **Instagram reel posting** flow (the first automation we're
building toward the larger platform in `SYSTEM-DESIGN.md`). Test device: `77329d80ddbc`
(Redmi Note 11, 1080×2400). Test account: **@radish271**.

---

## TL;DR — what works

- ✅ **End-to-end posting works.** A reel is uploaded, pushed to the phone, selected,
  and published. Verified live multiple times.
- ✅ **Video header fix works.** ffmpeg re-mux repairs the zeroed MP4 duration that made
  IG reject clips (the old 0:00 bug).
- ✅ **Selector-based navigation works.** Every screen is driven by uiautomator
  selectors (text / content-desc / resource-id) — only the home `+` is a coordinate.
- ✅ **Post confirmation works.** Reading the profile post count (before vs after)
  reliably confirms a post went up.

The remaining work is **reliability of the publish step in the headless script** (the
browser dashboard already does it reliably; the Python port over-taps — see Known Issues).

---

## The flow, step by step (with selectors)

| # | Screen | Action | How it's targeted |
|---|--------|--------|-------------------|
| 1 | Home | Open new post | tap `+` at **[66,167]** — ⚠️ pure coordinate (bare node, no label) |
| 2 | Composer | Select newest video | content-desc `"Video thumbnail created on <timestamp>"` (pick latest) |
| 3 | Composer | Next | text `"Next"` |
| 4 | Editor | Next | text `"Next"` |
| 5 | Caption ("New reel") | Tap **Share** ONCE — this publishes | text `"Share"` (the blue button by the "Write a caption…" field) |
| 6 | (any post-share screens) | **Ignore them** — do not tap anything | — just navigate away |
| 7 | Confirm | Go to profile, **refresh while it uploads** | exit reels: **Back → Home tab → Profile tab**, then pull-to-refresh + read post count |

> **Publish rule (important):** one Share tap publishes. Do **not** handle the
> post-share screens (About Reels, Facebook cross-post) — re-tapping or looping there is
> what caused failures. After Share: go to the profile and refresh until the post shows.

**Post-count element:** resource-id `profile_header_post_count_front_familiar`,
content-desc like `"N posts"`. Read N before and after; +1 = confirmed posted.

**Caption field** (for future caption automation): content-desc
`"Write a caption and add hashtags…"`.

---

## Video normalization (the critical reliability fix)

Clips ripped/downloaded from social media often have a **zeroed `mvhd` duration** in the
MP4 header. Players compute the real length, so they play fine — but Android/Instagram
read the header, see `0`, and treat it as a 0-second video → shows **0:00** and IG
**rejects** it.

Fix (server-side, on upload): `ffmpeg -c:v copy -c:a aac -movflags +faststart` —
a fast, lossless re-mux that rewrites a correct header. Non-H.264 clips get re-encoded.

---

## Selectors captured

- `selectors/ig_flow.json` — parsed interactive elements (text, resource-id,
  content-desc, bounds, center) for the home, composer, editor, caption, FB-crosspost,
  and profile screens.
- `selectors/raw/*.xml` — raw uiautomator dumps per screen.

---

## Known issues / hard-won lessons

1. **uiautomator dumps lag the real screen (stale).** After an action, a dump can still
   show the *previous* screen for a beat. ⇒ **Do not loop-tap based on dumps.** Tap once,
   wait, move on. (This is what made the publish step tap Share 7–12× and look chaotic.)
2. **The publish step was over-engineered.** The caption Share tap publishes; stop after
   it. At most: caption Share → (maybe) About Reels Share → (maybe) FB "Not now". No loop.
3. **"Share" is ambiguous.** The reels feed has a Share button on *every* reel, so a
   "find Share and tap" loop misfires once you've landed on the feed. Only tap Share on a
   compose screen, and never iterate it.
4. **Profile tab is swallowed in the immersive reels feed.** After posting, IG lands on
   the reels feed; a direct Profile-tab tap does nothing. Use **Back → Home tab → Profile
   tab** to reach the profile.
5. **Home `+` has no selector** — it's a bare clickable node. It stays a coordinate
   `[66,167]` (stable top-left). The one unavoidable coordinate.
6. **Reading the post count requires being on the profile** (wait for `profile_header*`
   to be present before reading, or it returns None).

---

## Files

| File | Purpose |
|---|---|
| `index.html` | Browser dashboard — the **manual** posting flow that works reliably |
| `app.py` | Local server: serves dashboard, video upload + ffmpeg normalize, screenshots |
| `post_and_confirm.py` | Headless Python runner (WIP) — post + profile-count confirm |
| `capture_ig_flow.py`, `capture_full.py`, `capture_profile.py` | Selector-capture tools |
| `nav_profile.py`, `check_state.py`, `confirm_now.py` | Diagnostics |
| `selectors/ig_flow.json` | The captured selector map |
| `ARCHITECTURE.md` | Current dashboard architecture |
| `SYSTEM-DESIGN.md` | Target platform (local runner + online backend + DB + dashboard) |
| `backups/` | Timestamped code backups |

---

## Next steps

1. **Simplify the publish step** in `post_and_confirm.py`: tap caption Share once, brief
   wait, handle About Reels / FB at most once each, then **stop** — confirm via the
   profile post-count delta. No re-tapping loop.
2. Fold the proven flow into a clean, reusable **`post_to_ig(device, video)`** handler
   (the headless action-handler the runner will call — see `SYSTEM-DESIGN.md` §7).
3. Build the runner + local SQLite `runs` log around it (per `SYSTEM-DESIGN.md`).
4. Add caption support (paste into the caption field by its content-desc selector).
