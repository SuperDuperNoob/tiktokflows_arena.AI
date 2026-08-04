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
from compliance_engine import ComplianceEngine

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
    source: str = "manual"

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

    return {
        "posted_today": posted_today,
        "daily_target": target,
        "stock_counts": stock_counts,
        "products_due": products_due,
        "recent_events": recent_events,
        "recent_posts": recent_posts,
        "performance": perf,
        "cookie_status": cookie_status,
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
            products = json.load(f)

    # Merge with config product details
    config_products = CONFIG.get("products", {})
    result = []
    for name, product_id in products.items():
        detail = config_products.get(name, {})
        stock = db.get_raw_stock_counts().get(name, 0)
        result.append({
            "name": name,
            "product_id": product_id,
            "description": detail.get("description", ""),
            "keywords": detail.get("keywords", []),
            "stock": stock,
        })

    return result


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
