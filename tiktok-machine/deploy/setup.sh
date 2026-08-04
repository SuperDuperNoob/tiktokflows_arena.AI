#!/usr/bin/env bash
# =============================================================================
# TikTok Auto-Posting Machine — Deployment Script
# =============================================================================
# Run this as root on the VPS to set up the full system.
# Prerequisites: Debian 11+, internet access
# =============================================================================
set -euo pipefail

echo "============================================================"
echo " TikTok Auto-Posting Machine — Deployment"
echo "============================================================"
echo ""

PROJECT_DIR="/opt/tiktok-machine"
UPLOADER_DIR="/opt/TiktokAutoUploader"
SERVICE_USER="tiktok"

# ---- 1. System dependencies ----
echo "[1/8] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    ffmpeg \
    rclone \
    curl \
    git \
    fonts-noto-color-emoji \
    fonts-noto \
    fonts-dejavu-core \
    wget \
    unzip \
    > /dev/null 2>&1
echo "  ✓ System packages installed (including Noto Color Emoji fonts)"

# ---- 1b. Install web fonts for Skia overlay rendering ----
# Skia uses system fonts. We install the same fonts that Playwright would
# load from Google Fonts, so Skia is the only renderer needed (~30MB RAM
# vs ~400MB for Playwright). On a 4GB VPS this matters.
echo "[1b/8] Installing web fonts for text overlay..."
FONT_DIR="/usr/local/share/fonts/tiktok"
mkdir -p "$FONT_DIR"

install_google_font() {
    local name="$1"
    local url="$2"
    if ls "$FONT_DIR"/${name}*.ttf 1>/dev/null 2>&1; then
        echo "  ✓ $name already installed"
        return
    fi
    local tmp=$(mktemp -d)
    wget -q "$url" -O "$tmp/${name}.zip" 2>/dev/null && \
    unzip -qo "$tmp/${name}.zip" -d "$tmp/${name}" 2>/dev/null && \
    find "$tmp/${name}" -name "*.ttf" -exec cp {} "$FONT_DIR/" \; && \
    echo "  ✓ $name installed" || echo "  ⚠ $name download failed (non-critical)"
    rm -rf "$tmp"
}

# Google Fonts static download URLs (unhinted TTF)
install_google_font "Outfit" "https://fonts.google.com/download?family=Outfit"
install_google_font "Inter" "https://fonts.google.com/download?family=Inter"
install_google_font "Montserrat" "https://fonts.google.com/download?family=Montserrat"
install_google_font "Poppins" "https://fonts.google.com/download?family=Poppins"
install_google_font "PlusJakartaSans" "https://fonts.google.com/download?family=Plus+Jakarta+Sans"

# Refresh font cache
fc-cache -f "$FONT_DIR" 2>/dev/null || true
echo "  ✓ Font cache refreshed"

# ---- 2. Node.js (for TiktokAutoUploader signature generation) ----
echo "[2/8] Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "  Installing Node.js 18..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - > /dev/null 2>&1
    apt-get install -y -qq nodejs > /dev/null 2>&1
fi
NODE_VER=$(node --version)
echo "  ✓ Node.js $NODE_VER"

# ---- 3. Create system user ----
echo "[3/8] Creating system user '$SERVICE_USER'..."
if ! id "$SERVICE_USER" &> /dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    echo "  ✓ User created"
else
    echo "  ✓ User already exists"
fi

# ---- 4. Set up project directory ----
echo "[4/8] Setting up project directory..."
mkdir -p "$PROJECT_DIR"
# Copy project files (assumes you've placed them here)
if [ -d "$(dirname "$0")/../tiktok-machine" ]; then
    cp -r "$(dirname "$0")/../tiktok-machine/"* "$PROJECT_DIR/"
fi
mkdir -p "$PROJECT_DIR"/{content/{raw,processed,posted,failed},captions,sounds,logs,config}
echo "  ✓ Project directory ready"

# ---- 5. Python virtualenv ----
echo "[5/8] Setting up Python virtualenv..."
python3 -m venv "$PROJECT_DIR/venv"
"$PROJECT_DIR/venv/bin/pip" install --quiet --upgrade pip
"$PROJECT_DIR/venv/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"
echo "  ✓ Virtualenv ready"

# ---- 6. TiktokAutoUploader setup ----
echo "[6/8] Setting up TiktokAutoUploader..."
if [ -d "$UPLOADER_DIR" ]; then
    echo "  ✓ TiktokAutoUploader already exists at $UPLOADER_DIR"
    # Install its Python deps into our venv so the orchestrator can import it
    "$PROJECT_DIR/venv/bin/pip" install --quiet -r "$UPLOADER_DIR/requirements.txt" 2>/dev/null || true

    # Install Node.js dependencies for signature generation
    if [ -d "$UPLOADER_DIR/tiktok_uploader/tiktok-signature" ]; then
        cd "$UPLOADER_DIR/tiktok_uploader/tiktok-signature"
        npm install --silent 2>/dev/null || true
        npx playwright install chromium 2>/dev/null || true
        cd "$PROJECT_DIR"
        echo "  ✓ Signature dependencies installed"
    fi

    # Create required directories
    mkdir -p "$UPLOADER_DIR"/{CookiesDir,VideosDirPath,output}
else
    echo "  ⚠️  TiktokAutoUploader not found at $UPLOADER_DIR"
    echo "  Please clone it: git clone <repo> $UPLOADER_DIR"
fi

# ---- 7. Permissions ----
echo "[7/8] Setting permissions..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"
# Allow tiktok user to read TiktokAutoUploader
chmod -R o+rX "$UPLOADER_DIR" 2>/dev/null || true
echo "  ✓ Permissions set"

# ---- 8. Install systemd services ----
echo "[8/8] Installing systemd services..."

# Main orchestrator
cp "$PROJECT_DIR/deploy/tiktok-machine.service" /etc/systemd/system/

# Web interface
cp "$PROJECT_DIR/deploy/tiktok-webapp.service" /etc/systemd/system/

# Cloudflare Tunnel (token must be set manually)
cp "$PROJECT_DIR/deploy/cloudflared.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable tiktok-machine
systemctl enable tiktok-webapp
echo "  ✓ Services installed: tiktok-machine, tiktok-webapp"

# Install cloudflared if not present
if ! command -v cloudflared &> /dev/null; then
    echo "  Installing cloudflared..."
    curl -L --output /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb"
    apt install -y /tmp/cloudflared.deb > /dev/null 2>&1
    rm /tmp/cloudflared.deb
    echo "  ✓ cloudflared installed"
else
    echo "  ✓ cloudflared already installed"
fi

echo ""
echo "============================================================"
echo " ✅ Deployment complete!"
echo "============================================================"
echo ""
echo " NEXT STEPS:"
echo ""
echo " 1. Edit configuration:"
echo "    nano $PROJECT_DIR/config/config.yaml"
echo "    → Set Telegram bot token and user ID"
echo "    → Set Cliproxy proxy endpoint"
echo "    → Set AI API key and base URL"
echo "    → Set Apify token"
echo "    → Configure product details"
echo ""
echo " 2. Set up rclone for Google Drive:"
echo "    rclone config"
echo "    → Create a remote named 'gdrive' (type: drive)"
echo "    → Follow the OAuth flow"
echo ""
echo " 3. Edit products.json:"
echo "    nano $PROJECT_DIR/content/products.json"
echo "    → Map folder names to TikTok Shop product IDs"
echo ""
echo " 4. Login to TikTok (see docs/cookie_login_guide.md):"
echo "    Option A: Browser extension export (recommended)"
echo "      → Export cookies from your browser"
echo "      → python3 $PROJECT_DIR/scripts/import_cookies.py myshop /tmp/cookies.json"
echo "    Option B: QR code headless login"
echo "      → pip3 install playwright && playwright install chromium"
echo "      → python3 $PROJECT_DIR/scripts/qr_login.py myshop"
echo "      → Scan QR with TikTok app"
echo ""
echo " 5. Add background music to sounds/ directory:"
echo "    cp /path/to/royalty-free/*.mp3 $PROJECT_DIR/sounds/"
echo "    → Add at least 20 tracks for variety"
echo ""
echo " 6. Set up Cloudflare Tunnel (no open ports!):"
echo "    a. Go to https://one.dash.cloudflare.com/"
echo "    b. Create a tunnel → copy the token"
echo "    c. Edit the tunnel service:"
echo "       sudo nano /etc/systemd/system/cloudflared.service"
echo "       → Replace YOUR_CLOUDFLARE_TUNNEL_TOKEN with your token"
echo "    d. Enable and start:"
echo "       sudo systemctl enable cloudflared"
echo "       sudo systemctl start cloudflared"
echo "    e. In Cloudflare dashboard, route your domain to:"
echo "       http://localhost:8080"
echo ""
echo " 7. Start services:"
echo "    sudo systemctl start tiktok-machine"
echo "    sudo systemctl start tiktok-webapp"
echo "    sudo systemctl status tiktok-machine"
echo "    sudo systemctl status tiktok-webapp"
echo ""
echo " 8. Access the web interface:"
echo "    → Via Cloudflare Tunnel: https://your-domain.com"
echo "    → Or locally: http://localhost:8080"
echo ""
echo " 9. View logs:"
echo "    journalctl -u tiktok-machine -f      # Main orchestrator"
echo "    journalctl -u tiktok-webapp -f       # Web interface"
echo "    journalctl -u cloudflared -f         # Tunnel logs"
echo ""
echo "============================================================"
