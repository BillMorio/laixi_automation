# Account Warming (Instagram) — Workflow & Implementation Guide

_Phase-1 MVP automation. Instagram only. Test device: `77329d80ddbc`._

Warming (养号) = simulate a real human browsing so the account looks active and builds
trust **before it posts**. The cardinal rule: **it must look human.** Regular, robotic
behavior (same dwell, like everything, machine-gun taps) is what gets accounts flagged —
so randomization and restraint are the entire point.

---

## 1. Where we warm

**The Reels feed** — infinite vertical scroll; trivial to watch / like / save / skip. The
viewer's selectors were already captured during the comment work (`like_button`,
`comment_button`, `save_button` in the `clips_*` viewer). Home-feed warming can come later.

## 2. Inputs (the action card's trigger inputs)

| Input | Meaning |
|---|---|
| **Duration (minutes)** | Main input — how long the session runs. The loop stops when time's up. |
| **Intensity** *(optional)* | low / med / high → like-rate ≈ 15 / 25 / 35% |
| Target account / device | (for multi-phone later) |

## 3. Behavior loop (the heart)

```
until elapsed >= duration_minutes:
    1. WATCH  — SHORT, varied dwell (~2.5–9s, occasionally up to ~15s); never camp on a reel
    2. MAYBE LIKE (~25%) — if like_button reads "Like", tap it; confirm it flips to "Liked"
    3. RARELY SAVE (~8%) — tap save_button
    4. SWIPE UP to next reel (randomized distance + speed)
    5. OCCASIONALLY IDLE (~5%) — pause 15–45s
```

Every probability/timing randomized — never the same rhythm twice. **No commenting during
warming** (separate, riskier action).

## 4. End state / logging

Session summary → a `runs` record: `action=warm`,
`result="watched N reels, liked M, saved K over T min"`. That's the card's end-state.

## 5. Selectors (CONFIRMED by discovery)

| Element | Selector / coords | Notes |
|---|---|---|
| Reels tab | content-desc `"Reels"` / `clips_tab` @ **[324, 2159]** | bottom nav |
| Like button | resource-id `like_button` @ **[997, 975]** | tap to like (count +1). See key finding below. |
| Save button | resource-id `save_button` @ **[997, 1715]** | tap to save (best-effort) |
| Comment button | resource-id `comment_button` @ **[997, 1160]** | unused by warming |
| Audio | `media_album_art` @ [997, 2024] | unused |
| Next reel | swipe ≈ `540,1700 → 540,500` | randomize distance/speed |

> **KEY FINDING — how to like & detect likes:**
> - Tapping `like_button` **reliably likes** (verified: like count `549827 → 549828`).
> - The **content-desc is static ("Like" always)** — do NOT use it to detect state.
> - The real signal is the **`selected` attribute**: `false` = not liked, `true` = liked.
> - **Only tap when `selected=false`** — tapping an already-liked button *unlikes* it.
> - **Double-tap-to-like was unreliable** in testing — use the like-button tap instead.
> - The reels like button content-desc is static, so warming reads the node's
>   `selected` attribute (which our element parser must capture).

_Source: `selectors/warm_flow.json` + the `verify_like.py` run._

## 6. Discovery run (first run)

Open IG → Reels, then capture screen by screen into `selectors/warm_flow.json` + raw dumps:
1. `w01_reels_viewer` — confirm like/save/comment selectors + bounds.
2. `w02_after_like` — tap like, re-dump, record how `like_button` content-desc changes
   (so warming can *confirm* a like and avoid toggling it back off).
3. `w03_after_save` — tap save, re-dump, record the change.
4. `w04_next_reel` — swipe up, confirm selectors persist on the next reel.

## 7. The warming script (after discovery)

`warm_account.py --minutes N`: open IG reels → run the behavior loop until the timer
elapses → clean exit (Back×3 → Home) → print the session summary. Python `time` drives the
duration. Selector-driven, heavily randomized.

## 8. Safety / anti-detection

- Randomize everything (dwell, like timing, swipe speed, idle).
- Cap rates — never like every reel (~1 in 4 max); save rarely.
- Per-account daily limits (warm X min/day, not endlessly).
- Human pacing; no rapid-fire taps.
- End with the clean exit pattern.

## 9. Build steps

1. **Discovery run** → capture selectors + like/save state transitions. ✅ _done — see §5._
2. Build `warm_account.py` with the duration loop; first test at 1–2 min. ← _next_
3. Test on the safe account; verify it looks human.
4. Tune probabilities/timings.
5. Wrap into `warm_account(device, minutes)` for the runner.
