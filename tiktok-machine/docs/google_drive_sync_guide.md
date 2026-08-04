# Google Drive Sync Guide — setting up `rclone_remote` + `remote_path`

This is the setup guide for the `google_drive:` section of `config/config.yaml`.
It tells the system **where on Google Drive your product video folders live**,
which is required for both sync directions:

- **sync_in** (`scripts/sync_drive.py`) — pulls new raws down to `content/raw/`
- **sync_out** (`scripts/sync_out.py`) — deletes already-posted raws **on Drive**
  so they are never re-downloaded / re-uploaded

If `google_drive` is left empty, nothing is synced from Drive — the pipeline
still works if you drop videos straight into `content/raw/<Product>/` yourself,
but you lose the automatic Drive round-trip.

---

## 1. What the two settings mean

```yaml
google_drive:
  rclone_remote: "gdrive:"      # name of the rclone remote (drive)
  remote_path: "TikTokContent"  # the Drive FOLDER that holds your product folders
```

- **`rclone_remote`** — the name of an rclone remote you configure (see step 2).
  You may write it **with** or **without** the trailing colon (`gdrive:` or
  `gdrive`) — both work, they resolve to the same path.
- **`remote_path`** — the Google Drive folder that **directly contains** your
  product folders (e.g. `Biocho/`, `Teh_v1/`, ...). Use the folder name only,
  **no leading/trailing slash**.

### How it resolves

| `rclone_remote` | `remote_path` | rclone path used |
|---|---|---|
| `gdrive:` | `TikTokContent` | `gdrive:TikTokContent` |
| `gdrive` | `TikTokContent` | `gdrive:TikTokContent` |
| `gdrive:` | *(empty)* | `gdrive:` (Drive root) |

> **Important:** `sync_in` and `sync_out` must point at the **same** folder —
> that is the whole point of the anti-duplicate loop. They now resolve
> identically (a trailing-colon mismatch can no longer split them apart).

---

## 2. Setting up the rclone remote (one time)

Install and configure rclone to talk to the Google Drive account that holds
your product videos:

```bash
# Install rclone
sudo apt-get install -y rclone

# Configure a remote. Answer the prompts:
rclone config
```

When it asks for a **name**, use the same name you put in `rclone_remote`
(here `gdrive`). For provider choose **Google Drive**. For "scope" choose the
one that lets rclone read **and delete** files (needed for sync_out):

- `drive` = full access (recommended so sync_out can delete posted raws)
- `drive.file` = works too if the account owns the files

> If you later change the remote name in rclone, update `rclone_remote` in the
> config to match.

**Verify the remote works:**

```bash
# List the root of your Drive through rclone
rclone lsd gdrive:

# Confirm the folder that holds your products is visible
rclone lsd gdrive:TikTokContent
```

---

## 3. Structure your Drive like `content/raw`

The Drive folder you point `remote_path` at should mirror the local layout:

```
TikTokContent/                    ← remote_path (this is "gdrive:TikTokContent")
├── Biocho/
│   ├── clip_001.mp4
│   └── clip_002.mp4
├── Teh_v1/
│   └── teh_01.MOV
├── Centella/
│   └── ...
└── ...                            (one folder per product, matching product_id.txt)
```

- Folder names must **exactly match** the product folders in
  `content/raw/product_id.txt` (e.g. `Biocho`, `Teh_v1`).
- `sync_in` copies these down to `content/raw/<Product>/`.
- `sync_out` later deletes the already-posted file from `TikTokContent/<Product>/`
  and backs it up under `TikTokContent/processed/<Product>/`.

> Keep archive/log folders (`processed/`, `failed/`, `posted/`, `tmp/`,
> `*.log`) **out** of the folder or they'll be excluded from sync anyway —
> sync_in explicitly excludes them so they are never pulled back down.

---

## 4. Full example config

```yaml
google_drive:
  rclone_remote: "gdrive:"      # matches the rclone remote name (step 2)
  remote_path: "TikTokContent"  # Drive folder holding your product folders
  products_file: "content/products.json"
```

Then test sync **in** (pull):

```bash
# Dry-run first — shows what WOULD be copied, without changing anything
rclone copy gdrive:TikTokContent content/raw \
  --exclude processed/** --exclude failed/** --exclude posted/** \
  --exclude tmp/** --exclude *.lock --exclude burn_log.jsonl \
  --exclude deleted.log --exclude deleted_history.log --dry-run

# Real sync in via the pipeline:
python3 -c "import sys; sys.path.insert(0,'scripts'); from db import Database; from sync_drive import DriveSyncer; print(DriveSyncer({'rclone_remote':'gdrive:','remote_path':'TikTokContent','products_file':'content/products.json','raw_dir':'content/raw'}, Database('logs/tiktok.db')).sync())"
```

And confirm sync **out** resolves to the same folder (the delete target):

```bash
python3 -c "import sys; sys.path.insert(0,'scripts'); from sync_out import SyncOut; print('delete target root:', SyncOut({'google_drive':{'rclone_remote':'gdrive:','remote_path':'TikTokContent'}})._remote_root())"
# Expect:  gdrive:TikTokContent
```

---

## 5. The full anti-duplicate loop (why both settings matter)

```
Google Drive  gdrive:TikTokContent
   │  ▲
   │  │ sync_in  (rclone copy, pull NEW only)
   ▼  │
content/raw/<Product>/  ──burn──▶  content/processed/<Product>/  (archive)
   │                                  + logs/deleted.log  ("Biocho/clip_001.mp4")
   │
   │ sync_out (rclone deletefile via deleted.log)
   └────────  removes gdrive:TikTokContent/Biocho/clip_001.mp4 on Drive
```

1. **sync_in** pulls every raw it hasn't seen (rclone `copy`, never deletes
   locally, excludes archives/logs).
2. After a video is posted, its source is archived to `content/processed/` and
   its relative path is appended to `logs/deleted.log`.
3. **sync_out** reads `deleted.log` and runs
   `rclone deletefile gdrive:TikTokContent/Biocho/clip_001.mp4` — deleting the
   **remote** copy. Successes move to `logs/deleted_history.log`; failures stay
   in `deleted.log` to be retried next run.
4. Because the posted raw no longer exists on Drive, the next sync_in can't pull
   it back → the same video is never uploaded twice.

**Both settings are what make step 3 target the right folder.** If `remote_path`
is wrong (e.g. empty when your files live under `TikTokContent/`), sync_out
would look in the wrong place and never delete anything → the raw would get
re-synced and re-uploaded.

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `rclone not found` | Install rclone: `sudo apt-get install -y rclone` |
| `gdrive::...` in logs | You had a stale config; `rclone_remote` is now stripped of its trailing colon automatically — update any copy of config.yaml. |
| `deletefile` does nothing / "file not found" | `remote_path` doesn't match where the raws actually are. Check `rclone lsd gdrive:TikTokContent`. |
| sync_in pulls nothing | Wrong `remote_path`, or the Drive folder has no product folders, or folders don't match `product_id.txt`. |
| Videos re-uploaded after posting | sync_out isn't deleting them remotely — confirm sync_out ran after upload (see orchestrator logs) and that `deletefile` succeeds. |
| Permission errors deleting | The rclone remote's scope doesn't allow delete (used `drive.readonly`). Reconfigure with `drive` scope. |
