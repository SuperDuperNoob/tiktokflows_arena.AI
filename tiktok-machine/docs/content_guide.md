# Content Setup Guide — what to fill in and how

This guide walks you through the `content/` directory end to end: what each
file/folder is, what to put in it, and how the pipeline uses it. The example
structure ships in the repo, so you only need to **fill in your real values**
and drop in media.

---

## 1. Folder / file map

```
content/
├── products.json        # (auto-generatable) name -> TikTok Shop product ID
└── raw/
    ├── product_id.txt   # ★ EDIT THIS — folder | product_id | captions | titles
    ├── preset_text.txt  # ★ EDIT THIS — overlay caption pool
    ├── soundtrack/      # legacy (ignore; active audio is in sounds/)
    ├── <Product>/       # ★ DROP RAW VIDEOS HERE (e.g. Biocho/)
    │   └── README.txt   # placeholder — safe to delete
    └── ...
sounds/                  # ★ DROP .mp3 AUDIO HERE (project root)
```

The pipeline reads **`content/raw/`** (configured via
`config.yaml -> content.raw_dir`). Do not rename it without updating config.

---

## 2. `content/raw/product_id.txt` — product mapping ★ REQUIRED

This is the single source of truth for which TikTok Shop product each folder
posts to. **It already contains the real product IDs from tiktokflow_vps** — you
only edit it if your shop/IDs/copy change.

**Format (one product per line):**
```
folder_name | PRODUCT_ID | caption1 / caption2 / caption3 | title1 / title2 / title3
```

- **folder_name** — must EXACTLY match the subfolder name in `content/raw/`.
- **PRODUCT_ID** — the numeric TikTok Shop product ID for that item.
- **captions** — the "anchor" captions shown in the TikTok Shop product tag;
  the burner rotates through them. Separate variants with `/`.
- **titles** — the on-video title variants; the burner picks one. Separate with `/`.

Real example from the repo:
```
Biocho | 1729426735260010630 | minyak zaitun rambut / rambut agak lebat / rambut sihat mungkin | Minyak Biocho / Rambut Zaitun / Grab sini
```

**Rules (from production):**
- Keep every caption phrase **≤ 3 words** — TikTok truncates the product anchor
  keyword at ~21 chars.
- No medical claims, no ringgit prices, no "paling murah/terbaik/no.1" — use soft
  hedges (`agak`, `mungkin`, `sedikit`). The compliance layer will reject bad
  ones at burn time, so keep them clean to avoid re-renders.
- Lines starting with `//` are comments (kept from vps) — leave them.

To add a brand-new product:
1. Create the folder: `mkdir content/raw/MyProduct`
2. Add a line: `MyProduct | <ID> | caption / caption | title / title`
3. Drop raw videos into `content/raw/MyProduct/`
4. Optionally regenerate `products.json` (see step 6).

---

## 3. `content/raw/preset_text.txt` — overlay caption pool ★ REQUIRED

This pool feeds the on-video text overlay. The burner picks one line, then
randomizes hook / CTA / emoji / structure so repeats don't look duplicated.

**Format:** one caption per block, blocks separated by a line containing only `---`:

```
Penat aku kejar disqoun
semalam rupanya harini
lagi murrazz 😭😭
---
hasil scroll harini, sekali nampak
hrga terus 😭 ...
---
```

The repo ships a small **example pool** (real vps captions). You can:
- **Add your own** — append new blocks. `/growth` also auto-appends fresh
  captions here (capped at 150 entries).
- The compliance layer softens hype words automatically, so you can write plain
  `murah`/`harga` and it gets obfuscated to `mughrahh`/`hrga` at burn time.

> Keep each caption to **1–2 short lines (≤70 chars)** — the overlay is burned
> into pixels and long text covers the product.

---

## 4. `content/raw/<Product>/` — raw videos ★ REQUIRED

Drop your source clips here. Per product, one folder.

- Accepted: `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`
- Size range the pipeline accepts: **1MB – 500MB**
- The processor burns ONE video per run from one selected product folder, then
  archives the source to `content/processed/<Product>/`.
- **Never delete** raw videos yourself — the pipeline archives them safely and
  logs to `logs/deleted.log`. Broken burns are quarantined to `content/failed/`
  and the source is retried next run.
- To **pause a single product**: create an empty file named `stop_post` inside
  its folder.

---

## 5. `sounds/` — audio tracks ★ REQUIRED (for overlay burns)

Drop royalty-free `.mp3` tracks here (project root, `sounds/`). The burner
attaches one random track per video and **skips the burn if the folder is
empty** (it refuses to render silent clips). A handful of tracks is enough;
rotate them with the video.

Example: `sounds/sound_1.mp3`, `sounds/sound_2.mp3`, ...

---

## 6. `content/products.json` — web dashboard list

The web dashboard's **Products** tab reads this. It's a simple
`{ "ProductName": "product_id" }` map. Regenerate it from `product_id.txt`:

```bash
python3 - <<'PY'
import json
out = {}
for line in open("content/raw/product_id.txt", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("//") or "|" not in line:
        continue
    p = [x.strip() for x in line.split("|")]
    if len(p) >= 2:
        out[p[0]] = p[1]
open("content/products.json", "w", encoding="utf-8").write(
    json.dumps(out, ensure_ascii=False, indent=2) + "\n")
PY
```

---

## 7. First-run checklist

- [ ] `content/raw/product_id.txt` present (yes — ships with real IDs)
- [ ] `content/raw/preset_text.txt` present (yes — example pool)
- [ ] At least one `content/raw/<Product>/` folder has a `.mp4` in it
- [ ] `sounds/` has at least one `.mp3`
- [ ] `config.yaml` → `apify.token`, `telegram.bot_token/chat_id`, `proxy.endpoint`,
      `ai.api_key` set (copy `config/config.yaml.example` to `config/config.yaml`)
- [ ] TikTok cookies present (run `python3 scripts/qr_login.py` or import cookies)

### Smoke test (no upload, no AI spend)

```bash
python3 scripts/video_processor.py --dry-run   # plans one burn
python3 scripts/generate_report.py             # writes logs/daily_report.txt
python3 scripts/check_burns.py --quarantine    # quality gate (0 bad = exit 0)
```

---

## 9. How Drive sync avoids uploading the same video twice

`content/raw/` is fed from Google Drive. The pipeline is careful never to
re-download or re-upload a clip:

1. **sync in** (`sync_drive.py`) — `rclone copy` pulls **new** raws only, with
   excludes for `processed/**`, `failed/**`, `posted/**`, `tmp/**` and log
   files. It never deletes local files.
2. **burn + post** (`video_processor.py` → `uploader.py`) — after a successful
   burn the raw source is moved to `content/processed/<Product>/` and its path
   is appended to `logs/deleted.log`, e.g. `Biocho/foo.mp4`.
3. **sync out** (`sync_out.py`) — runs right after a successful upload:
   - copies `success.log` / `failed.log` / `burn_log.jsonl` / reports back to
     Drive (small files),
   - copies the `content/processed/` archive up to `Drive/processed/` (backup),
   - reads `deleted.log` and runs `rclone deletefile` on each **remote** raw
     (`gdrive:TikTokContent/Biocho/foo.mp4`). Successes go to
     `logs/deleted_history.log`; failures are kept to retry next run.
4. Next sync-in sees the posted raw is **gone from Drive**, so it is never
   pulled back down and never uploaded again.

> If you ever reset the local `content/` folder, the mapping in `products.json`
> and `product_id.txt` is unaffected — those are source-of-truth files kept in
> the repo. Only `deleted.log` and `deleted_history.log` track what has already
> been posted remotely.
>
> **To set up the `google_drive` config (rclone remote + folder) so sync_in and
> sync_out know where your product folders live on Drive, see
> [`docs/google_drive_sync_guide.md`](google_drive_sync_guide.md).**

When those pass, start the orchestrator:

```bash
python3 scripts/orchestrator.py                # or via systemd
```

---

## 8. Where things land after a run

| Item | Location |
|---|---|
| Rendered (queued) video | `content/processed/*.mp4` |
| Sidecars (`.json` / `.pid`) | next to the rendered mp4 |
| Archived source | `content/processed/<Product>/` |
| Quarantined broken burns | `content/failed/` |
| Archived-source log | `logs/deleted.log` (processed, then archived) |
| Deleted-remote history | `logs/deleted_history.log` |
| Upload success log | `logs/success.log` |
| Upload failure log | `logs/failed.log` |
| Burn quality log | `logs/burn_log.jsonl` |
| SQLite DB (ops + analytics) | `logs/tiktok.db` |
| OPS report | `logs/daily_report.txt` |
| Growth report | `logs/growth_report.txt` |
