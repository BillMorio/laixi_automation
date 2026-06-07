# Phone-Farm Automation Platform — System Design

A platform to **run, schedule, and log** daily social-media automations across a farm of
Android devices (motherboards) driven by Laixi, with a clear record of *which phone did
what, when, and whether it worked* — viewable both locally (on the farm machine) and
online (from anywhere).

---

## 1. Goals

- Run daily automations per device/account: **warming, liking, commenting, following,
  posting, text input, auto-reply, AI tasks** across **Instagram / TikTok / YouTube**.
- **Log every run** — device, account, platform, action, outcome, timing, error, content used.
- **Two dashboards**: a **local** one (real-time, runs even if the internet is down) and an
  **online** one (history + remote monitoring from anywhere).
- Resilient to **China ↔ rest-of-world connectivity** (Great Firewall latency/blocking).
- Scale from **1 farm machine / 20 devices** today to **many machines / hundreds** later
  without re-architecture.

---

## 2. Architecture overview

```
  FARM MACHINE (China, behind AnyDesk)                 ONLINE (hosted, view anywhere)
┌───────────────────────────────────────┐          ┌──────────────────────────────────┐
│  Laixi  (WS :22221)  ── USB ──► phones │          │  Backend API  (FastAPI)           │
│        ▲                               │          │  Postgres (master DB)             │
│        │ device commands               │  HTTPS   │  Object storage (videos)          │
│  ┌─────┴───────────────────────────┐   │  sync    │                                   │
│  │ LOCAL RUNNER (FastAPI + worker) │───┼────────► │  serves ─► ONLINE DASHBOARD       │
│  │  - automation engine (Python)   │   │ runs/    │            (history, remote)      │
│  │  - scheduler (APScheduler)      │ ◄─┼─jobs──── │                                   │
│  │  - SQLite (local-first log)     │   │          └──────────────────────────────────┘
│  │  - serves LOCAL DASHBOARD       │   │
│  └─────────────────────────────────┘   │
└───────────────────────────────────────┘
```

**Core principle — local-first:** the runner writes every run to **local SQLite first**
(instant, never blocked), then **syncs to the online Postgres** in the background with
retry. Automation and the local dashboard never depend on the internet link being healthy.

**Why the runner must be local:** Laixi only listens on `127.0.0.1:22221`. Only software on
the farm machine can issue device commands. The online backend is the *control plane and
record store* — never the device path.

---

## 3. Three tiers

| Tier | Runs where | Responsibility | Stack |
|---|---|---|---|
| **Local Runner** | Farm machine | Execute automations via Laixi, schedule jobs, log runs locally, serve local dashboard, sync up | Python, FastAPI, APScheduler, `websockets`, SQLite, httpx |
| **Online Backend** | Cloud / VPS | Master DB, ingest synced runs, serve online dashboard API, hold schedules/jobs/content registry | FastAPI, Postgres, object storage |
| **Dashboards** | Browser | Local (live) + Online (history). Same React/vanilla SPA, different API base URL | Dark UI (see §9) |

---

## 4. Action taxonomy

Modeled directly from Laixi's capabilities. Stored as the `action_type` enum.

| `action_type` | Description | Platforms | Key params |
|---|---|---|---|
| `warm` | Account warming — scroll, watch, like, save (养号) | IG, TikTok, YT | `duration_min`, `intensity` |
| `like` | Batch like target content | IG, TikTok | `target`, `count` |
| `comment` | Smart comment on target content | IG, TikTok | `target`, `comment_pool_id`, `count` |
| `follow` | Follow accounts in a niche | IG, TikTok, YT | `niche`/`target`, `count` |
| `post` | Scheduled/cyclic posting (video + caption) | IG, TikTok, YT | `content_id`, `caption_strategy` |
| `content_upload` | Push video to phone + open app (precursor to post) | IG, TikTok, YT | `content_id` |
| `text_input` | Set captions / bios / comments in bulk | all | `text`, `field` |
| `auto_reply` | Monitor comments and reply | IG, TikTok | `reply_pool_id`, `window_min` |
| `ai_task` | Laixi Claw natural-language task | all | `prompt` |

Enums used throughout:
- `platform`: `instagram` | `tiktok` | `youtube`
- `run_status` / `job_status`: `pending` | `queued` | `running` | `success` | `failed` | `skipped` | `cancelled`
- `account_status`: `active` | `warming` | `quarantined` | `banned` | `logged_out`
- `device_status`: `online` | `offline` | `busy` | `error`

---

## 5. Database schema (master = Postgres)

```sql
-- A farm machine running Laixi + an agent.
CREATE TABLE hosts (
  id            BIGSERIAL PRIMARY KEY,
  name          TEXT NOT NULL,            -- "China Farm 1"
  location      TEXT,
  agent_version TEXT,
  status        TEXT DEFAULT 'offline',   -- online | offline
  last_heartbeat TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- A physical device / motherboard, as seen by Laixi.
CREATE TABLE devices (
  id          BIGSERIAL PRIMARY KEY,
  host_id     BIGINT REFERENCES hosts(id),
  laixi_id    TEXT NOT NULL,              -- e.g. 77329d80ddbc
  label       TEXT,                       -- friendly name / slot number
  model       TEXT,                       -- 2201116SI
  resolution  TEXT,                       -- 1080x2400  (drives tap coords)
  status      TEXT DEFAULT 'offline',     -- device_status enum
  last_seen   TIMESTAMPTZ,
  notes       TEXT,
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (host_id, laixi_id)
);

-- A social account; lives on a device (one device can host several over time).
CREATE TABLE accounts (
  id            BIGSERIAL PRIMARY KEY,
  platform      TEXT NOT NULL,            -- platform enum
  username      TEXT NOT NULL,
  device_id     BIGINT REFERENCES devices(id),
  status        TEXT DEFAULT 'warming',   -- account_status enum
  warmup_stage  INT DEFAULT 0,            -- days/level into warming
  proxy         TEXT,
  followers     INT,                      -- last known snapshot
  last_action_at TIMESTAMPTZ,
  notes         TEXT,
  created_at    TIMESTAMPTZ DEFAULT now(),
  UNIQUE (platform, username)
);

-- Reusable media + text assets.
CREATE TABLE content (
  id           BIGSERIAL PRIMARY KEY,
  type         TEXT NOT NULL,             -- video | image | caption | hashtags | comment
  platform     TEXT,                      -- null = cross-platform
  url          TEXT,                      -- object-storage URL (videos/images)
  file_path    TEXT,                      -- path on the farm machine after sync-down
  text_body    TEXT,                      -- caption/hashtag/comment text
  duration_s   NUMERIC,
  width INT, height INT,
  normalized   BOOLEAN DEFAULT false,     -- passed the ffmpeg header fix
  status       TEXT DEFAULT 'available',  -- available | used | archived
  used_count   INT DEFAULT 0,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- Recurring automation definitions (the "do this daily" rules).
CREATE TABLE schedules (
  id           BIGSERIAL PRIMARY KEY,
  name         TEXT NOT NULL,
  action_type  TEXT NOT NULL,             -- action_type enum
  platform     TEXT NOT NULL,
  target_type  TEXT NOT NULL,             -- device | group | account | all
  target_id    BIGINT,                    -- id of the target (null for "all")
  params       JSONB DEFAULT '{}',        -- action-specific (count, duration, content pool…)
  cadence      TEXT NOT NULL,             -- cron expression or interval
  jitter_min   INT DEFAULT 0,             -- randomize start to look human
  enabled      BOOLEAN DEFAULT true,
  last_run_at  TIMESTAMPTZ,
  next_run_at  TIMESTAMPTZ,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- A concrete unit of work (from a schedule or created manually).
CREATE TABLE jobs (
  id           BIGSERIAL PRIMARY KEY,
  schedule_id  BIGINT REFERENCES schedules(id),  -- null = ad-hoc/manual
  action_type  TEXT NOT NULL,
  platform     TEXT NOT NULL,
  device_id    BIGINT REFERENCES devices(id),
  account_id   BIGINT REFERENCES accounts(id),
  content_id   BIGINT REFERENCES content(id),
  params       JSONB DEFAULT '{}',
  status       TEXT DEFAULT 'pending',    -- job_status enum
  priority     INT DEFAULT 0,
  scheduled_for TIMESTAMPTZ,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- THE LOG: one row per execution attempt. This answers "what phone did what".
CREATE TABLE runs (
  id            BIGSERIAL PRIMARY KEY,
  job_id        BIGINT REFERENCES jobs(id),    -- null = manual/ad-hoc run
  host_id       BIGINT REFERENCES hosts(id),
  device_id     BIGINT REFERENCES devices(id),
  account_id    BIGINT REFERENCES accounts(id),
  action_type   TEXT NOT NULL,
  platform      TEXT NOT NULL,
  status        TEXT NOT NULL,                 -- running | success | failed | skipped
  started_at    TIMESTAMPTZ NOT NULL,
  finished_at   TIMESTAMPTZ,
  duration_ms   INT,
  result_summary TEXT,                         -- "Posted — upload complete"
  error         TEXT,                          -- failure reason
  steps         JSONB,                         -- [{step, status, at}] fine-grained trace
  content_id    BIGINT REFERENCES content(id),
  artifact_ref  TEXT,                          -- posted URL / screenshot path
  local_uid     UUID,                          -- dedupe key for local→online sync
  created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_runs_device_time ON runs (device_id, started_at DESC);
CREATE INDEX idx_runs_status      ON runs (status);
CREATE INDEX idx_runs_action      ON runs (action_type, platform);

-- Optional: post-performance metrics gathered later (views/likes growth).
CREATE TABLE run_metrics (
  id          BIGSERIAL PRIMARY KEY,
  run_id      BIGINT REFERENCES runs(id),
  metric      TEXT NOT NULL,             -- views | likes | comments | shares
  value       BIGINT,
  captured_at TIMESTAMPTZ DEFAULT now()
);

-- System/audit events (agent start, device dropped, errors).
CREATE TABLE events (
  id        BIGSERIAL PRIMARY KEY,
  host_id   BIGINT REFERENCES hosts(id),
  device_id BIGINT REFERENCES devices(id),
  level     TEXT DEFAULT 'info',         -- info | warn | error
  type      TEXT,
  message   TEXT,
  at        TIMESTAMPTZ DEFAULT now()
);
```

### Local SQLite (on the farm machine)
A subset, mirroring the same shapes:
- `runs` — written first locally, each with `local_uid` + a `synced BOOLEAN` flag.
- `jobs` + `schedules` — a cache pulled from the backend so the runner works offline.
- `devices` — local device state/heartbeats.

The sync worker: `INSERT`s unsynced `runs` to the backend (`POST /api/runs/sync`),
marks them synced; `GET`s schedule/job updates. Idempotent via `local_uid`.

---

## 6. API design

### Runner → Backend (sync + control)
| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/hosts/heartbeat` | Host alive + agent version |
| `POST` | `/api/devices/sync` | Upsert device list/status from Laixi `List` |
| `POST` | `/api/runs/sync` | Batch-push completed runs (idempotent on `local_uid`) |
| `GET`  | `/api/jobs/pending?host_id=` | Pull queued jobs to execute (pull model) |
| `PATCH`| `/api/jobs/{id}` | Update job status (running/success/failed) |
| `GET`  | `/api/schedules?host_id=` | Fetch active schedules to materialize jobs |
| `GET`  | `/api/content/{id}/download` | Fetch a video to push to a phone |

### Dashboard → Backend (read + manage)
| Method | Endpoint | Purpose |
|---|---|---|
| `GET`  | `/api/runs?device=&action=&platform=&status=&from=&to=` | The runs log (filtered) |
| `GET`  | `/api/devices` | Devices + live status |
| `GET`  | `/api/accounts?status=` | Accounts + health |
| `GET`  | `/api/stats/overview` | Counts, success rates, by platform/action/day |
| `GET/POST/PATCH` | `/api/schedules` | Manage recurring automations |
| `POST` | `/api/jobs` | Trigger an ad-hoc action |
| `GET/POST` | `/api/content` | Content library |

The **local dashboard** hits the runner's own API (same shapes, reading local SQLite) so
it works with zero internet. The **online dashboard** hits the backend.

---

## 7. Execution model (the runner)

- **Scheduler** (APScheduler): on each tick, reads enabled `schedules`, applies `jitter_min`,
  and materializes `jobs` (status `queued`) for the due devices/accounts.
- **Worker pool**: pulls `queued` jobs and runs them. Concurrency is **bounded** (e.g. 3–5
  devices in parallel) — the uiautomator-driven flows are per-device sequential, and ADB
  gets unstable if you hammer all 20 at once.
- **Per job**: create a `run` (`running`) → dispatch to the action handler
  (`post`, `warm`, `like`, …) → handler drives Laixi (the engine we already built, ported to
  Python) → update the `run` (`success`/`failed`) with `result_summary`, `error`, `steps`.
- **Human-like pacing**: jittered delays, randomized order, per-account daily caps.
- **Safety**: on repeated failures for an account → set `account.status = quarantined` and
  stop scheduling it until reviewed.
- **Retries**: failed jobs re-queued up to N times with backoff.
- **Sync worker**: every ~15 s, push unsynced runs + heartbeat to the backend (retry-tolerant).

**The critical enabler (first build step):** port the browser automation
(`postToInstagram`, `dismissNotices`, `tapByText`, `uiDump`, etc.) into a headless Python
**action-handler module** the worker can call: `handlers.post(device, account, content)`,
`handlers.warm(device, account, params)`, …

---

## 8. Technology stack

| Concern | Choice | Why |
|---|---|---|
| Local runner | **Python 3.11 + FastAPI** | Serves local dashboard + local API, runs background workers |
| Scheduling | **APScheduler** | Cron-like, in-process |
| Laixi comms | **`websockets`** + the ported action handlers | Talk to local Laixi |
| Local store | **SQLite** | Local-first, zero-setup, fast |
| Video fix | **ffmpeg/ffprobe** | The mvhd duration fix (already proven) |
| Online backend | **FastAPI + Postgres** | Async API + relational integrity for jobs/accounts |
| Object storage | **S3-compatible** (or backend disk to start) | Video library |
| Hosting | **Railway / Render / Fly / VPS**; or **Supabase** (Postgres + auto API) | Pick for latency to China |
| Dashboards | **Vite + React + TypeScript** (or keep vanilla) | The dark SPA in §9 |
| Auth | Token per host (runner↔backend) + login for dashboard | |

---

## 9. Dashboard design — dark, minimal, Linear/Tesla

### Visual language
- **Background** `#09090b`, **surfaces** `#131316` / `#18181b`, **borders** `#27272a` (1px, no heavy shadows).
- **Text** primary `#fafafa`, muted `#a1a1aa`. **Accent** electric indigo `#6366f1` / blue `#3b82f6`.
- **Status**: success `#22c55e`, running `#f59e0b`, failed `#ef4444`, idle/grey `#52525b`.
- **Type**: Inter; **monospace** (JetBrains Mono) for IDs, timestamps, device codes.
- Compact density, generous whitespace, rounded-md (8px), subtle hover, quiet micro-transitions.
  Status as **soft-tinted pills**, not loud blocks. Feels like Linear: keyboard-friendly, fast, calm.

### Layout — fixed left sidebar + content
```
┌────────────┬──────────────────────────────────────────────┐
│ ◆ FarmOps  │  Overview                          [China F1 ●]│
│            │  ┌─────────┬─────────┬─────────┬─────────┐     │
│ ▸ Overview │  │ Runs    │ Success │ Active  │ Quaran- │     │
│ ▸ Devices  │  │ today   │  rate   │ devices │ tined   │     │
│ ▸ Runs     │  │  342    │  96.2%  │ 19/20   │   1     │     │
│ ▸ Schedule │  └─────────┴─────────┴─────────┴─────────┘     │
│ ▸ Content  │  Success rate by action (last 7d)  ▁▃▅▇▆▇█    │
│ ▸ Accounts │  ── Recent activity ─────────────────────────  │
│            │  12:04  slot-07  IG   post     ✓ posted        │
│ ⚙ Settings │  12:03  slot-02  TT   warm     ✓ 10m           │
│            │  12:01  slot-11  IG   comment  ✗ captcha       │
└────────────┴──────────────────────────────────────────────┘
```

### Pages
1. **Overview** — stat cards (runs today, success %, devices online, accounts by status),
   a 7-day success-rate sparkline/bar, and a live recent-activity feed.
2. **Devices** — grid of cards: online dot, label + `laixi_id`, current account, **live badge**
   (Idle / Running: <action> / Failed), today's run count + success %. Click → device detail
   with its run history and the account(s) it hosts.
3. **Runs** — the core table. Dense, monospace timestamps, filter bar (date · device · platform ·
   action · status). Columns: time, device, account, platform, action, status pill, duration,
   result/error. Click a row → step-by-step trace (`runs.steps`).
4. **Schedule** — recurring automations: name, action, platform, target, cadence, next run,
   enable/disable toggle, edit. "Daily IG warm @ 09:00 ±30m → all warming accounts".
5. **Content** — media/text library: thumbnails, type, platform, duration, used count, upload.
6. **Accounts** — health table: platform, username, device, status pill
   (active/warming/quarantined/banned), followers, last action. Filter by status.

The local and online dashboards are the **same app** pointed at different API bases; local
adds a "live" tint and works offline.

---

## 10. Deployment

**Farm machine (China):** Python + ffmpeg + Laixi (API on) + clone of the runner. Run
`uvicorn runner:app` (serves local dashboard on `:8000`, starts scheduler + workers). Set the
backend URL + host token in a `.env`.

**Online:** deploy backend (FastAPI + Postgres) to your host of choice; deploy the dashboard
build as static files; point it at the backend. Choose a region with the best China latency
(test from the farm machine).

---

## 11. Build roadmap (incremental — useful at each step)

1. **Port automation to Python** action handlers (`post`, then `warm`, `like`, `comment`). *Unlocks everything.*
2. **Local runner**: FastAPI + SQLite `runs` log + APScheduler + worker pool. Local dashboard reads SQLite.
3. **Schema + online backend**: Postgres + FastAPI ingest (`/api/runs/sync`) + read APIs.
4. **Sync worker** in the runner (local-first → online, retry-tolerant).
5. **Online dashboard** (the dark SPA) over the backend.
6. **Scheduling + content library + account health**; then **multi-host** (repeat the runner per machine).

Don't big-bang it — each step is independently useful, and you always have a working system.
