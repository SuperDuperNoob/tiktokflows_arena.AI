"""
Web Interface Backend — FastAPI

Provides a REST API and serves the static frontend for the TikTok
Auto-Posting Machine. Designed to run behind Cloudflare Tunnel
(no open ports needed).

Endpoints:
  GET  /api/status          — Dashboard data (stock, posts, events)
  GET  /api/config          — Current configuration
  PUT  /api/config          — Update configuration
  GET  /api/posts           — Recent posts
  GET  /api/captions        — Caption pool (optional ?product filter)
  POST /api/captions        — Add caption to pool
  GET  /api/products        — Product list
  GET  /api/events          — System events log
  POST /api/actions/sync    — Trigger Google Drive sync
  POST /api/actions/test-proxy — Test proxy connection
  GET  /api/actions/cookie-status — Check cookie age

Run: python3 server.py
Access: http://localhost:8080 (tunnel via cloudflared)
"""
import os
import sys
import json
import yaml
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add scripts to path
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from db import Database
from compliance import ComplianceEngine

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
DB_PATH = PROJECT_ROOT / "logs" / "tiktok.db"
PRODUCTS_PATH = PROJECT_ROOT / "content" / "products.json"

# Load config
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

# Initialize DB
db = Database(str(DB_PATH))

app = FastAPI(title="TikTok Auto-Posting Machine", version="1.0")

# Mount static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Pydantic Models ──────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    section: str
    key: str
    value: str

class CaptionAdd(BaseModel):
    product_name: Optional[str] = None
    caption_text: str
    description_text: Optional[str] = None
    product_tag_text: Optional[str] = None
    source: str = "manual"

class ProductAdd(BaseModel):
    name: str
    product_id: str

class TagAdd(BaseModel):
    product_name: str
    tag: str

class ActionResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


# ── Root ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── Dashboard / Status ───────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """Full dashboard data."""
    posted_today = db.get_posted_count_today()
    target = CONFIG.get("posting", {}).get("daily_post_target", 7)
    stock_counts = db.get_raw_stock_counts()
    products_due = db.get_products_due_next()
    recent_events = db.get_recent_events(limit=10)
    recent_posts = []

    with db._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM posts ORDER BY posted_at DESC LIMIT 5"
        ).fetchall()
        recent_posts = [dict(r) for r in rows]

    # Performance summary
    perf = db.get_performance_summary(days=7)

    # Cookie status
    cookie_status = get_cookie_status()

    # Drive cleanup (minimal: pending deletes + how many were cleaned today)
    drive_cleanup = get_drive_cleanup_status()

    return {
        "posted_today": posted_today,
        "daily_target": target,
        "stock_counts": stock_counts,
        "products_due": products_due,
        "recent_events": recent_events,
        "recent_posts": recent_posts,
        "performance": perf,
        "cookie_status": cookie_status,
        "drive_cleanup": drive_cleanup,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Configuration ────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Return current configuration (secrets masked)."""
    config = load_config()
    # Mask sensitive values
    if "telegram" in config:
        config["telegram"]["bot_token"] = mask_secret(config["telegram"].get("bot_token", ""))
    if "ai" in config:
        config["ai"]["api_key"] = mask_secret(config["ai"].get("api_key", ""))
    if "apify" in config:
        config["apify"]["api_token"] = mask_secret(config["apify"].get("api_token", ""))
    if "proxy" in config:
        config["proxy"]["endpoint"] = mask_secret(config["proxy"].get("endpoint", ""))
    return config


@app.put("/api/config")
async def update_config(payload: ConfigUpdate):
    """Update a single config value."""
    config = load_config()
    section = payload.section
    key = payload.key

    if section not in config:
        raise HTTPException(400, f"Unknown section: {section}")
    if key not in config[section]:
        raise HTTPException(400, f"Unknown key: {key}")

    old_value = config[section][key]

    # Type preservation
    if isinstance(old_value, bool):
        config[section][key] = payload.value.lower() in ("true", "1", "yes")
    elif isinstance(old_value, int):
        config[section][key] = int(payload.value)
    elif isinstance(old_value, float):
        config[section][key] = float(payload.value)
    else:
        config[section][key] = payload.value

    save_config(config)
    db.log_event("CONFIG_CHANGE", f"{section}.{key} changed",
                 metadata={"old": str(old_value), "new": str(config[section][key])})

    return {"success": True, "section": section, "key": key, "value": config[section][key]}


# ── Posts ────────────────────────────────────────────────────────────────

@app.get("/api/posts")
async def get_posts(limit: int = 50, product: Optional[str] = None, status: Optional[str] = None):
    """Get posts with optional filters."""
    with db._connect() as conn:
        query = "SELECT * FROM posts WHERE 1=1"
        params = []
        if product:
            query += " AND product_name = ?"
            params.append(product)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY posted_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ── Captions ─────────────────────────────────────────────────────────────

@app.get("/api/captions")
async def get_captions(product: Optional[str] = None):
    """Get caption pool, optionally filtered by product."""
    if product:
        captions = db.get_caption_pool_for_product(product)
    else:
        # Get all
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM caption_pool ORDER BY times_used DESC"
            ).fetchall()
            captions = [dict(r) for r in rows]
    return captions


@app.post("/api/captions")
async def add_caption(payload: CaptionAdd):
    """Add a caption to the pool (with compliance check)."""
    compliance = ComplianceEngine(
        CONFIG.get("compliance", {}),
        ai_config=CONFIG.get("ai", {}),
    )
    approved, final_text, issues = compliance.process_caption(payload.caption_text)

    if not approved:
        raise HTTPException(400, f"Caption rejected: {issues}")

    db.add_caption(
        product_name=payload.product_name,
        caption_text=final_text,
        description_text=payload.description_text,
        product_tag_text=payload.product_tag_text,
        source=payload.source,
        compliance_checked=True,
        original_text=payload.caption_text if final_text != payload.caption_text else None,
    )

    return {"success": True, "caption": final_text, "issues": issues}


# ── Products ────────────────────────────────────────────────────────────

@app.get("/api/products")
async def get_products():
    """Get product list from products.json and config."""
    products = {}
    if PRODUCTS_PATH.exists():
        with open(PRODUCTS_PATH, "r") as f:
            try:
                products = json.load(f)
            except:
                pass

    # Merge with config product details
    config_products = CONFIG.get("products", {})
    result = []
    for name, data in products.items():
        if isinstance(data, dict):
            product_id = data.get("id", "")
            tags = data.get("yellow_bag_tags", [])
        else:
            product_id = str(data)
            tags = []

        detail = config_products.get(name, {})
        stock = db.get_raw_stock_counts().get(name, 0)
        result.append({
            "name": name,
            "product_id": product_id,
            "yellow_bag_tags": tags,
            "description": detail.get("description", ""),
            "keywords": detail.get("keywords", []),
            "stock": stock,
        })

    return result

@app.post("/api/products")
async def add_product(payload: ProductAdd):
    """Add a new product, update JSON, and create its raw folder."""
    products = {}
    if PRODUCTS_PATH.exists():
        with open(PRODUCTS_PATH, "r") as f:
            try:
                products = json.load(f)
            except Exception:
                pass
    
    # Store using dict format so we can add tags later
    products[payload.name] = {
        "id": payload.product_id,
        "yellow_bag_tags": []
    }
    
    with open(PRODUCTS_PATH, "w") as f:
        json.dump(products, f, indent=2)
        
    # Create raw folder
    raw_dir = PROJECT_ROOT / CONFIG.get("content", {}).get("raw_dir", "content/raw")
    product_dir = raw_dir / payload.name
    product_dir.mkdir(parents=True, exist_ok=True)
    
    dummy_file = product_dir / ".keep"
    if not dummy_file.exists():
        dummy_file.write_text("keep folder for Google Drive sync")
        
    return {"status": "success", "message": f"Added product {payload.name}"}

@app.post("/api/products/tags")
async def add_product_tag(payload: TagAdd):
    """Add a yellow bag tag to a product."""
    if not PRODUCTS_PATH.exists():
        raise HTTPException(400, "products.json not found")
        
    with open(PRODUCTS_PATH, "r") as f:
        products = json.load(f)
        
    if payload.product_name not in products:
        raise HTTPException(404, "Product not found")
        
    data = products[payload.product_name]
    if not isinstance(data, dict):
        products[payload.product_name] = {
            "id": str(data),
            "yellow_bag_tags": [payload.tag]
        }
    else:
        tags = data.get("yellow_bag_tags", [])
        if payload.tag not in tags:
            tags.append(payload.tag)
        data["yellow_bag_tags"] = tags
        products[payload.product_name] = data
        
    with open(PRODUCTS_PATH, "w") as f:
        json.dump(products, f, indent=2)
        
    return {"status": "success"}

@app.delete("/api/products/tags")
async def remove_product_tag(payload: TagAdd):
    """Remove a yellow bag tag from a product."""
    if not PRODUCTS_PATH.exists():
        raise HTTPException(400, "products.json not found")
        
    with open(PRODUCTS_PATH, "r") as f:
        products = json.load(f)
        
    if payload.product_name not in products:
        raise HTTPException(404, "Product not found")
        
    data = products[payload.product_name]
    if isinstance(data, dict):
        tags = data.get("yellow_bag_tags", [])
        if payload.tag in tags:
            tags.remove(payload.tag)
        data["yellow_bag_tags"] = tags
        products[payload.product_name] = data
        
        with open(PRODUCTS_PATH, "w") as f:
            json.dump(products, f, indent=2)
            
    return {"status": "success"}


# ── Events ──────────────────────────────────────────────────────────────

@app.get("/api/events")
async def get_events(limit: int = 50, event_type: Optional[str] = None):
    """Get system events."""
    with db._connect() as conn:
        query = "SELECT * FROM system_events WHERE 1=1"
        params = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ── Actions ──────────────────────────────────────────────────────────────

@app.post("/api/actions/sync")
async def trigger_sync():
    """Trigger Google Drive sync."""
    try:
        from sync_drive import DriveSyncer
        syncer = DriveSyncer({
            "rclone_remote": CONFIG["google_drive"]["rclone_remote"],
            "remote_path": CONFIG["google_drive"]["remote_path"],
            "products_file": CONFIG["google_drive"]["products_file"],
            "raw_dir": CONFIG["content"]["raw_dir"],
            "min_stock_warning": CONFIG["content"].get("min_stock_warning", 5),
        }, db)
        success, stock_report = syncer.sync()
        return {"success": success, "stock_report": stock_report}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/actions/test-proxy")
async def test_proxy():
    """Test proxy connection and verify exit IP."""
    import httpx
    proxy_url = CONFIG.get("proxy", {}).get("endpoint", "")
    if not proxy_url or proxy_url == "http://USER:PASS@HOST:PORT":
        return {"success": False, "message": "Proxy not configured"}

    try:
        proxies = {"http://": proxy_url, "https://": proxy_url}
        resp = httpx.get("https://ipinfo.io/json", proxies=proxies, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        expected = CONFIG.get("proxy", {}).get("expected_country", "MY")
        is_ok = data.get("country") == expected

        return {
            "success": is_ok,
            "message": f"IP: {data.get('ip')} | Country: {data.get('country')} | Org: {data.get('org')}",
            "data": data,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/actions/cookie-status")
async def cookie_status():
    """Check TikTok cookie age and validity."""
    return get_cookie_status()


@app.post("/api/actions/relogin")
async def trigger_relogin():
    """Trigger QR code login for TikTok cookies."""
    try:
        session_user = CONFIG.get("tiktok", {}).get("session_username", "myshop")
        uploader_dir = CONFIG.get("tiktok", {}).get("uploader_dir", "/opt/TiktokAutoUploader")

        qr_script = PROJECT_ROOT / "scripts" / "qr_login.py"
        if not qr_script.exists():
            return {"success": False, "message": "QR login script not found"}

        # Get proxy from config (CRITICAL: login must use same proxy as uploads)
        proxy_url = CONFIG.get("proxy", {}).get("endpoint", "")
        if not proxy_url or proxy_url == "http://USER:PASS@HOST:PORT":
            proxy_url = None

        import subprocess
        cmd = [
            sys.executable, str(qr_script),
            session_user,
            "--uploader-dir", str(uploader_dir),
            "--timeout", "120",
        ]
        if proxy_url:
            cmd.extend(["--proxy", proxy_url])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=130)

        if result.returncode == 0:
            # Find QR image
            import glob
            qr_files = glob.glob("/tmp/tiktok_qr_*.png")
            qr_path = None
            if qr_files:
                qr_path = max(qr_files, key=os.path.getctime)

            return {
                "success": True,
                "message": result.stdout,
                "qr_path": qr_path,
            }
        else:
            return {"success": False, "message": result.stderr[:500]}

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "QR login timed out (120s)"}
    except Exception as e:
        return {"success": False, "message": str(e)[:500]}


@app.get("/api/qr-image")
async def get_qr_image(path: str = Query(...)):
    """Serve QR code image for web display."""
    # Security: only allow files in /tmp that match the pattern
    import re
    if not re.match(r'^/tmp/tiktok_qr_[\w_]+\.png$', path):
        raise HTTPException(403, "Invalid path")

    if not os.path.exists(path):
        raise HTTPException(404, "QR image not found")

    return FileResponse(path, media_type="image/png")


# ── Reports & queue (Phase 3 additions) ─────────────────────────────────

def _read_report(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None


@app.get("/api/growth-report")
async def growth_report():
    """Cached growth analysis from ai_growth.py (growth_report.txt)."""
    import lib as _lib
    text = _read_report(_lib.growth_report())
    return {"exists": text is not None, "report": text or "(no growth report yet - run ai_growth.py --ai)"}


@app.get("/api/ops-report")
async def ops_report():
    """Daily OPS report from generate_report.py (daily_report.txt)."""
    import lib as _lib
    text = _read_report(_lib.daily_report())
    return {"exists": text is not None, "report": text or "(no ops report yet - run generate_report.py)"}


@app.get("/api/queue-status")
async def queue_status():
    """Upload queue: rendered videos with their sidecar metadata."""
    import lib as _lib
    from sidecar_manager import SidecarManager
    manager = SidecarManager(_lib.queue_dir())
    items = []
    for mp4, _primary, meta in manager.find():
        items.append({
            "filename": mp4.name,
            "product_folder": meta.get("product_folder", ""),
            "product_id": meta.get("product_id", ""),
            "title": meta.get("title", ""),
            "size_mb": meta.get("file_size_mb"),
            "style": meta.get("style_name"),
            "processed_at": meta.get("processed_at"),
        })
    return {"count": len(items), "items": items}


@app.get("/api/analytics")
async def analytics(days: int = 7):
    """Chart data from the analytics schema (views over time, by product).

    Reads the same logs/tiktok.db analytics tables that reconcile_metrics,
    ai_growth and generate_report use. Returns empty series on a fresh install
    so the frontend can show "no data yet" instead of erroring.
    """
    import lib as _lib
    conn = _lib.get_conn()
    _lib.ensure_schema(conn)
    since = (_lib.local_today() - timedelta(days=days)).isoformat()

    views_by_day = [dict(r) for r in conn.execute(
        """SELECT snap_date, SUM(views) AS views
           FROM daily_metrics WHERE snap_date >= ?
           GROUP BY snap_date ORDER BY snap_date""", (since,))]

    # Net-new views per day (difference from the previous snapshot total).
    deltas = []
    prev = 0
    for row in views_by_day:
        cur = int(row["views"] or 0)
        deltas.append({"date": row["snap_date"], "views": max(0, cur - prev)})
        prev = cur

    product_views = [dict(r) for r in conn.execute(
        """WITH latest AS (
               SELECT video_id, views,
                      ROW_NUMBER() OVER (PARTITION BY video_id
                                         ORDER BY snap_date DESC) AS rn
               FROM daily_metrics WHERE snap_date >= ?
           )
           SELECT COALESCE(NULLIF(v.product_folder,''),'(unassigned)') AS product,
                  CAST(SUM(l.views) AS INTEGER) AS views
           FROM latest l JOIN videos v ON v.video_id = l.video_id
           WHERE l.rn = 1
           GROUP BY product_folder ORDER BY views DESC""", (since,))]

    posts_by_day = [dict(r) for r in conn.execute(
        """SELECT substr(posted_at,1,10) AS day, COUNT(*) AS n
           FROM videos WHERE posted_at >= ?
           GROUP BY day ORDER BY day""", (since,))]
    conn.close()

    return {
        "views_by_day": views_by_day,
        "views_delta_by_day": deltas,
        "product_views": product_views,
        "posts_by_day": posts_by_day,
        "days": days,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Helpers ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def save_config(config: dict):
    # Write to temp file first, then atomic rename
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False,
                                      dir=str(CONFIG_PATH.parent)) as tmp:
        yaml.dump(config, tmp, default_flow_style=False, sort_keys=False)
        tmp_path = tmp.name
    shutil.move(tmp_path, str(CONFIG_PATH))

def mask_secret(value: str) -> str:
    if not value or len(value) < 8:
        return "***"
    return value[:4] + "..." + value[-4:]


def get_drive_cleanup_status() -> dict:
    """Minimal Drive-cleanup indicator: raws deleted from Drive today + pending.

    'pending' = consumed raws whose Drive copy hasn't been deleted yet (will be
    retried by sync_out). 'deleted_today' = lines in drive_cleanup.log stamped
    on today's date (business timezone MYT).
    """
    try:
        import lib as _lib
        # Pending deletes (consumed but not yet removed from Drive).
        pending = len(_lib.consumed_pending_cleanup())
        # Cleaned today from the audit log.
        today = _lib.local_today().isoformat()
        deleted_today = 0
        cl = _lib.drive_cleanup_log()
        if cl.exists():
            for line in cl.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith(today):
                    deleted_today += 1
        return {"pending": pending, "deleted_today": deleted_today}
    except Exception:
        return {"pending": 0, "deleted_today": 0}

def get_cookie_status() -> dict:
    session_user = CONFIG.get("tiktok", {}).get("session_username", "myshop")
    uploader_dir = CONFIG.get("tiktok", {}).get("uploader_dir", "/opt/TiktokAutoUploader")
    cookie_path = os.path.join(uploader_dir, "CookiesDir", f"tiktok_session-{session_user}.cookie")

    if not os.path.exists(cookie_path):
        return {"exists": False, "message": "Cookie file not found"}

    mtime = os.path.getmtime(cookie_path)
    age_days = (time.time() - mtime) / 86400
    max_age = CONFIG.get("tiktok", {}).get("cookie_max_age_days", 7)

    return {
        "exists": True,
        "age_days": round(age_days, 1),
        "max_age_days": max_age,
        "needs_refresh": age_days > max_age,
        "path": cookie_path,
    }


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("WEBAPP_PORT", "8080"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
