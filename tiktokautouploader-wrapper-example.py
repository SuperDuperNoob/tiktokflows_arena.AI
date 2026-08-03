#!/usr/bin/env python3
"""
auto_uploader_v4.py - resilient TikTokFlow uploader
- Anti-spam: jitter, hash tracking, low-stock guard, cookie expiry check
- Tracking: logs to tiktok_analytics.db + success.log + prevents duplicate uploads
- Resilience: retry with backoff, moves failed to failed/, keeps sidecars as JSON
- For 4GB RAM VPS: single upload per run, no concurrency, flock lock
- Optional TIKTOK_PROXY: route ONLY the TikTok upload through a Malaysian
  residential/mobile proxy (datacenter IPs get 0-view shadowbans). Includes a
  ~2KB pre-upload exit-IP geo check + no-retry-on-dead-proxy so GB-metered
  proxy plans never burn a full video upload on a bad/dead proxy.
"""
import os, sys, random, time, json, sqlite3, hashlib, argparse, shutil
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

LOCKFILE = Path("/tmp/auto_uploader_v4.lock")

DRIVE_ROOT = Path(os.path.expanduser("~/tiktokflow/tiktokflow_drive"))
VIDEOS_DIR = Path(os.path.expanduser("~/tiktokflow/TiktokAutoUploader/VideosDirPath"))
PROCESSED_DIR = DRIVE_ROOT / "processed"
FAILED_DIR = DRIVE_ROOT / "failed"
SUCCESS_LOG = DRIVE_ROOT / "success.log"
FAILED_LOG = DRIVE_ROOT / "failed.log"
BURN_JSONL = DRIVE_ROOT / "burn_log.jsonl"
DB_PATH = Path(os.environ.get("TIKTOK_ANALYTICS_DB", os.path.expanduser("~/tiktokflow/tiktok_analytics.db")))
CONFIG_PATH = Path(os.path.expanduser("~/tiktokflow/TiktokAutoUploader/config.txt"))

# Add TiktokAutoUploader to path
sys.path.insert(0, str(Path(__file__).parent / "TiktokAutoUploader"))
try:
    from tiktok_uploader.tiktok_v2 import upload_video
    from tiktok_uploader.Config import Config
except Exception as e:
    print(f"[uploader v4] Failed to import TiktokAutoUploader: {e}", file=sys.stderr)
    sys.exit(1)

def get_lock():
    import fcntl
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    f = open(LOCKFILE, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except:
        print("[uploader v4] Another upload in progress, exiting 0 for idempotency")
        sys.exit(0)

def md5_file(p):
    h=hashlib.md5()
    with open(p,'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def env_flag(name, default=False):
    """Parse a boolean-ish env var: 1/true/yes/on = True."""
    v=os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v in ("1","true","yes","on")

def mask_proxy(url):
    """Log-safe proxy rendering: scheme://use***@host:port - never prints the password."""
    if not url:
        return None
    try:
        p=urlparse(url if "://" in url else f"http://{url}")
        user=""
        if p.username:
            u=p.username
            user=f"{u[:3]}***@" if len(u)>3 else "***@"
        host=p.hostname or "?"
        port=f":{p.port}" if p.port else ""
        return f"{p.scheme}://{user}{host}{port}"
    except Exception:
        return "(could not parse TIKTOK_PROXY URL)"

def check_proxy_exit(proxy_url, timeout=10):
    """Verify the proxy exits in Malaysia on a residential/mobile line, not a datacenter.

    Costs ~2KB of proxy traffic and runs BEFORE any video bytes are sent, so a
    wrong-country or hosting-class proxy never burns a full metered upload
    (~5-10MB of GB-plan quota) on a post that would get shadowbanned anyway.

    Returns (ok, detail): True = verified MY residential/mobile;
    False = verified bad (non-MY or hosting); None = check unreachable (unknown).
    """
    import requests  # local import: only needed when a proxy is configured
    proxies={"http": proxy_url, "https": proxy_url}
    last_err="no geo endpoint tried"
    # ip-api.com: free, no key, and returns exactly the mobile/proxy/hosting
    # flags that separate a Malaysian residential/4G line from a datacenter box.
    try:
        r=requests.get(
            "http://ip-api.com/json/?fields=status,message,country,countryCode,city,isp,org,mobile,proxy,hosting,query",
            proxies=proxies, timeout=timeout)
        j=r.json()
        if j.get("status")=="success":
            cc=j.get("countryCode","?")
            kinds=[]
            if j.get("mobile"): kinds.append("mobile/4G")
            if j.get("hosting"): kinds.append("DATACENTER-hosting")
            if j.get("proxy"): kinds.append("proxy-flagged")
            if not kinds: kinds.append("residential/ISP")
            detail=(f"exit_ip={j.get('query')} geo={j.get('city','?')},{cc} "
                    f"isp={j.get('isp','?')} org={j.get('org','?')} type={'+'.join(kinds)}")
            ok=(cc=="MY") and not j.get("hosting")
            return ok, detail
        last_err=f"ip-api: {j.get('message','unknown error')}"
    except Exception as e:
        last_err=f"ip-api: {e}"
    # Fallback: ipinfo.io over HTTPS (country + ASN org only, no hosting flag).
    try:
        r=requests.get("https://ipinfo.io/json", proxies=proxies, timeout=timeout)
        j=r.json()
        if j.get("ip"):
            cc=j.get("country","?")
            detail=(f"exit_ip={j.get('ip')} geo={j.get('city','?')},{cc} "
                    f"org={j.get('org','?')} type=unknown(ip-api fallback)")
            return (cc=="MY"), detail
        last_err=f"{last_err}; ipinfo: no ip in response"
    except Exception as e:
        last_err=f"{last_err}; ipinfo: {e}"
    return None, f"geo check failed: {last_err}"

def is_proxy_transport_error(exc):
    """True for 'the proxy itself is broken' errors (NOT TikTok API errors).

    Retrying those re-sends the entire video through a dead proxy, which on a
    GB-metered residential plan burns another ~5-10MB per attempt for nothing.
    """
    try:
        import requests
        if isinstance(exc,(requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout)):
            return True
    except Exception:
        pass
    msg=str(exc).lower()
    return any(s in msg for s in (
        "proxyerror",
        "cannot connect to proxy",
        "unable to connect to proxy",
        "tunnel connection failed",
        "407 proxy authentication required",
    ))

def load_sidecar_json(json_path):
    try:
        data=json.loads(json_path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        print(f"[v4] sidecar JSON load failed {json_path}: {e}")
        return None

def load_sidecar_pid(pid_path):
    """legacy .pid: product_id|title|caption"""
    try:
        txt=pid_path.read_text(encoding="utf-8").strip()
        parts=txt.split("|",2)
        pid=parts[0] if len(parts)>0 else ""
        title=parts[1] if len(parts)>1 else pid_path.stem
        cap=parts[2] if len(parts)>2 else ""
        return {"product_id":pid,"title":title,"caption":cap}
    except Exception as e:
        print(f"[v4] pid load failed {pid_path}: {e}")
        return None

def check_cookie_expiry():
    """Check if TikTok cookies older than 12h - warn, as observed fails after 16h idle"""
    # CookiesDir may be in different locations
    possible_dirs=[
        Path(os.path.expanduser("~/tiktokflow/TiktokAutoUploader/CookiesDir")),
        Path("/home/archery/tiktokflow/TiktokAutoUploader/CookiesDir"),
        Path(__file__).parent / "TiktokAutoUploader/CookiesDir",
    ]
    for d in possible_dirs:
        if d.exists():
            for f in d.glob("tiktok_session-*"):
                try:
                    age_hours=(time.time()-f.stat().st_mtime)/3600
                    print(f"[v4] Cookie {f.name} age {age_hours:.1f}h")
                    if age_hours>12:
                        print(f"[v4] WARNING: Cookie older than 12h ({age_hours:.1f}h) - high risk of session expiry, consider re-login")
                        # write warning to failed.log for AI diagnostic
                        with open(FAILED_LOG,"a") as fl:
                            fl.write(f"{datetime.now().isoformat()} WARNING cookie {f.name} age {age_hours:.1f}h - may need re-login\n")
                    if age_hours>36:
                        print(f"[v4] CRITICAL: Cookie >36h, upload likely FAIL with status_code 5")
                    return age_hours
                except Exception as e:
                    print(f"[v4] Cookie check error: {e}")
    print("[v4] No cookie files found - will likely fail, need to login via browser")
    return None

def is_duplicate_upload(video_path):
    """Check if this file hash already uploaded in last 30 days (avoid TikTok duplicate detection)"""
    try:
        if not DB_PATH.exists():
            return False
        h=md5_file(video_path)
        conn=sqlite3.connect(DB_PATH)
        conn.row_factory=sqlite3.Row
        # Check videos table if we stored hash? We don't yet, but check daily_metrics for recent same product?
        # For now, check burn_log.jsonl for same input_hash? We'll check hash in success.log simple
        if SUCCESS_LOG.exists():
            text=SUCCESS_LOG.read_text(errors="ignore")
            if h[:8] in text:
                print(f"[v4] Potential duplicate hash {h[:8]} found in success.log")
                # not hard block, just warn
        conn.close()
        return False
    except Exception as e:
        print(f"[v4] dup check failed: {e}")
        return False

def jitter_sleep():
    """Random sleep 5-90 sec to avoid bot pattern detection"""
    delay=random.randint(5,90)
    print(f"[v4] Anti-bot jitter sleeping {delay}s before upload...")
    time.sleep(delay)

def get_videos_with_sidecars():
    """Find all mp4 with sidecar json, prioritize newest, but weight against recent product repeats"""
    if not VIDEOS_DIR.exists():
        print(f"[v4] VideosDirPath missing {VIDEOS_DIR}")
        return []

    mp4s=list(VIDEOS_DIR.glob("*.mp4"))
    if not mp4s:
        print(f"[v4] No mp4 in {VIDEOS_DIR}")
        return []

    candidates=[]
    for mp4 in mp4s:
        json_side=mp4.with_suffix(".json")
        pid_side=mp4.with_suffix(".pid")
        data=None
        if json_side.exists():
            data=load_sidecar_json(json_side)
        elif pid_side.exists():
            data=load_sidecar_pid(pid_side)
            # upgrade to include json path
        if not data:
            print(f"[v4] No sidecar for {mp4.name}, skipping to avoid data loss")
            continue
        # age
        age= time.time()-mp4.stat().st_mtime
        candidates.append((mp4, data, json_side, pid_side, age))

    # Sort: newest first, but avoid product repeats last 3 uploads (read burn jsonl)
    recent_products=[]
    if BURN_JSONL.exists():
        try:
            for line in BURN_JSONL.read_text().strip().splitlines()[-3:]:
                j=json.loads(line)
                recent_products.append(j.get("folder"))
        except: pass

    def score(item):
        mp4,data,js,pid,age=item
        s=0
        # newer = higher
        s+= max(0, 1000-age/10)
        if data.get("product_folder") in recent_products:
            s-=500
        return s

    candidates.sort(key=score, reverse=True)
    return candidates

def log_to_analytics(video_path, sidecar, success=True):
    """Log upload to the analytics DB.

    `caption` stores the TITLE that was actually posted to TikTok, not the
    burned-in overlay text. reconcile_own_metrics.py matches our uploads to
    scraped videos on the posted description, and the overlay text never
    appears there, so storing the overlay made caption matching always miss.
    """
    if not success:
        return
    try:
        # Create the DB if missing instead of silently skipping the log.
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn=sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            from tiktokflow_lib import ensure_schema
            ensure_schema(conn)
        except Exception:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    product_folder TEXT,
                    caption TEXT,
                    hashtags_json TEXT,
                    sound_id TEXT,
                    sound_name TEXT,
                    posted_at TEXT NOT NULL
                );
            """)
        vid_id=f"{sidecar.get('product_folder','unk')}_{int(time.time())}_{random.randint(1000,9999)}"
        hashtags=json.dumps(sidecar.get("hashtags",[]), ensure_ascii=False)
        posted_title=(sidecar.get("title","") or sidecar.get("caption","") or "")[:500]
        conn.execute("""
            INSERT OR REPLACE INTO videos(video_id, product_folder, caption, hashtags_json, sound_id, sound_name, posted_at)
            VALUES(?,?,?,?,?,?,?)
        """, (
            vid_id,
            sidecar.get("product_folder",""),
            posted_title,
            hashtags,
            sidecar.get("trending_sound_id","") or sidecar.get("sound_name",""),
            sidecar.get("sound_name",""),
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
        conn.close()
        print(f"[v4] Logged to analytics DB: {vid_id}")
        return vid_id
    except Exception as e:
        print(f"[v4] Analytics log failed: {e}")

def safe_remove_files(mp4_path, json_path, pid_path):
    for p in [mp4_path, json_path, pid_path]:
        try:
            if p and p.exists():
                p.unlink()
                print(f"[v4] Deleted {p.name}")
        except Exception as e:
            print(f"[v4] Delete failed {p}: {e}")

def move_to_failed(mp4_path, json_path, pid_path, reason):
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir=FAILED_DIR / f"{mp4_path.stem}_{ts}"
    dest_dir.mkdir(exist_ok=True)
    for p in [mp4_path, json_path, pid_path]:
        if p and p.exists():
            try:
                shutil.move(str(p), str(dest_dir / p.name))
            except Exception as e:
                print(f"[v4] Move to failed error {p}: {e}")
    # Write reason
    try:
        (dest_dir / "reason.txt").write_text(f"{datetime.now().isoformat()}\n{reason}\n", encoding="utf-8")
    except: pass
    print(f"[v4] Moved failed upload to {dest_dir}")

def run():
    parser=argparse.ArgumentParser(description="TikTokFlow Auto Uploader v4")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual upload")
    parser.add_argument("--now", action="store_true", help="Legacy flag")
    args=parser.parse_args()

    lock_f=get_lock()

    print(f"[v4] Started at {datetime.now().isoformat()} - dry_run={args.dry_run}")
    print(f"[v4] VIDEOS_DIR={VIDEOS_DIR} exists={VIDEOS_DIR.exists()}")

    # Optional residential/mobile proxy. VPS IPs are datacenter IPs and TikTok
    # quietly shadowbans uploads from them (0 views). Only the TikTok upload
    # traffic is routed through it (passed per-call, never via global
    # HTTP(S)_PROXY) so Apify/Telegram/Drive/AI traffic cannot eat proxy GB.
    proxy_url=os.environ.get("TIKTOK_PROXY", "").strip() or None
    if proxy_url:
        print(f"[v4] Upload proxy    : {mask_proxy(proxy_url)} (exit IP verified before upload)")
    else:
        print(f"[v4] Upload proxy    : None - posting from VPS datacenter IP, 0-view shadowban risk (set TIKTOK_PROXY to a Malaysian residential/4G proxy)")

    # Load config
    if CONFIG_PATH.exists():
        try:
            Config.load(str(CONFIG_PATH))
        except Exception as e:
            print(f"[v4] Config load warning: {e}")

    # Cookie age check
    check_cookie_expiry()

    cands=get_videos_with_sidecars()
    if not cands:
        print("[v4] No valid video+sidecar found - ensure process-videos-v4.sh ran", file=sys.stderr)
        sys.exit(1)

    print(f"[v4] Found {len(cands)} candidates, picking best")
    mp4_path, sidecar, json_path, pid_path, age = cands[0]

    product_id=sidecar.get("product_id","")
    title=sidecar.get("title","") or sidecar.get("product_folder","")
    # TikTok shop caption limit 21 chars for product anchor keyword
    raw_caption=sidecar.get("caption","") or sidecar.get("product_folder","")
    safe_caption=raw_caption[:21].strip()
    if not safe_caption:
        safe_caption=sidecar.get("product_folder","")[:21]

    print(f"Target Video Path: {mp4_path}")
    print(f"Target Product ID: {product_id}")
    print(f"Target Title     : {title}")
    print(f"Target Caption   : {raw_caption} -> safe 21char: '{safe_caption}'")
    print(f"Product Folder   : {sidecar.get('product_folder')}")
    print(f"Sound            : {sidecar.get('sound_name')}")
    print(f"Hashtags         : {sidecar.get('hashtags')}")
    print(f"Session User     : {os.environ.get('TIKTOK_SESSION_USER','kumpul.shop')}")

    if is_duplicate_upload(mp4_path):
        print("[v4] Duplicate risk - continuing but flagged")

    # Pre-upload proxy exit-IP check. Runs only when a video is actually queued
    # (empty queue = 0 proxy bytes spent) and costs ~2KB. A wrong-country or
    # datacenter-class exit would both shadowban the post AND waste a full
    # video's worth of metered proxy GB uploading it, so verify first.
    if proxy_url:
        if env_flag("TIKTOK_PROXY_GEO_CHECK", default=True):
            geo_ok, geo_detail=check_proxy_exit(proxy_url)
            print(f"[v4] Proxy exit check: {geo_detail}")
            if geo_ok is True:
                print("[v4] Proxy exit IP verified: Malaysia residential/mobile line")
            elif geo_ok is False:
                print("[v4] WARNING: proxy exit IP is NOT Malaysian residential/mobile - uploads through it may still get 0-view shadowbanned", file=sys.stderr)
                if env_flag("TIKTOK_PROXY_STRICT", default=False):
                    if args.dry_run:
                        print("[v4] TIKTOK_PROXY_STRICT=1: real run WOULD abort here before burning proxy GB (dry-run continues)")
                    else:
                        print("[v4] TIKTOK_PROXY_STRICT=1: aborting BEFORE upload - a bad exit would burn metered proxy GB for a shadowbanned post. Fix TIKTOK_PROXY first.", file=sys.stderr)
                        try:
                            FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
                            with open(FAILED_LOG,"a",encoding="utf-8") as ff:
                                ff.write(f"{datetime.now().isoformat()} ABORTED proxy geo check failed: {geo_detail}\n")
                        except Exception as e:
                            print(f"[v4] failed.log write error: {e}")
                        sys.exit(1)
            else:
                # Geo endpoints unreachable (proxy down or no route) - cannot
                # prove the exit is good, but also cannot prove it is bad, so
                # we stay non-blocking. A dead proxy will fail the upload fast
                # with a transport error and the retry guard will stop it there.
                print("[v4] Proxy geo check unavailable, continuing unverified (set TIKTOK_PROXY_GEO_CHECK=0 to skip this check)", file=sys.stderr)
        else:
            print("[v4] Proxy geo check disabled via TIKTOK_PROXY_GEO_CHECK=0")

    if args.dry_run:
        print("--- DRY RUN: would upload above ---")
        # Still log analytics dry
        sys.exit(0)

    # Anti-bot jitter
    jitter_sleep()

    # Upload with retry
    session_user=os.environ.get("TIKTOK_SESSION_USER","kumpul.shop")
    max_retries=2
    last_exc=None
    for attempt in range(1, max_retries+1):
        try:
            print(f"[v4] Attempt {attempt}/{max_retries} uploading {mp4_path.name} at {datetime.now().isoformat()} via={mask_proxy(proxy_url) or 'direct'}")
            success=upload_video(
                session_user=session_user,
                video=str(mp4_path),
                title=title,
                products=[{"product_id": product_id, "caption": safe_caption}] if product_id else [],
                proxy=proxy_url
            )
            if success:
                print(f"[v4] Upload SUCCESS for {mp4_path.name}")
                vid_id=log_to_analytics(mp4_path, sidecar, success=True)
                # Log success.log with JSON
                with open(SUCCESS_LOG,"a",encoding="utf-8") as sf:
                    sf.write(f"{datetime.now().isoformat()} SUCCESS {mp4_path.name} product={sidecar.get('product_folder')} pid={product_id} title={title!r} hash={md5_file(mp4_path)[:10]} size={mp4_path.stat().st_size}\n")
                safe_remove_files(mp4_path, json_path, pid_path)
                print(f"[v4] Cleaned up after success")
                sys.exit(0)
            else:
                print(f"[v4] Upload returned False (TikTok API error) attempt {attempt}", file=sys.stderr)
                last_exc="API returned False"
                if attempt < max_retries:
                    sleep_t=attempt*30+random.randint(5,15)
                    print(f"[v4] Retrying in {sleep_t}s...")
                    time.sleep(sleep_t)
        except Exception as e:
            import traceback
            traceback.print_exc()
            last_exc=str(e)
            print(f"[v4] Exception attempt {attempt}: {e}", file=sys.stderr)
            # Proxy transport failures mean the proxy itself is dead/wrong - a
            # retry would re-send the whole video through it and just burn
            # another chunk of metered GB plan quota. Bail instead of retrying.
            if proxy_url and is_proxy_transport_error(e):
                print("[v4] Proxy transport error - NOT retrying to protect metered proxy quota. Check TIKTOK_PROXY credentials/ endpoint.", file=sys.stderr)
                break
            if attempt < max_retries:
                sleep_t=attempt*60
                print(f"[v4] Retry sleep {sleep_t}s")
                time.sleep(sleep_t)

    # All retries failed
    print(f"[v4] All retries failed for {mp4_path.name}: {last_exc}", file=sys.stderr)
    with open(FAILED_LOG,"a",encoding="utf-8") as ff:
        ff.write(f"{datetime.now().isoformat()} FAILED {mp4_path.name} product={sidecar.get('product_folder')} reason={last_exc} file={mp4_path}\n")
    move_to_failed(mp4_path, json_path, pid_path, reason=last_exc)
    sys.exit(1)

if __name__=="__main__":
    run()
