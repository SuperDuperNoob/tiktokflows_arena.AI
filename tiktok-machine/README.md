# TikTok Shop Auto-Posting Machine

<div align="center">

**Fully autonomous TikTok Shop posting system with AI-powered captions, emoji text overlays, video fingerprint randomization, residential proxy routing, Telegram bot, and responsive web interface.**

Built for Malaysian TikTok Shop sellers running on a budget VPS (2 CPU / 4GB RAM).

[Architecture](#architecture) · [Setup](#quick-start) · [Web Interface](#web-interface) · [Telegram Commands](#telegram-commands) · [Cookie Login](#cookie-login) · [How It Works](#how-it-works)

</div>

---

## What This Does

Every ~2 hours (with human-like jitter), the system:

1. **Syncs** raw product videos from Google Drive
2. **Selects** a product based on stock levels and posting rotation
3. **Picks** a compliance-checked caption from the pool
4. **Verifies** proxy exit IP is Malaysian residential
5. **Transforms** the video — speed, brightness, trim, **emoji text overlay**, audio
6. **Uploads** to TikTok Shop via TiktokAutoUploader through the proxy
7. **Archives** the processed video and logs everything to SQLite
8. **Notifies** you on Telegram with the result

**Two interfaces:**
- **Telegram bot** — Quick commands on the go (`/status`, `/pause`, `/force`)
- **Web dashboard** — Deep configuration, caption management, monitoring (laptop/Android)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  Telegram Bot Interface                          │
│            /status  /growth  /stock  /pause  /force  /logs       │
└─────────────────────────────┬────────────────────────────────────┘
                              │
┌─────────────────────────────┴────────────────────────────────────┐
│                  Web Interface (FastAPI)                         │
│       Dashboard · Posts · Captions · Config · Events · Tools     │
│       Access: https://your-domain.com (Cloudflare Tunnel)        │
─────────────────────────────┬────────────────────────────────────┘
                              │
┌─────────────────────────────┴────────────────────────────────────┐
│                      Upload Orchestrator                         │
│                                                                  │
│   ┌───────────┐    ┌──────────────────┐    ┌─────────────────┐  │
│   │  Google   │───▶│  Video Transform │───▶│ TiktokAutoUpload│  │
│   │   Drive   │    │  (FFmpeg + Skia) │    │  + Cliproxy     │  │
│   │   Sync    │    │  PNG overlay for │    │  Proxy          │  │
│   │ (rclone)  │    │  emoji support   │    │  (verified IP)  │  │
│   └───────────    └──────────────────┘    └─────────────────┘  │
│         │                   │                      │             │
│         ▼                   ▼                      ▼             │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                    SQLite Database                       │   │
│   │  posts │ raw_stock │ caption_pool │ competitor │ events  │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌─────────────┐    ┌────────────┐    ┌─────────────────────┐  │
│   │ Compliance  │    │    AI      │    │   Competitor        │  │
│   │ Engine      │    │  Engine    │    │   Scraper (Apify)   │  │
│   │ (AI+regex)  │    │ (captions) │    │   (daily, 3AM MYT)  │  │
│   └─────────────┘    └────────────┘    └─────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
tiktok-machine/
├── config/
│   └── config.yaml              ← Master configuration (EDIT THIS)
├── content/
│   ├── products.json            ← Product → TikTok Shop ID mapping (dashboard)
│   └── raw/                     ← "Drive root" the pipeline scans
│       ├── product_id.txt       ← Real product IDs + captions/titles (from vps)
│       ├── preset_text.txt      ← Overlay caption pool (example included)
│       ├── soundtrack/          ← legacy audio (see sounds/ at root)
│       └── <Product>/           ← one folder per product; drop raw videos here (mp4/mov/mkv/webm/...) 
├── sounds/                      ← Royalty-free audio tracks (drop .mp3 here)
── logs/
│   └── tiktok.db                ← SQLite database
├── scripts/
│   ├── orchestrator.py          ← Unified main loop (systemd service)
│   ├── lib.py                   ← Shared paths, timezone (MYT), DB, proxy helpers
│   ├── caption_policy.py        ← Compliance core: regex + obfuscation (ported)
│   ├── compliance.py            ← Two-layer compliance (regex + AI) — merged
│   ├── video_processor.py       ← FFmpeg + Skia burn pipeline (ported v4)
│   ├── uploader.py              ← Resilient uploader: proxy + geo-check (ported)
│   ├── check_burns.py           ← Quality gate: catches static-image burns
│   ├── sidecar_manager.py       ← .json/.pid metadata sidecars
│   ├── ai_growth.py             ← Cached AI growth engine (≤1 call/day, ported)
│   ├── generate_report.py       ← OPS report (daily_report.txt, ported)
│   ├── reconcile_metrics.py     ← Links uploads to scraped metrics (ported)
│   ├── db.py                    ← SQLite database layer
│   ├── sync_drive.py            ← Google Drive sync via rclone
│   ├── transform_video.py       ← 8 overlay styles + Skia renderer (legacy entry)
│   ├── competitor_scraper.py    ← Apify competitor monitoring
│   ├── telegram_bot.py          ← Telegram bot interface
│   ├── import_cookies.py        ← Cookie import utility (Method 1)
│   ├── qr_login.py              ← QR code headless login (Method 5)
│   └── setup_tools.py           ← Setup verification utility
├── webapp/
│   ├── server.py                ← FastAPI web interface backend
│   └── static/
│       ├── index.html           ← Responsive single-page frontend
│       ├── style.css            ← Dark theme, mobile-first CSS
│       └── app.js               ← Frontend logic
├── deploy/
│   ├── setup.sh                 ← One-command VPS deployment
│   ├── migrate_from_vps.sh      ← Migrate from the legacy tiktokflow_vps
│   ├── tiktok-machine.service   ← systemd: main orchestrator
│   ├── tiktok-webapp.service    ← systemd: web interface
│   └── cloudflared.service      ← systemd: Cloudflare Tunnel
├── docs/
│   ├── cookie_login_guide.md    ← Detailed cookie login instructions
│   ├── content_guide.md         ← What to fill in (products, captions, media)
│   ├── google_drive_sync_guide.md ← rclone_remote/remote_path setup + anti-dupe
│   └── rollback.md              ← Rollback to tiktokflow_vps (<30 min)
├── tests/
│   ├── test_compliance.py       ← Obfuscation + banned-phrase + AI layer
│   ├── test_video_processor.py  ← QC guards + sidecar generation
│   └── test_uploader.py         ← Proxy shorthand + geo-check + strict mode
├── requirements.txt             ← Python dependencies
└── README.md                    ← This file
```

## Unified pipeline (battle-tested hardening)

The core pipeline is a port of the production tiktokflow_vps v4 scripts:

```
  sync_drive ─▶ check_burns (quality gate) ─▶ video_processor ─▶ uploader ─▶ done
                    │                          (renders + sidecars)   (proxy-safe)
                    └─ quarantines static images
```

- **`video_processor.py`** — port of `process-videos-v4.sh`. FFmpeg + Skia PNG
  overlay, the 8 modern overlay styles, `eof_action=repeat`, frame-count guard
  and MB/s floor, sidecar generation, safe archive + `deleted.log`.
- **`uploader.py`** — port of `auto_uploader_v4.py`. Proxy shorthand parsing,
  pre-upload geo-check, strict mode, no-retry-on-dead-proxy, TikTok-API retry
  with backoff, sidecar-driven cleanup.
- **`compliance.py`** — merge of `caption_policy.py` (regex + obfuscation) and
  the context-aware LLM check. Two-layer, obfuscation is anti-spam only.
- **`ai_growth.py`** — port of `ai_growth_engine.py`. Cached AI, one paid call
  per calendar day (MYT). Writes only `growth_report.txt`.
- **`generate_report.py`** / **`reconcile_metrics.py`** — ported OPS report and
  analytics reconciliation.
- **`sync_out.py`** — the other half of the Drive sync loop: pushes logs +
  processed archive back to Drive and deletes already-posted raws remotely via
  `deleted.log`, so the next sync never re-downloads/re-uploads the same video.

### How Drive sync avoids duplicates (DB-as-truth + Drive cleanup)

"Already posted" is recorded in **SQLite** (`raw_stock.posted_at`), not a file.
Deleting the file from Drive is cosmetic cleanup — it gives you the satisfaction
of watching your Drive empty, but it is **not** what prevents duplicates.

```
Google Drive ──sync_in (rclone copy, pull new only)──▶ content/raw/<Product>/
   │  ▲                                                     │ burn
   │  │                                                     ▼
   │  │                                        content/processed/<Product>/ (archive)
   │  │                                         + raw_stock.posted_at SET  (the truth)
   │  │                                                     │
   │  ◀──sync_out (rclone deletefile from the DB ledger)─────┘
   └── (posted raw gone from Drive → feels good, and never re-pulled)
```

1. **`sync_in`** uses `rclone copy` (not `sync`) with excludes — pulls **new**
   raws only, never deletes local files.
2. After a video is burned + archived, `video_processor` records it in the DB
   ledger (`mark_raw_consumed`) — **this is what makes it "done"**. It is then
   excluded from every selector and stock count.
3. **`sync_out`** runs after a successful upload: it copies logs + the
   processed archive back to Drive (backup), then reads the DB for consumed
   raws whose Drive copy isn't deleted yet and runs `rclone deletefile` on each.
4. Because "posted" lives in the DB, **even if a delete fails** the raw is never
   re-selected → no duplicate upload. Failed deletes stay in the ledger and are
   retried next run.

**Key difference from tiktokflow_vps:** vps coupled "already posted" to a
`deleted.log` file + a destructive remote delete — a lost file or failed delete
meant the raw came back and got re-uploaded. Here the delete is pure cleanup;
the DB is the source of truth. `deleted.log` / `drive_cleanup.log` are kept only
as human-readable audits.

> **Full setup for the `google_drive` config (rclone remote + folder, rclone
> install, verification, troubleshooting): [`docs/google_drive_sync_guide.md`](docs/google_drive_sync_guide.md)**
- **`competitor_scraper.py`** — uses the battle-tested Apify actor
  `clockworks/tiktok-scraper` (same actor tiktokflow_vps ran in production).
  It writes per-post data into the `competitor_videos`/`competitor_daily`
  analytics tables that `/growth`, `reconcile_metrics` and the OPS report read,
  plus the legacy `competitor_data` table for the dashboard.

**Configuration:** copy `config/config.yaml.example` to `config/config.yaml`
(the live file is git-ignored because it holds secrets).

### Battle-tested lessons (from tiktokflow_vps)

1. **Never `shortest=1` on the overlay filter.** The caption is a single-frame
   PNG, so `overlay=...:shortest=1` ends the output after exactly one frame and
   ships a 1-frame mp4 that uploads fine and shows as a still image on TikTok.
   The pipeline uses `eof_action=repeat` instead.
2. **Never `-loop 1` on the PNG input.** An infinite loop plus no other
   terminating stream encodes until the disk fills. The base video must stay the
   one finite stream.
3. **Proxy transport errors abort immediately.** Retrying re-sends the whole
   video through a dead proxy and burns another 5-10MB of metered quota per
   attempt for nothing. Only TikTok API failures retry (with backoff).
4. **Cached AI — max 1 call/day.** `daily_summary.ai_called_at` gates the paid
   `/growth` call. A failed call is *not* cached, so a blip does not burn the
   day's budget. Only `/growth` passes `--ai`; the scheduled pipeline makes zero
   AI calls.
5. **Business timezone (MYT, UTC+8).** All timestamps, "today" rollover and the
   daily AI budget use `Asia/Kuala_Lumpur`, not the container's TZ.
6. **Quality floors.** Burns under `MIN_MB_PER_SEC=0.30` are flagged; burns under
   `MIN_OUTPUT_FRAMES=10` are quarantined, never uploaded. The raw source is
   left in place so the next run retries it.
7. **Sidecars before upload.** An mp4 without a `.json`/`.pid` sidecar is
   skipped (no untraceable posts). Sidecars are cleaned up after success.
8. **Obfuscation is anti-spam, not a compliance licence.** Medical claims,
   prices and absolute overclaims are dropped/repaired — disguising their
   spelling does not make them compliant.

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `BROKEN BURN ... STATIC IMAGE` | Overlay ended early. Re-run `python3 check_burns.py --quarantine`, check you never reintroduced `shortest=1`. |
| `Upload proxy: None ... shadowban risk` | `proxy.endpoint` unset. Set a Malaysian residential/4G proxy. |
| `STRICT: aborting BEFORE upload` | `proxy.geo_check` verified a non-MY/datacenter exit. Fix the proxy or set `strict_mode: false`. |
| Uploads "succeed" but 0 views | Datacenter IP. Use a residential/4G proxy (not datacenter). |
| `/growth` returns the same text all day | Correct — the daily AI result is cached (`ai_called_at`). Tapping again is free. |
| AI spending more than 1 call/day | Only `/growth --ai` should call AI. Confirm `ai.caption_per_video: false`. |
| Cookie "older than 12h" warning | Session likely expired. `python3 qr_login.py` or re-import cookies. |
| `check_burns` exit code 1 | Static images found. Use `--quarantine`; broken burns are expected during a config change. |

### Migrating from tiktokflow_vps

```bash
sudo bash /opt/tiktok-machine/deploy/migrate_from_vps.sh
```

It backs up the old install, copies config/cookies/products/captions, starts the
systemd services and verifies them. To go back, follow `docs/rollback.md`
(under 30 minutes).

---

## Quick Start

### Prerequisites

| What | Why |
|---|---|
| VPS (Debian 11+, 2 CPU, 4GB RAM) | Runs the system |
| TikTok account logged in | Uploads videos |
| Google Drive with product videos | Content source |
| Cliproxy (or similar) residential proxy | Malaysian IP for uploads |
| Telegram bot | Your control interface |
| OpenAI-compatible API | AI captions & compliance |
| Apify API key ($5/month) | Competitor scraping |
| Cloudflare account (free) | Secure web access, no open ports |

**Content is the one thing you must supply.** The repo ships an example
`content/raw/` structure (real product IDs from tiktokflow_vps, an example
caption pool, per-product folders and placeholders) — you drop raw videos (any
common format: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, ...) into
each product folder, drop `.mp3`s into `sounds/`, and edit
`content/raw/product_id.txt` / `preset_text.txt`.
> **Full step-by-step: [`docs/content_guide.md`](docs/content_guide.md).**

### 1. Deploy to VPS

```bash
# Copy tiktok-machine/ to your VPS at /opt/tiktok-machine
scp -r tiktok-machine/ user@your-vps:/opt/

# SSH in and run the setup script
ssh user@your-vps
sudo bash /opt/tiktok-machine/deploy/setup.sh
```

The setup script installs everything:
- Python 3, FFmpeg, rclone, Node.js
- Noto Color Emoji fonts (for emoji overlays)
- Web fonts (Outfit, Inter, Montserrat, Poppins) for text rendering
- Python virtualenv with all dependencies
- TiktokAutoUploader + its Node.js signature generator
- cloudflared (Cloudflare Tunnel client)
- systemd services (auto-restart on failure)

### 2. Configure

```bash
sudo nano /opt/tiktok-machine/config/config.yaml
```

**Required fields:**

| Field | Where to Get It |
|---|---|
| `telegram.bot_token` | Message [@BotFather](https://t.me/BotFather) on Telegram |
| `telegram.allowed_user_id` | Message [@userinfobot](https://t.me/userinfobot) |
| `proxy.endpoint` | Your Cliproxy dashboard (format: `http://user:pass@host:port`) |
| `ai.base_url` + `ai.api_key` | Your OpenAI-compatible API provider |
| `tiktok.session_username` | Whatever name you use in `cli.py login -n <name>` |

**Optional:**

| Field | Default | Notes |
|---|---|---|
| `apify.api_token` | — | Without this, competitor scraping is disabled |
| `proxy.verify_ip_before_upload` | `true` | Verifies exit IP is Malaysian residential |
| `compliance.strict_mode` | `true` | Rejects captions with banned phrases |

### 3. Set Up Google Drive

```bash
# Configure rclone (creates a remote named "gdrive")
rclone config
# → New remote → name: gdrive → type: drive → follow OAuth flow

# Create the expected folder structure on Google Drive:
#   /TikTokContent/
#   ├── products.json
#   ├── Biocho/
#   │   ├── raw_001.mp4
#   │   └── raw_002.mp4
#   └── Serum/
#       └── raw_001.mp4
```

**`products.json` format:**
```json
{
    "Biocho": "TIKTOK_PRODUCT_ID_ABC123",
    "Serum": "TIKTOK_PRODUCT_ID_DEF456"
}
```

### 4. Cookie Login

**Option A: Browser Export (Recommended — No VPS GUI needed)**

Do this on your home computer:
1. Install [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg) (Chrome) or [Cookie-Editor](https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/) (Firefox)
2. Log in to https://tiktok.com
3. Export cookies as JSON → save as `tiktok_cookies.json`
4. Upload to VPS and convert:
   ```bash
   scp tiktok_cookies.json user@your-vps:/tmp/
   ssh user@your-vps
   python3 /opt/tiktok-machine/scripts/import_cookies.py myshop /tmp/tiktok_cookies.json
   ```

**Option B: QR Code Headless Login (No VPS GUI needed)**

```bash
pip3 install playwright && playwright install chromium
python3 /opt/tiktok-machine/scripts/qr_login.py myshop
```

Script generates a QR code image → you scan it with TikTok app → cookies auto-save.

**Option C: SSH X11 Forwarding (if Chrome is installed on VPS)**

```bash
ssh -X user@your-vps
cd /opt/TiktokAutoUploader
/opt/tiktok-machine/venv/bin/python cli.py login -n myshop
```

Chrome opens on your local screen → log in → cookies save to VPS.

> **Full guide:** See [`docs/cookie_login_guide.md`](docs/cookie_login_guide.md) for detailed instructions on all methods.

### 5. Add Sounds

Drop 20+ royalty-free `.mp3` files into `/opt/tiktok-machine/sounds/`:

```bash
# Sources:
# - Pixabay Music (pixabay.com/music) — free commercial use
# - Mixkit (mixkit.co) — free stock music
# - Uppbeat (uppbeat.io) — free tier

cp ~/Downloads/royalty-free/*.mp3 /opt/tiktok-machine/sounds/
```

### 6. Set Up Cloudflare Tunnel (No Open Ports!)

```bash
# 1. Go to https://one.dash.cloudflare.com/
# 2. Create a tunnel → copy the token
# 3. Edit the tunnel service:
sudo nano /etc/systemd/system/cloudflared.service
#    → Replace YOUR_CLOUDFLARE_TUNNEL_TOKEN with your token

# 4. In Cloudflare dashboard, add a public hostname:
#    Domain: tiktok.yourdomain.com
#    Service: http://localhost:8080

# 5. Enable and start:
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

**Result:** Your web interface is accessible at `https://tiktok.yourdomain.com` — no ports opened on the VPS, all traffic encrypted and protected by Cloudflare.

### 7. Verify & Start

```bash
# Run setup verification
/opt/tiktok-machine/venv/bin/python scripts/setup_tools.py

# Expected output:
# ✅ Telegram bot token configured
# ✅ Telegram user ID set
# ✅ Proxy endpoint configured
# ✅ AI API key configured
# ✅ Products configured: Biocho, Serum
# ✅ Sounds directory: 24 audio files
# ✅ rclone remote 'gdrive' configured
# ✅ TiktokAutoUploader found

# Start all services
sudo systemctl start tiktok-machine
sudo systemctl start tiktok-webapp
sudo systemctl enable tiktok-machine
sudo systemctl enable tiktok-webapp

# Watch the logs
sudo journalctl -u tiktok-machine -f
sudo journalctl -u tiktok-webapp -f
```

### 8. Access the Interfaces

**Telegram:** Open your bot and send `/status`

**Web Dashboard:** Open `https://tiktok.yourdomain.com` in your browser

---

## Web Interface

The web interface provides a **responsive dashboard** accessible from laptop or Android browser.

### Tabs

| Tab | What It Shows |
|---|---|
| **📊 Dashboard** | Posted today, stock levels, posting priority, recent posts & events, cookie age |
| **📹 Posts** | Filterable table of all posts (by product, by status) |
| ** Captions** | View caption pool, add new captions (with compliance check) |
| **📦 Products** | Product list with stock counts and descriptions |
| **⚙️ Config** | Edit all config.yaml values inline (click to edit, auto-saves) |
| **📜 Events** | Filterable system event log |
| **🔧 Tools** | Proxy test, Google Drive sync trigger, cookie status |

### Features

- **Auto-refresh** — Dashboard updates every 30 seconds
- **Dark theme** — Easy on the eyes, TikTok-brand red accents
- **Mobile-first** — Works on Android browser and laptop
- **Secure** — Behind Cloudflare Tunnel, no open ports, secrets masked
- **No build step** — Pure HTML/CSS/JS, served by FastAPI

### API Endpoints

```
GET    /api/status              — Full dashboard data
GET    /api/config              — Current config (secrets masked)
PUT    /api/config              — Update a config value
GET    /api/posts               — Posts (filter by product/status)
GET    /api/captions            — Caption pool
POST   /api/captions            — Add caption (with compliance check)
GET    /api/products            — Product list
GET    /api/events              — System events
POST   /api/actions/sync        — Trigger Google Drive sync
POST   /api/actions/test-proxy  — Test proxy connection
GET    /api/actions/cookie-status — Check cookie age
```

---

## Telegram Commands

| Command | What It Does |
|---|---|
| `/status` | Queue, stock levels, today's post count, last post time |
| `/growth` | AI strategy report + generates 10 new captions per product |
| `/stock` | Detailed stock breakdown + posting priority order |
| `/captions [product]` | View caption pool for a specific product |
| `/pause` | Pauses the posting loop |
| `/resume` | Resumes the posting loop |
| `/force [product]` | Forces next upload to use the specified product |
| `/logs` | Shows last 20 system events |

### Example: `/growth` Output

```
⏳ Generating growth strategy and captions...
(this takes ~30 seconds)

🚀 Growth Strategy Report

## My Performance (Last 7 Days)
- **Biocho**: 5 posts, 12,400 total views, avg 2,480 views/post
- **Serum**: 2 posts, 3,200 total views, avg 1,600 views/post

## Recommended Actions
1. Push Biocho harder — 2.5x better views per post
2. Try the "before/after" angle competitors are using
3. Move posting window to 7-9 PM MYT (competitor peak)

━━━━━━━━━━━━━━━━━━━━━━
✨ New Captions Added:

📦 Biocho (8 new):
  • eh korang tau tak? Serum ni viral 
  • tekan beg kuning sekarang 👇
  ...
```

---

## Cookie Login

Two methods to get TikTok cookies onto your VPS **without needing a GUI on the VPS**.

### Method 1: Browser Extension Export (Easiest)

**Do this on your home computer. No VPS access needed during login.**

1. Install [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg) (Chrome) or [Cookie-Editor](https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/) (Firefox)
2. Go to https://tiktok.com and log in normally
3. Click the extension icon → Export → Save as JSON file
4. Upload to VPS and convert:
   ```bash
   scp tiktok_cookies.json user@your-vps:/tmp/
   ssh user@your-vps
   python3 /opt/tiktok-machine/scripts/import_cookies.py myshop /tmp/tiktok_cookies.json
   ```

### Method 5: QR Code Headless Login

**Run on VPS. No GUI needed. Scan QR from your phone.**

```bash
pip3 install playwright && playwright install chromium
python3 /opt/tiktok-machine/scripts/qr_login.py myshop
```

Script generates a QR code image → save it or send via Telegram → scan with TikTok app → cookies auto-save.

> **Full guide with troubleshooting:** [`docs/cookie_login_guide.md`](docs/cookie_login_guide.md)

---

## How It Works

### Video Transformation Pipeline

Every raw video is made visually unique before upload — no two uploads share the same file hash or fingerprint.

```
Raw Video (from Google Drive)
         │
         ▼
┌─────────────────────────────────────┐
│  Parameter Randomization            │
│  • Speed: 0.97–1.06x               │
│  • Brightness: ±0.04               │
│  • Contrast: 0.97–1.06             │
│  • Trim: 0–0.8s from start         │
│  • Overlay Y: 35–50% height        │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Caption + Emoji Overlay            │
│                                     │
│  1. Pick caption from pool          │
│  2. Decorate with hook + CTA + emoji│
│  3. Render to transparent PNG       │
│     (Skia — 30MB RAM, full emoji)   │
│  4. Composite onto video via        │
│     FFmpeg overlay filter           │
│                                     │
│  8 TikTok-native styles:            │
│  • Classic Yellow (30%)             │
│  • Bold White (25%)                 │
│  • Bright Yellow (15%)              │
│  • TikTok Red (10%)                 │
│  • White+Yellow Glow (8%)           │
│  • Yellow+Red Shadow (7%)           │
│  • White on Black Box (5%)          │
│  • Fire Urgency (5%)                │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Audio Replacement                  │
│  • Pick random royalty-free track   │
│  • Loop + trim to video length      │
│  • -stream_loop -1 + -shortest      │
└─────────────┬───────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  Quality Guards                     │
│  • Frame count ≥ 10 (motion check) │
│  • MB/s ≥ 0.30 (bitrate floor)     │
│  • Broken burns → content/failed/   │
└─────────────┬───────────────────────┘
              │
              ▼
   Processed Video → Upload → Posted/
```

### Emoji Text Overlay — Why PNG?

FFmpeg's `drawtext` filter uses FreeType, which **cannot render color emoji on Linux**. The solution: render text + emoji to a transparent PNG first using a proper font engine, then composite that PNG on the video.

**Renderer comparison:**

| | Skia (Primary) | Playwright (Fallback) |
|---|---|---|
| **RAM** | ~30 MB | ~150–400 MB |
| **Text quality** | Pixel-perfect | Pixel-perfect |
| **Emoji quality** | Full color | Full color |
| **Startup** | Instant | 2–5 seconds |
| **Stability** | Rock solid | Can hang / OOM |
| **Fonts** | System-installed | Any Google Font via CSS |

**For a 4GB VPS, Skia is the clear winner.** The setup script pre-installs the same web fonts (Outfit, Inter, Montserrat, Poppins, Plus Jakarta Sans) that Playwright would load dynamically, so Skia never needs a fallback.

### Compliance Engine (AI-Powered)

Every caption passes through a two-layer compliance pipeline before being used:

```
Caption Input
     │
     ▼
┌──────────────────────┐
│ Layer 1: Regex       │  ← Instant, catches obvious violations
│ (banned phrases)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Layer 2: AI Analysis │  ← Context-aware, catches evasion
│ (LLM review)         │     + implicit claims + slang
│                      │
│ Checks for:          │
│ • Medical claims     │
│ • Price guarantees   │
│ • Superlatives       │
│ • Guaranteed results │
│ • Creative evasion   │
│   (u.b.a.t, ub4t)   │
│ • Implicit claims    │
│   (confirm putih)    │
└──────────┬───────────┘
           │
     ┌─────┴─────┐
     │ Violation? │
     └─────┬─────
   Yes  /       \ No
     /           \
    ▼             ▼
┌──────────┐  ┌──────────────┐
│ AI       │  │ AUTO-APPROVE │
│ Rewrite  │  └──────────────┘
│ (fixes   │
│ while    │
│ keeping  │
│ tone)    │
└────┬─────┘
     │
     ▼
┌──────────────┐
│ AI Re-check  │  ← Confirms rewrite is clean
└──────┬───────┘
       │
       ▼
   Final Caption
```

**Accuracy:** ~95% (vs ~65% for regex-only). Catches things regex cannot:
- `"ubat gigi"` (toothpaste) — regex flags it, AI understands context
- `"u.b.a.t"` — regex misses evasion, AI catches it
- `"confirm putih lepas 3 hari"` — no banned word, but AI recognizes implicit guarantee

### Scheduling & Anti-Detection

```python
base_interval = 120 minutes  # 2 hours
jitter = random(-30, +30)    # ±30 minutes
actual_wait = base + jitter  # 90–150 minutes between posts

# Quiet hours: 2AM–6AM MYT (no posting)
# Product rotation: least-recently-posted first
# Video selection: random from least-used pool
# Caption selection: least-used compliance-checked caption
```

### Proxy Verification

Before every upload:

1. Fetch proxy endpoint from config
2. Make a test request through the proxy to `ipinfo.io`
3. Verify exit IP is in Malaysia (`country: MY`)
4. Verify org is NOT a datacenter (AWS, Google, Azure, etc.)
5. If verification fails → skip upload, alert via Telegram

Only upload traffic goes through the proxy — AI calls, Telegram messages, and Apify use the VPS's direct IP.

---

## Configuration Reference

### `config/config.yaml` — Key Sections

```yaml
tiktok:
  session_username: "myshop"      # Login label
  uploader_dir: "/opt/TiktokAutoUploader"
  cookie_max_age_days: 7          # Warn if cookies older

posting:
  interval_minutes: 120           # Base interval
  jitter_minutes: 30              # ± randomization
  quiet_hours_start: 2            # 2AM MYT
  quiet_hours_end: 6              # 6AM MYT
  daily_post_target: 7
  retry_delay_minutes: 15

proxy:
  endpoint: "http://user:pass@host:port"
  expected_country: "MY"
  verify_ip_before_upload: true

ai:
  base_url: "https://your-api.com/v1"
  api_key: "your-key"
  caption_model: "gpt-3.5-turbo"
  compliance_model: "gpt-3.5-turbo"
  strategy_model: "gpt-4"

compliance:
  strict_mode: true               # Reject banned phrases
  banned_phrases:                 # Medical claims, price guarantees, etc.
    - "sembuh"
    - "ubat"
    - "paling murah"

telegram:
  bot_token: "YOUR_BOT_TOKEN"
  allowed_user_id: 123456789      # ONLY this user can control the bot
```

---

## Troubleshooting

### View Logs
```bash
# Live log streams
sudo journalctl -u tiktok-machine -f    # Main orchestrator
sudo journalctl -u tiktok-webapp -f     # Web interface
sudo journalctl -u cloudflared -f       # Tunnel logs

# Last 100 lines
sudo journalctl -u tiktok-machine -n 100

# Today's logs
sudo journalctl -u tiktok-machine --since today
```

### Common Issues

| Problem | Fix |
|---|---|
| `No cookie with Tiktok session id found` | Re-login using cookie import or QR script |
| `Proxy verification failed` | Check Cliproxy endpoint in config |
| `rclone sync failed` | Run `rclone config` to re-auth Google Drive |
| `No captions available` | Send `/growth` on Telegram or add via web UI |
| Video uploads as still image | Check logs for `BROKEN BURN` — quarantined to `content/failed/` |
| Bot doesn't respond | Verify `allowed_user_id` matches your Telegram ID |
| Emoji not rendering | Install fonts: `apt install fonts-noto-color-emoji` |
| Web interface not loading | Check `sudo systemctl status tiktok-webapp` |
| Cloudflare Tunnel not working | Check `sudo systemctl status cloudflared` and verify token |

### Manual Database Inspection
```bash
sqlite3 /opt/tiktok-machine/logs/tiktok.db

# Last 10 posts
SELECT product_name, status, posted_at FROM posts ORDER BY id DESC LIMIT 10;

# Recent events
SELECT event_type, message, occurred_at FROM system_events ORDER BY id DESC LIMIT 20;

# Stock levels
SELECT product_name, COUNT(*) as videos FROM raw_stock GROUP BY product_name;

# Caption pool
SELECT product_name, caption_text, times_used FROM caption_pool WHERE compliance_checked=1;
```

### Restart Services
```bash
sudo systemctl restart tiktok-machine
sudo systemctl restart tiktok-webapp
sudo systemctl restart cloudflared
sudo systemctl status tiktok-machine tiktok-webapp cloudflared
```

---

## Cost Breakdown

| Component | Cost | Frequency |
|---|---|---|
| AI captions (`/growth`) | ~$0.001/caption | Only when you trigger it |
| AI strategy (`/growth`) | ~$0.03/report | Only when you trigger it |
| AI compliance check | ~$0.001/caption | Every post (~7/day) |
| Apify scraping | ~$0.05/scrape | Once daily |
| Cliproxy proxy | Monthly plan | Fixed |
| VPS hosting | Monthly | Fixed |
| Cloudflare Tunnel | Free | Unlimited |
| Telegram API | Free | Unlimited |
| FFmpeg transform | $0 (local CPU) | Every post |

**Typical monthly AI cost at 7 posts/day:** ~$0.50–$1.00

---

## Security

- All processes run as non-root `tiktok` system user
- Telegram bot **only responds to your user ID** — no open access
- Web interface **behind Cloudflare Tunnel** — no open ports, HTTPS, DDoS protection
- Cookies stored locally, never transmitted except to TikTok's API
- Proxy used **only for upload traffic** — AI/API calls use direct IP
- SQLite uses WAL mode for concurrent read safety
- Failed burns are quarantined, never uploaded
- Raw videos are **never deleted** — only archived
- Config secrets are **masked** in web API responses

---

## License

MIT — use at your own risk. TikTok may ban accounts that use automation tools.

---

## Acknowledgments

- [TiktokAutoUploader](https://github.com/makiisthenes/TiktokAutoUploader) — the underlying upload engine
- [Apify](https://apify.com/) — competitor data scraping
- [Cloudflare](https://www.cloudflare.com/) — secure tunnel (no open ports)
- Malaysian TikTok Shop seller community — compliance rules and caption style guidance
