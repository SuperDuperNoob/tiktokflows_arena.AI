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
| Archived-source log | `logs/deleted.log` |
| Upload success log | `logs/success.log` |
| Upload failure log | `logs/failed.log` |
| Burn quality log | `logs/burn_log.jsonl` |
| SQLite DB (ops + analytics) | `logs/tiktok.db` |
| OPS report | `logs/daily_report.txt` |
| Growth report | `logs/growth_report.txt` |
