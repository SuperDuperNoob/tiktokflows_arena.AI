# Content directory

Everything the pipeline reads to make and post videos. It mirrors the
battle-tested `tiktokflow_vps/tiktokflow_drive` layout:

```
content/
├── products.json        # name -> TikTok Shop product ID (web dashboard reads this)
└── raw/                 # <-- the "drive root" the pipeline scans
    ├── product_id.txt   # folder -> product_id -> captions -> titles  (REAL IDs)
    ├── preset_text.txt  # overlay caption pool (one per line, split by ---)
    ├── soundtrack/      # legacy audio folder (see sounds/ at project root)
    ├── Biocho/          # one folder PER PRODUCT — drop raw .mp4 clips here
    │   └── README.txt   # placeholder explaining the folder
    ├── Centella/
    └── ...              # 13 product folders (matches product_id.txt)
```

## What each file is for

| Path | Purpose | Source |
|---|---|---|
| `raw/product_id.txt` | Maps each product folder to its real TikTok Shop product ID, plus the anchor caption / title pools | **real IDs copied from tiktokflow_vps** |
| `raw/preset_text.txt` | Malay overlay captions; the video burner picks one and randomizes it | example pool — expand it |
| `raw/<Product>/` | Raw source clips for that product | **you drop `.mp4` files in here** |
| `products.json` | Web dashboard product list (name → product ID) | generated from `product_id.txt` |
| `sounds/` (project root) | Royalty-free `.mp3` audio tracks | **you drop `.mp3` files in here** |

## How the pipeline consumes this

1. `video_processor.py` reads `raw/product_id.txt` (folder, ID, captions, titles)
   and `raw/preset_text.txt` (overlay caption pool).
2. It scans every subfolder of `raw/` for video files (`1MB–500MB`, extensions
   `.mp4/.mov/.mkv/.avi/.webm`), picks one product by weighted stock ×
   performance rotation, and picks one video in that folder.
3. It burns the overlay, writes sidecars into `content/processed/`, archives
   the source to `content/processed/<Product>/`, and logs the filename to
   `logs/deleted.log`.
4. `uploader.py` posts the rendered clip with the product ID + caption.

## What YOU must fill in

- [ ] **Raw videos** — drop `.mp4` clips into each `raw/<Product>/` folder.
- [ ] **Audio** — drop a few `.mp3` files into `sounds/`.
- [ ] **Captions** — expand `raw/preset_text.txt` (or let `/growth` top it up).
- [ ] **Product IDs / captions / titles** — edit `raw/product_id.txt` if your
      shop IDs or wording differ from the examples.

> Note: `raw/product_id.txt` already contains the **real product IDs** carried
> over from tiktokflow_vps. Keep the format exactly
> `folder | id | caption / caption | title / title`.
>
> To pause one product without stopping the whole run, create an empty
> `stop_post` file inside its folder.

Full walk-through: see **`docs/content_guide.md`**.
