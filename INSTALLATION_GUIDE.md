# Installation Guide

## System Requirements

### Hardware
- CPU: 2+ cores (4+ recommended for parallel processing)
- RAM: 4 GB minimum (8 GB recommended)
- Disk: 20 GB free space (SSD recommended)
- Network: Stable internet connection (10+ Mbps upload)

### Software
- OS: Linux (Ubuntu 22.04+, Debian 12+, CentOS 8+)
- Python: 3.11 or 3.12
- Git: 2.30+
- System packages: ffmpeg, rclone, sqlite3, python3-venv

### External Dependencies
- Residential/4G proxy (Malaysian IP required)
- TikTok account with TikTok Shop access
- Apify account with API token
- Telegram bot (optional, for notifications)
- OpenAI-compatible API key (optional, for AI captions)

## Installation Steps

### 1. Clone Repository
```bash
git clone https://github.com/SuperDuperNoob/tiktokflows_arena.AI.git
cd tiktokflows_arena.AI
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Install System Dependencies
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y \
    ffmpeg rclone sqlite3 python3-venv python3-dev \
    build-essential libssl-dev libffi-dev \
    fonts-noto-color-emoji fonts-dejavu-core

# CentOS/RHEL
sudo dnf install -y \
    ffmpeg rclone sqlite3 python3-venv python3-devel \
    gcc openssl-devel libffi-devel \
    google-noto-emoji-fonts dejavu-fonts-common
```

### 4. Configure Application
```bash
# Copy example config
cp config/config.yaml.example config/config.yaml

# Edit config with your settings
# Required: proxy.endpoint, ai.api_key, apify.token, telegram.bot_token
vim config/config.yaml
```

### 5. Set Environment Variables
```bash
# Copy example
cp .env.example .env

# Edit with your secrets
vim .env

# Required variables:
# TIKTOK_PROXY, OPENAI_API_KEY, APIFY_TOKEN, TELEGRAM_BOT_TOKEN
# TIKTOK_MACHINE_CONFIG=config/config.yaml
```

### 6. Initialize Database
```bash
# Database will be created automatically on first run
# Or initialize manually:
export TIKTOK_MACHINE_CONFIG=config/config.yaml
export TESTING=0
python -c "from services.infrastructure.database import Database; Database('logs/tiktok.db')"
```

### 5. Set Up TikTok AutoUploader
```bash
cd TiktokAutoUploader
# Follow TiktokAutoUploader setup instructions
# Run QR login to generate cookies:
python3 ../scripts/qr_login.py <username> --uploader-dir $(pwd)
```

### 6. Configure Google Drive (Optional)
```bash
# Install and configure rclone
rclone config
# Create remote named "gdrive" pointing to your Google Drive folder

# Update config.yaml:
# google_drive:
#   rclone_remote: "gdrive"
#   remote_path: "TikTokContent"
```

### 6. Test Installation
```bash
# Run tests
export TIKTOK_MACHINE_CONFIG=config/config.yaml
export TESTING=1
python -m pytest tests/ -v

# Test orchestrator startup (runs for 5 seconds)
timeout 5 python scripts/orchestrator.py
```

### 7. Deploy as Service (Production)
```bash
# Copy systemd service file
sudo cp deploy/tiktok-machine.service /etc/systemd/system/

# Edit service file with correct paths
sudo vim /etc/systemd/system/tiktok-machine.service

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable tiktok-machine
sudo systemctl start tiktok-machine

# Check status
systemctl status tiktok-machine
```

## Configuration Reference

### Required Secrets (in .env)
| Variable | Description | Example |
|----------|-------------|---------|
| TIKTOK_PROXY | Residential proxy URL | `http://user:pass@host:port` |
| OPENAI_API_KEY | OpenAI API key | `sk-...` |
| APIFY_TOKEN | Apify API token | `apify_api_...` |
| TELEGRAM_BOT_TOKEN | Telegram bot token | `123:...` |
| TELEGRAM_CHAT_ID | Telegram chat ID | `123456789` |

### Key Config Sections (config/config.yaml)
| Section | Key | Description |
|---------|-----|-------------|
| proxy.endpoint | Proxy URL | Residential proxy with credentials |
| proxy.strict_mode | Strict geo check | `true` (recommended) |
| ai.api_key | OpenAI API key | From OPENAI_API_KEY env |
| apify.token | Apify token | From APIFY_TOKEN env |
| telegram.bot_token | Bot token | From TELEGRAM_BOT_TOKEN env |
| logging.db_path | Database path | `logs/tiktok.db` |
| posting.daily_post_target | Daily post limit | `7` |

## Verification Checklist

After installation, verify:
- [ ] `python -m pytest tests/ -v` passes (62 tests)
- [ ] `timeout 5 python scripts/orchestrator.py` starts without errors
- [ ] Database created at `logs/tiktok.db`
- [ ] Logs show "Startup validation completed"
- [ ] Health check responds: `python -m scripts.operator_cli health`
- [ ] Cookie status shows valid: `python -m scripts.operator_cli cookie-status`

## Common Installation Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: skia_python` | Install system deps: `pip install skia-python` |
| `ffmpeg not found` | Install ffmpeg: `apt-get install ffmpeg` |
| `Config file not found` | Check TIKTOK_MACHINE_CONFIG path |
| `Proxy geo check failed` | Verify proxy is Malaysian residential |
| `Cookie expired` | Run `qr_login.py` to renew |
| `Database locked` | Ensure only one instance running |

## Updating
```bash
# Pull latest changes
git pull origin main

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Run migrations (automatic on startup)
# Restart service
sudo systemctl restart tiktok-machine
```

## Uninstalling
```bash
# Stop service
sudo systemctl stop tiktok-machine
sudo systemctl disable tiktok-machine

# Remove files
rm -rf /path/to/tiktokflows_arena.AI
sudo rm /etc/systemd/system/tiktok-machine.service
sudo systemctl daemon-reload
```