#!/usr/bin/env bash
# =============================================================================
# migrate_from_vps.sh - migrate from the legacy tiktokflow_vps (n8n/Docker)
# to the unified tiktok-machine deployment.
#
# What it does:
#   1. Backs up the existing tiktokflow_vps installation
#   2. Installs tiktok-machine to /opt/tiktok-machine
#   3. Migrates config (.env -> config.yaml), cookies, products (product_id.txt
#      -> products.json), and the caption pool (preset_text.txt)
#   4. Starts the systemd services and verifies they are running
#
# Rollback: docs/rollback.md
#
# Usage:
#   sudo bash deploy/migrate_from_vps.sh
# =============================================================================
set -euo pipefail

NEW_DIR="/opt/tiktok-machine"
LEGACY_DIR="${LEGACY_DIR:-/home/archery/tiktokflow}"          # old n8n install
LEGACY_DRIVE="${LEGACY_DRIVE:-$LEGACY_DIR/tiktokflow_drive}"  # drive root with products
BACKUP_DIR="${BACKUP_DIR:-/opt/tiktokflow_backup}"
SERVICE_USER="tiktok"
SRC="${SRC:-$(cd "$(dirname "$0")/.." && pwd)}"               # this repo's tiktok-machine

log()  { echo -e "\033[1;32m[migrate]\033[0m $*"; }
warn() { echo -e "\033[1;33m[migrate]\033[0m WARNING: $*"; }
die()  { echo -e "\033[1;31m[migrate]\033[0m ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root (sudo bash migrate_from_vps.sh)"

# ---------------------------------------------------------------- backup ----
TS=$(date +%Y%m%d_%H%M%S)
log "1/8 Backing up legacy tiktokflow_vps -> $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
if [[ -d "$LEGACY_DIR" ]]; then
    cp -a "$LEGACY_DIR" "$BACKUP_DIR/tiktokflow_vps_$TS" || true
fi
if [[ -f "$LEGACY_DIR/.env" ]]; then
    cp -a "$LEGACY_DIR/.env" "$BACKUP_DIR/.env_$TS" || true
fi
log "   Backup complete."

# ---------------------------------------------------------------- install ----
log "2/8 Installing tiktok-machine -> $NEW_DIR"
mkdir -p "$NEW_DIR"
# Copy source excluding generated/venv dirs.
rsync -a --exclude 'venv' --exclude '__pycache__' --exclude 'logs/' \
      --exclude 'content/raw' --exclude 'content/processed' \
      --exclude 'content/failed' --exclude '.git' "$SRC/" "$NEW_DIR/" || {
    # fallback if rsync missing
    cp -a "$SRC/." "$NEW_DIR/"
}
mkdir -p "$NEW_DIR/logs" "$NEW_DIR/content/raw" "$NEW_DIR/sounds"

if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home "$NEW_DIR" "$SERVICE_USER" || true
fi
chown -R "$SERVICE_USER":"$SERVICE_USER" "$NEW_DIR"

# ------------------------------------------------------------- python venv ---
log "3/8 Creating Python venv + installing deps"
if [[ ! -d "$NEW_DIR/venv" ]]; then
    python3 -m venv "$NEW_DIR/venv"
fi
"$NEW_DIR/venv/bin/pip" install --quiet --upgrade pip
"$NEW_DIR/venv/bin/pip" install --quiet -r "$NEW_DIR/requirements.txt" || \
    warn "requirements install had issues (check output); continuing"

# ------------------------------------------------------------ config merge ---
log "4/8 Migrating config (.env -> config.yaml)"
CFG="$NEW_DIR/config/config.yaml"
if [[ -f "$CFG" ]]; then
    # Fill in values from the legacy .env if the config placeholders are empty.
    LEGACY_ENV="$BACKUP_DIR/.env_$TS"
    [[ -f "$LEGACY_ENV" ]] || LEGACY_ENV="$LEGACY_DIR/.env"
    if [[ -f "$LEGACY_ENV" ]]; then
        set -a; source "$LEGACY_ENV"; set +a
        sed -i \
          -e "s|^  session_username: .*|  session_username: \"${TIKTOK_SESSION_USER:-kumpul.shop}\"|" \
          -e "s|^  endpoint: \"\"|  endpoint: \"${TIKTOK_PROXY:-}\"|" \
          -e "s|^  api_key: \"\"|  api_key: \"${AI_API_KEY:-}\"|" \
          -e "s|^  bot_token: \"\"|  bot_token: \"${TELEGRAM_BOT_TOKEN:-}\"|" \
          -e "s|^  chat_id: \"\"|  chat_id: \"${TELEGRAM_CHAT_ID:-}\"|" \
          "$CFG"
        log "   Config values copied from legacy .env."
    fi
else
    warn "config.yaml not found at $CFG - create it from the repo."
fi

# ---------------------------------------------------------------- cookies ----
log "5/8 Migrating TikTok cookies"
LEGACY_COOKIES="$LEGACY_DIR/TiktokAutoUploader/CookiesDir"
NEW_COOKIES="$NEW_DIR/TiktokAutoUploader/CookiesDir"
if [[ -d "$LEGACY_COOKIES" ]]; then
    mkdir -p "$NEW_COOKIES"
    cp -a "$LEGACY_COOKIES/." "$NEW_COOKIES/" || true
    chown -R "$SERVICE_USER":"$SERVICE_USER" "$NEW_COOKIES"
    log "   Cookies copied from $LEGACY_COOKIES"
else
    warn "No legacy cookie dir found - run qr_login.py / import_cookies.py after migration."
fi

# --------------------------------------------------------------- products ----
log "6/8 Migrating products (product_id.txt) + caption pool (preset_text.txt)"
if [[ -f "$LEGACY_DRIVE/product_id.txt" ]]; then
    # Keep the plain-text mapping in the new layout too (video_processor reads it).
    mkdir -p "$NEW_DIR/content/raw"
    cp -a "$LEGACY_DRIVE/product_id.txt" "$NEW_DIR/content/raw/product_id.txt"
    # Build products.json from the same file for the web dashboard.
    "$NEW_DIR/venv/bin/python" - "$LEGACY_DRIVE/product_id.txt" "$NEW_DIR/content/products.json" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
out = {}
try:
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//") or "|" not in line:
                continue
            p = [x.strip() for x in line.split("|")]
            if len(p) >= 2:
                out[p[0]] = p[1]
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[migrate] wrote {dst} with {len(out)} products")
except FileNotFoundError:
    pass
PY
fi
if [[ -f "$LEGACY_DRIVE/preset_text.txt" ]]; then
    cp -a "$LEGACY_DRIVE/preset_text.txt" "$NEW_DIR/content/raw/preset_text.txt"
fi

# ------------------------------------------------------------- services -----
log "7/8 Installing + starting systemd services"
for unit in tiktok-machine tiktok-webapp cloudflared; do
    cp "$NEW_DIR/deploy/$unit.service" "/etc/systemd/system/$unit.service"
done
systemctl daemon-reload
systemctl enable --now tiktok-machine tiktok-webapp cloudflared || \
    warn "some services failed to start - see 'systemctl status'"

# ------------------------------------------------------------ verification ----
log "8/8 Verifying services"
sleep 5
FAIL=0
for unit in tiktok-machine tiktok-webapp cloudflared; do
    if systemctl is-active --quiet "$unit"; then
        log "   ✓ $unit is ACTIVE"
    else
        warn "$unit is NOT active - run: systemctl status $unit"
        FAIL=1
    fi
done
if [[ $FAIL -eq 0 ]]; then
    log "Migration complete. Point Cloudflare Tunnel at 127.0.0.1:8080."
    log "Rollback: see docs/rollback.md"
else
    warn "Migration finished with service warnings - inspect before relying on it."
fi
