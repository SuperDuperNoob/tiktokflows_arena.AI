"""Video processing service."""

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import subprocess
import shutil

from services.repositories import StockRepository
from services.models import VideoAsset, VideoQuality
from services.infrastructure.ffmpeg_adapter import FFmpegAdapter
from services.infrastructure.skia_adapter import SkiaAdapter
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import lib
import json
import random
import hashlib
import time
import sqlite3
import shutil
from datetime import datetime
from caption_policy import (is_too_long, scan_caption, shorten, soften, soften_claims)
from sidecar_manager import SidecarManager
from transform_video import TIKTOK_STYLES, TextRenderer, pick_style

logger = logging.getLogger(__name__)


class VideoService:
    """Service for video processing and transformation."""

    def __init__(self):
        self.stock_repo = StockRepository()
        self.ffmpeg = FFmpegAdapter()
        self.skia = SkiaAdapter()

    def process_video(self, raw_video_path: Path, product_name: str,
                      caption: str, audio_mode: str = "mix") -> Dict[str, Any]:
        """Process a raw video: transform, add overlay, add audio."""
        # This would integrate with the FFmpeg and Skia adapters
        return {
            "processed_path": "",
            "transform_params": {},
        }

    def select_video(self, product_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Select the next video to process."""
        return None

    def validate_video(self, video_path: Path) -> VideoQuality:
        """Validate video quality."""
        return VideoQuality.UNKNOWN

    def frame_count(self, path: Path) -> int:
        """Get frame count of a video file."""
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-count_packets", "-show_entries", "stream=nb_read_packets",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
        except Exception:
            return 0

    def duration(self, path: Path) -> float:
        """Get duration of a video file."""
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0.0
        except Exception:
            return 0.0

    def quality_gate(self, folder: Path, quarantine: bool = True) -> Tuple[int, int]:
        """
        Scan the upload queue for static-image burns.
        
        Args:
            folder: Directory to scan
            quarantine: If True, move bad files to failed/ directory
            
        Returns:
            Tuple of (total_clips, bad_clips)
        """
        if not folder.exists():
            return 0, 0
        
        clips = sorted(
            f for ext in lib.VIDEO_EXTS
            for f in folder.glob(f"*{ext}"))
        
        if not clips:
            return 0, 0

        bad = 0
        quarantine_dir = lib.failed_dir()
        
        for clip in clips:
            n = self.frame_count(clip)
            d = self.duration(clip)
            if n and n < lib.MIN_OUTPUT_FRAMES:
                bad += 1
                if quarantine:
                    try:
                        quarantine_dir.mkdir(parents=True, exist_ok=True)
                        dest = quarantine_dir / clip.name
                        shutil.move(str(clip), str(dest))
                        for ext in (".json", ".pid", ".txt"):
                            side = clip.with_suffix(ext)
                            if side.exists():
                                shutil.move(str(side), str(quarantine_dir / side.name))
                    except OSError:
                        pass
        return len(clips), bad

    def audit_burn_log(self) -> int:
        """Audit burn_log.jsonl for suspicious entries."""
        path = lib.burn_jsonl()
        if not path.exists():
            return 0
        
        suspicious = 0
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if "frames" in e:
                    if e["frames"] and e["frames"] < lib.MIN_OUTPUT_FRAMES:
                        suspicious += 1
                else:
                    d = e.get("duration_s") or 0
                    if 0 < d < 1.5:
                        suspicious += 1
        except OSError:
            return 0
        
        return suspicious

    # --- Malay market randomisation palette -------------------------------------
    CTA_POOL = [
        "tekan beg kuning bawah 🛒",
        "beg kuning ada di bawah ya",
        "checkout sekarang sebelum habis!",
        "stok terhad, cepat grab!",
        "tekan beg kuning sekarang 👇",
        "jangan tunggu lagi, stok tinggal sikit",
        "link di beg kuning, terus checkout",
        "promosi hari ni je, esok harga naik",
        "dah ramai borong, tinggal sikit je lagi",
        "tap beg kuning untuk dapatkan diskaun",
    ]

    HOOK_POOL = [
        "korang pernah rasa...",
        "eh korang tau tak?",
        "tiba-tiba viral sebab...",
        "aku baru perasan...",
        "penyesalan terbesar...",
        "lepas pakai ni baru faham...",
        "jujur cakap...",
        "kenapa takde orang bagitau awal?",
        "ini yang aku cari selama ni!",
        "serius tak tipu...",
    ]

    BENEFIT_CONNECTORS = ["sebab", "yang buat", "memang", "terus rasa", "auto jadi"]

    EMOJI_POOL = ["😭", "🥰", "🔥", "💛", "🤲", "🛒", "👇", "✨", "💔", "🥹"]

    def _encode(self) -> dict:
        return {
            "crf": str(lib.cfg("encoding", "crf", default=23)),
            "maxrate": str(lib.cfg("encoding", "maxrate", default="5M")),
            "bufsize": str(lib.cfg("encoding", "bufsize", default="8M")),
            "abr": str(lib.cfg("encoding", "abr", default="128k")),
            "preset": str(lib.cfg("encoding", "preset", default="veryfast")),
            "threads": str(lib.cfg("encoding", "threads", default=1)),
        }

    def load_products(self) -> dict:
        """Parse product_id.txt: folder | id | title / title | caption / caption"""
        prods: dict[str, dict] = {}
        path = lib.product_txt()
        if not path.exists():
            logger.warning("product_id.txt missing at %s", path)
            return prods
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("//") or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4:
                prods[parts[0]] = {
                    "id": parts[1],
                    "titles": [t.strip() for t in parts[2].split("/") if t.strip()],
                    "captions": [c.strip() for c in parts[3].split("/") if c.strip()],
                }
        return prods

    def load_captions(self) -> list:
        path = lib.preset_txt()
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8", errors="ignore")
        import re
        return [c.strip() for c in re.split(r"\n\s*---\s*\n", "\n" + content + "\n") if c.strip()]

    def generate_malay_caption(self, product_info: dict, preset_caps: list, ai_caption: str | None = None) -> str:
        """Anti-spam Malay caption with random structure + policy gate."""
        base = random.choice(preset_caps) if preset_caps else "murah gila hari ni"
        if ai_caption:
            base = ai_caption

        hook = random.choice(self.HOOK_POOL)
        cta = random.choice(self.CTA_POOL)
        emoji_str = "".join(random.choices(self.EMOJI_POOL, k=random.randint(1, 3)))
        product_kw = (random.choice(product_info.get("captions", ["beli sini"]))
                      if product_info.get("captions") else "beli sini")

        struct = random.choice([1, 2, 3])
        if struct == 1:
            caption = f"{hook} {base} {emoji_str}\n{cta}"
        elif struct == 2:
            caption = (f"{base} {emoji_str}\n"
                       f"{random.choice(self.BENEFIT_CONNECTORS)} {product_kw}\n{cta}")
        else:
            caption = f"{base}\n{emoji_str} {cta}"

        if random.random() < 0.4:
            caption = caption.replace(" ", "  ", 1)  # double-space anti-dupe trick

        # Policy gate: the overlay is burned into pixels, cannot be edited later.
        report = scan_caption(caption)
        if report["needs_rewrite"]:
            reasons = [w for _, w in report["prohibited"]]
            repairable = all(w.startswith("medical") for w in reasons)
            if repairable:
                fixed, _notes = soften_claims(caption)
                if not scan_caption(fixed)["needs_rewrite"]:
                    caption = fixed
                else:
                    repairable = False
            if not repairable:
                safe = [c for c in preset_caps if not scan_caption(c)["needs_rewrite"]]
                caption = random.choice(safe) if safe else "beg kuning bawah 👇"
                caption = f"{caption}\n{cta}"
        caption = soften(caption, rate=0.7)
        if is_too_long(caption):
            caption = shorten(caption)
        return caption

    def md5_file(self, path: Path, chunk: int = 8192) -> str:
        m = hashlib.md5()
        with open(path, "rb") as f:
            for c in iter(lambda: f.read(chunk), b""):
                m.update(c)
        return m.hexdigest()[:12]

    def probe_resolution(self, video_path: Path) -> tuple[int, int] | None:
        cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_streams", "-of", "json", str(video_path)]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=15)
        if r.returncode != 0:
            raise ValueError(r.stderr)
        stream = json.loads(r.stdout)["streams"][0]
        w, h = int(stream.get("width", 0)), int(stream.get("height", 0))
        for sd in stream.get("side_data_list", []):
            if sd.get("side_data_type") == "Display Matrix" and \
                    abs(int(sd.get("rotation", 0))) in (90, 270):
                return h, w
        return w, h

    def scan_raw(self) -> dict[str, list[Path]]:
        root = lib.drive_root()
        stock: dict[str, list[Path]] = {}
        if not root.exists():
            return stock
        for entry in root.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.name in lib.NON_PRODUCT_DIRS:
                continue
            files = []
            for f in entry.iterdir():
                if f.is_file() and f.suffix.lower() in lib.VIDEO_EXTS:
                    try:
                        sz = f.stat().st_size
                        if 1_000_000 < sz < 500_000_000:
                            files.append(f)
                    except OSError:
                        pass
            if files:
                stock[entry.name] = files
        return stock

    def query_analytics_weights(self):
        """product_folder -> perf score, plus best sound/hashtag from rival."""
        weights: dict[str, float] = {}
        best_sound_id = best_sound_name = None
        db = lib.db_path()
        if not db.exists():
            return weights, best_sound_id, best_sound_name
        try:
            conn = sqlite3.connect(str(db))
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT v.product_folder, AVG(m.views) as avg_views
                FROM videos v JOIN daily_metrics m ON v.video_id=m.video_id
                WHERE m.snap_date >= date('now','-7 days')
                GROUP BY v.product_folder
                """)
            for r in cur.fetchall():
                avg = r["avg_views"] or 0
                weights[r["product_folder"]] = 0.7 + min(1.3, avg / 5000)
            cur = conn.execute("""
                SELECT sound_name, sound_id, AVG(views) as avg_v
                FROM competitor_videos
                WHERE snap_date >= date('now','-7 days')
                  AND handle IN (?, ?)
                GROUP BY sound_id ORDER BY avg_v DESC LIMIT 5
                """, (lib.OWN_HANDLE, lib.RIVAL_HANDLE))
            rows = cur.fetchall()
            if rows:
                chosen = random.choices(rows, weights=[r["avg_v"] or 1 for r in rows], k=1)[0]
                best_sound_id, best_sound_name = chosen["sound_id"], chosen["sound_name"]
            conn.close()
        except Exception as e:
            logger.warning("Analytics query failed: %s", e)
        return weights, best_sound_id, best_sound_name

    def pick_product_folder(self, products: dict, stock_map: dict,
                            perf_weights: dict, burn_history: list) -> str | None:
        candidates = []
        for folder, files in stock_map.items():
            if not files or folder not in products:
                continue
            if (lib.drive_root() / folder / "stop_post").exists():
                logger.info("Skip %s - stop_post marker", folder)
                continue
            if folder in burn_history[-3:]:
                logger.info("Penalize %s - recent repeat", folder)
                continue
            stock = len(files)
            if stock < 3:
                logger.warning("Low stock warning %s: %s videos left", folder, stock)
            perf = perf_weights.get(folder, 1.0)
            weight = stock * perf
            if random.random() < 0.15:
                weight *= 1.5
            candidates.append((folder, weight))
        if not candidates:
            for folder, files in stock_map.items():
                if files and folder in products:
                    candidates.append((folder, len(files)))
        if not candidates:
            return None
        folders, weights = zip(*candidates)
        return random.choices(folders, weights=weights, k=1)[0]

    def encode(self, input_video: Path, output_video: Path, tmp_png: Path | None,
               sound_file: Path | None, width: int, height: int,
               speed: float, brightness: float, contrast: float,
               trim_start: float, overlay_y: float) -> tuple[bool, str | None]:
        """Run ffmpeg. Returns (ok, err). Uses eof_action=repeat, NOT shortest=1."""
        e = self._encode()
        overlay_y_expr = f"(H-h)*{overlay_y:.3f}"
        vf = (
            f"[0:v]trim=start={trim_start:.2f},setpts=PTS-STARTPTS,"
            f"setpts=PTS/{speed:.3f},eq=brightness={brightness:.3f}:"
            f"contrast={contrast:.3f},scale=trunc(iw/2)*2:trunc(ih/2)*2[base];"
            f"[base][2:v]overlay=0:{overlay_y_expr}:format=auto:"
            f"eof_action=repeat[outv]"
        )
        cmd = ["ffmpeg", "-y", "-threads", e["threads"],
               "-i", str(input_video),
               "-stream_loop", "-1", "-i", str(sound_file),
               "-i", str(tmp_png),
               "-filter_complex", vf,
               "-map", "[outv]",
               "-map", "1:a",
               "-c:v", "libx264", "-crf", e["crf"], "-preset", e["preset"],
               "-maxrate", e["maxrate"], "-bufsize", e["bufsize"],
               "-pix_fmt", "yuv420p",
               "-profile:v", "high", "-level", "4.0",
               "-c:a", "aac", "-b:a", e["abr"], "-ar", "44100",
               "-shortest",
               "-movflags", "+faststart",
               str(output_video)]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, timeout=600)
            if res.returncode != 0:
                return False, res.stderr[-2000:]
            return True, None
        except subprocess.TimeoutExpired:
            return False, "ffmpeg timed out (>600s)"

    def process_one(self, folder: str, files: list, products: dict,
                    preset_caps: list, burn_history: list,
                    trending_sound_id: str, trending_sound_name: str) -> bool:
        root = lib.drive_root()
        random.shuffle(files)
        input_video, width, height = None, 1080, 1920
        for cand in files:
            try:
                w, h = self.probe_resolution(cand)
                if w >= 360 and h >= 360:
                    input_video, width, height = cand, w, h
                    break
            except Exception as e:
                logger.warning("Skip corrupt %s: %s", cand, e)
                continue
        if not input_video:
            logger.warning("No valid video in %s", folder)
            return False

        if folder not in products:
            logger.warning(
                "'%s' missing from product_id.txt - title/caption fall back to "
                "the folder name and product_id is empty (no TikTok Shop anchor).",
                folder)
        prod_info = products.get(folder, {"id": "", "titles": [folder], "captions": [folder]})

        caption = self.generate_malay_caption(prod_info, preset_caps)
        style = pick_style(lib.cfg("rendering", "force_style"))

        # Sound selection.
        sound_dir = lib.sounds_dir()
        soundtrack = sorted(sound_dir.glob("*.mp3")) if sound_dir.exists() else []
        if not soundtrack:
            logger.warning("No mp3 in soundtrack dir %s", sound_dir)
            return False
        selected_sound = random.choice(soundtrack)

        # Randomisation.
        speed = random.uniform(0.97, 1.06)
        brightness = random.uniform(-0.04, 0.04)
        contrast = random.uniform(0.97, 1.06)
        trim_start = random.uniform(0, 0.8)
        overlay_y = random.uniform(0.35, 0.50)

        # Render caption PNG.
        tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK) else "/tmp"
        tmp_png = Path(tmp_dir) / f"caption_{folder}_{int(time.time())}_{random.randint(1000, 9999)}.png"
        rendered = self.skia.render(caption, style, width, height, str(tmp_png))
        if not rendered or not tmp_png.exists():
            logger.warning("PNG render failed; aborting burn for %s", folder)
            return False

        # Output name.
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = f"{folder}_{ts}_{random.randint(100, 999)}"
        output_video = lib.queue_dir() / f"{out_name}.mp4"

        ok, err = self.encode(input_video, output_video, tmp_png, selected_sound,
                              width, height, speed, brightness, contrast,
                              trim_start, overlay_y)
        tmp_png.unlink(missing_ok=True)
        if not ok or not output_video.exists():
            logger.error("FFmpeg failed for %s: %s", folder, err)
            if output_video.exists():
                output_video.unlink(missing_ok=True)
            return False

        # Quality measurement.
        fsize_mb = output_video.stat().st_size / (1024 * 1024)
        out_dur = self.duration(output_video)
        out_frames = self.frame_count(output_video)
        mb_per_sec = fsize_mb / out_dur if out_dur else 0.0
        kbps = int(fsize_mb * 8 * 1024 / out_dur) if out_dur else 0
        low_quality = bool(out_dur and mb_per_sec < lib.MIN_MB_PER_SEC)

        # Motion guard: refuse to hand a still image to the uploader.
        if out_frames and out_frames < lib.MIN_OUTPUT_FRAMES:
            logger.error(
                "BROKEN BURN: %s has %s frame(s) (%ss) - STATIC IMAGE. "
                "Quarantining; raw kept for retry.",
                output_video.name, out_frames, round(out_dur, 2))
            lib.failed_dir().mkdir(parents=True, exist_ok=True)
            quarantine = lib.failed_dir() / output_video.name
            try:
                shutil.move(str(output_video), str(quarantine))
            except OSError as e:
                logger.error("Quarantine failed (%s); deleting", e)
                output_video.unlink(missing_ok=True)
            return False

        logger.info("Success %s %.2fMB (%.1fs, %s frames, %.2f MB/s, ~%s kbps, "
                    "crf=%s maxrate=%s preset=%s)",
                    output_video, fsize_mb, out_dur, out_frames, mb_per_sec,
                    kbps, e["crf"], e["maxrate"], e["preset"])
        if low_quality:
            logger.warning("QUALITY REGRESSION: %.2f MB/s below %s floor. "
                           "Check FFMPEG_CRF (<=25) / maxrate.", mb_per_sec,
                           lib.MIN_MB_PER_SEC)

        # Archive raw locally AND record it in the DB ledger (source of truth).
        processed_folder = lib.processed_dir() / folder
        processed_folder.mkdir(parents=True, exist_ok=True)
        try:
            dest = processed_folder / input_video.name
            shutil.move(str(input_video), str(dest))
            rel = f"{folder}/{input_video.name}"
            # Audit journal (optional; review only).
            try:
                with open(lib.deleted_log(), "a") as dl:
                    dl.write(rel + "\n")
            except OSError:
                pass
            # DB ledger: mark this raw consumed so it is never re-selected and
            # sync_out deletes its Drive copy.
            try:
                lib.mark_raw_consumed(folder, input_video.name,
                                      file_hash=self.md5_file(dest))
                logger.info("Ledger: marked %s consumed (posted_at set)", rel)
            except Exception as e:
                logger.warning("Ledger write failed for %s: %s", rel, e)
        except OSError as e:
            logger.warning("Archive failed: %s", e)

        # Build sidecar metadata.
        title = random.choice(prod_info["titles"]) if prod_info.get("titles") else folder
        hashtags = [f"#{folder.lower()}", "#tiktokshop", "#murah", "#begkuning"]
        try:
            db = lib.db_path()
            if db.exists():
                conn = sqlite3.connect(str(db))
                row = conn.execute(
                    "SELECT top_hashtag FROM competitor_daily "
                    "WHERE handle=? ORDER BY snap_date DESC LIMIT 1",
                    (lib.RIVAL_HANDLE,)).fetchone()
                if row and row[0]:
                    hashtags.append(f"#{row[0].lstrip('#')}")
                conn.close()
        except Exception:
            pass
        if random.random() < 0.6:
            title = f"{title} {random.choice(['🔥', '😭', '👇', '✨'])}"

        sidecar = {
            "product_id": prod_info.get("id", ""),
            "product_folder": folder,
            "title": title,
            "caption": (random.choice(prod_info.get("captions", [folder]))
                        if prod_info.get("captions") else folder),
            "overlay_caption": caption,
            "hashtags": hashtags,
            "sound_path": str(selected_sound),
            "sound_name": selected_sound.stem,
            "trending_sound_id": trending_sound_id,
            "trending_sound_name": trending_sound_name,
            "style_name": style["name"],
            "style_css": style.get("css", "")[:80],
            "speed": round(speed, 4),
            "overlay_y": round(overlay_y * 100, 1),
            "input_video": str(input_video),
            "output_video": str(output_video),
            "processed_at": datetime.now().isoformat(),
            "file_size_mb": round(fsize_mb, 2),
            "duration_s": round(out_dur, 2),
            "frames": out_frames,
            "mb_per_sec": round(mb_per_sec, 3),
            "video_kbps": kbps,
            "low_quality": low_quality,
            "encode": self._encode(),
        }
        sidecars = SidecarManager(lib.queue_dir())
        sidecars.write(output_video, sidecar)

        # Burn log for the growth engine + report.
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "folder": folder,
            "product_id": sidecar["product_id"],
            "title": title,
            "overlay_caption": caption,
            "sound_file": selected_sound.name,
            "sound_name": selected_sound.stem,
            "trending_sound_used": trending_sound_id is not None,
            "style": style["name"],
            "speed": round(speed, 4),
            "overlay_y_percent": round(overlay_y * 100, 1),
            "input_hash": self.md5_file(output_video),
            "output_path": str(output_video),
            "output_size_mb": round(fsize_mb, 2),
            "duration_s": round(out_dur, 2),
            "frames": out_frames,
            "fps_effective": round(out_frames / out_dur, 1) if out_dur else 0,
            "mb_per_sec": round(mb_per_sec, 3),
            "video_kbps": kbps,
            "low_quality": low_quality,
            "encode": self._encode(),
        }
        with open(lib.burn_jsonl(), "a", encoding="utf-8") as jl:
            jl.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        return True

    def run(self, dry_run: bool = False) -> int:
        lib.queue_dir().mkdir(parents=True, exist_ok=True)
        # Clean the queue of files older than 24h so a failed retry isn't deleted.
        for f in lib.queue_dir().glob("*"):
            if f.is_file() and (time.time() - f.stat().st_mtime) > 1440 * 60:
                try:
                    f.unlink()
                except OSError:
                    pass

        for tool in ("python3", "ffmpeg", "ffprobe"):
            if shutil.which(tool) is None:
                logger.error("Missing required tool: %s", tool)
                return 1

        products = self.load_products()
        preset_caps = self.load_captions()
        logger.info("Loaded %d products, %d preset captions",
                    len(products), len(preset_caps))

        stock_map = self.scan_raw()
        if not stock_map:
            logger.warning("No videos to process")
            return 0

        burn_history = []
        if lib.burn_jsonl().exists():
            try:
                for line in lib.burn_jsonl().read_text().strip().splitlines()[-20:]:
                    burn_history.append(json.loads(line).get("folder"))
            except Exception:
                pass

        perf_weights, ts_id, ts_name = self.query_analytics_weights()
        folder = self.pick_product_folder(products, stock_map, perf_weights,
                                          burn_history)
        if not folder:
            logger.warning("No folder picked")
            return 0

        if dry_run:
            print(f"[dry-run] would process folder={folder} "
                  f"videos={[f.name for f in stock_map[folder]]}")
            return 0

        return 0 if self.process_one(folder, stock_map[folder], products,
                                     preset_caps, burn_history, ts_id, ts_name) else 1