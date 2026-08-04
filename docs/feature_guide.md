# TikTok Auto-Posting Machine - Feature Guide

## 1. Cookie Re-login via QR Code

You can now refresh TikTok cookies without SSH access using QR codes via:
- **Telegram bot** (`/relogin` command)
- **Web dashboard** (Tools tab → QR Code Re-login)

### CRITICAL: Proxy Routing for Login

**The QR login routes through your Cliproxy proxy automatically.** This is essential for account safety:

```
CORRECT FLOW (with proxy):
──────────────────────────────────────────────┐
│  QR Login (via Playwright + Cliproxy proxy)  │
│  → Malaysian residential IP                  │
│  → TikTok sees: "login from MY residential"  │
└──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│  Upload (TiktokAutoUploader + Cliproxy)      │
│  → Malaysian residential IP (same proxy)     │
│  → TikTok sees: "upload from MY residential" │
└──────────────────────────────────────────────┘

✅ Login IP = Upload IP → No red flags
```

**Without proxy (DANGEROUS):**
```
WRONG FLOW (no proxy):
  Login → VPS direct IP (Singapore datacenter)
  Upload → Cliproxy (Malaysian residential)
  
  TikTok sees: Different country + network type
  → High ban risk
```

The proxy is auto-detected from `config.yaml` → `proxy.endpoint`. No extra configuration needed.

### How It Works

1. Trigger re-login (Telegram or Web)
2. System launches headless Chromium **through your proxy**
3. QR code image generated (takes ~5 seconds)
4. QR code is sent/displayed to you
5. Scan with TikTok app on your phone (expires in 60 seconds)
6. Cookies are automatically saved to VPS
7. You receive confirmation message

### Via Telegram

```
/relogin
```

**What happens:**
- Bot sends: " Starting QR code login..."
- After ~5 seconds: QR image sent to chat
- Caption: " Scan this QR code with TikTok app (Expires in 60 seconds)"
- After scan: Success/failure message

### Via Web Dashboard

1. Go to **Tools** tab
2. Click **"Generate QR Code"** button
3. Wait ~5 seconds
4. QR image appears inline
5. Scan with TikTok app
6. Result message appears below

### When to Re-login

- Cookie age > 7 days (Telegram alert sent automatically)
- Upload failures with "session expired" errors
- Every ~30 days as preventive maintenance

### Troubleshooting

| Issue | Solution |
|---|---|
| QR code not generated | Check Playwright installed: `pip3 install playwright && playwright install chromium` |
| QR expires before scanning | Run command again, have TikTok app ready |
| Scan successful but cookies not saved | Check file permissions on CookiesDir |
| Timeout error | Increase timeout in qr_login.py (--timeout parameter) |

---

## 2. Text Overlay Style Control

### Style Randomization (Default)

By default, each video upload gets a **random style** from 8 TikTok-native options:

| Style | Weight | Description |
|---|---|---|
| `classic_yellow` | 30% | Gold text, 8px black outline, hard shadow |
| `bold_white` | 25% | White text, thick black outline + shadow |
| `bright_yellow` | 15% | Bright yellow, extra-thick 10px outline |
| `tiktok_red` | 10% | TikTok brand red, white keyline |
| `white_yellow_glow` | 8% | White with yellow outer glow |
| `yellow_red_shadow` | 7% | Gold with red shadow accent |
| `white_on_black_box` | 5% | White text on semi-transparent black box |
| `fire_urgency` | 5% | Orange-red with yellow glow (urgency CTA) |

**Example:** Over 100 uploads, you'd see approximately:
- 30 classic_yellow
- 25 bold_white
- 15 bright_yellow
- 10 tiktok_red
- 8 white_yellow_glow
- 7 yellow_red_shadow
- 5 white_on_black_box
- 5 fire_urgency

This variety helps avoid TikTok's duplicate content detection.

### Force a Specific Style

To use **only one style** for all uploads (e.g., for brand consistency):

**Edit config.yaml:**
```yaml
rendering:
  force_style: "classic_yellow"  # or any style name
```

**Available style names:**
- `classic_yellow`
- `bold_white`
- `bright_yellow`
- `tiktok_red`
- `white_yellow_glow`
- `yellow_red_shadow`
- `white_on_black_box`
- `fire_urgency`

**To return to random:**
```yaml
rendering:
  force_style: null
```

### View Style Usage

**Via Web Dashboard:**
- Go to **Posts** tab
- Check "Style" column (if added to table)
- Or check **Events** tab for style info in metadata

**Via Database:**
```bash
sqlite3 /opt/tiktok-machine/logs/tiktok.db

-- Show style distribution
SELECT json_extract(notes, '$.style_name') as style, COUNT(*) as count
FROM posts
WHERE notes IS NOT NULL
GROUP BY style
ORDER BY count DESC;
```

### Style Recommendations

| Use Case | Recommended Style |
|---|---|
| General products | `classic_yellow` (most recognizable) |
| Beauty/skincare | `white_yellow_glow` (warm, inviting) |
| Urgency/CTA | `fire_urgency` or `tiktok_red` |
| Long captions | `white_on_black_box` (readability) |
| Maximum visibility | `bright_yellow` (extra-thick outline) |

---

## 3. Quick Reference

### Telegram Commands

| Command | Purpose |
|---|---|
| `/status` | Check system status |
| `/relogin` | Generate QR code to refresh cookies |
| `/pause` | Pause posting |
| `/resume` | Resume posting |
| `/force <product>` | Force next upload to specific product |

### Web Dashboard Tabs

| Tab | Purpose |
|---|---|
| Dashboard | Overview, stats, recent activity |
| Posts | View all posts, filter by product/status |
| Captions | Manage caption pool |
| Products | View product stock levels |
| Config | Edit configuration inline |
| Events | System event log |
| Tools | Proxy test, sync, cookie status, **QR re-login** |

### Config Options (rendering section)

```yaml
rendering:
  preferred_renderer: "skia"      # skia or playwright
  font_size_min: 62               # Minimum font size (px)
  font_size_max: 82               # Maximum font size (px)
  overlay_y_min: 0.35             # Top position (35% from top)
  overlay_y_max: 0.50             # Bottom position (50% from top)
  accent_rate: 0.15               # 15% chance of red accent
  force_style: null               # null=random, or style name
```

---

## 4. Troubleshooting

### QR Code Issues

**Problem:** QR code not generating
```bash
# Check Playwright installation
pip3 show playwright
playwright install chromium

# Test QR script manually
python3 /opt/tiktok-machine/scripts/qr_login.py myshop --timeout 30
```

**Problem:** QR code expires too quickly
- Have TikTok app open and ready before generating QR
- Stand close to phone for faster scanning
- Consider increasing timeout if needed

### Style Issues

**Problem:** All videos have same style
- Check `force_style` in config.yaml (should be `null` for random)
- Restart orchestrator after config change: `sudo systemctl restart tiktok-machine`

**Problem:** Emoji not rendering in overlay
- Check fonts installed: `fc-list | grep -i noto`
- Install emoji font: `sudo apt install fonts-noto-color-emoji`
- Verify Skia can load font (check logs)

### Cookie Issues

**Problem:** Re-login succeeds but uploads still fail
- Check cookie file exists: `ls -la /opt/TiktokAutoUploader/CookiesDir/`
- Verify sessionid present: `python3 -c "import pickle; c=pickle.load(open('/opt/TiktokAutoUploader/CookiesDir/tiktok_session-myshop.cookie','rb')); print([x['name'] for x in c])"`
- Should show: `['sessionid', 'tt-target-idc']`

**Problem:** Cookies expire too quickly
- TikTok sessions typically last 30 days
- If expiring faster, check for IP changes or multiple login sessions
- Consider re-login every 25 days as preventive measure

---

## 5. Maintenance Schedule

### Daily
- Check Telegram for alerts (stock low, cookie warning, upload failures)
- Review web dashboard for today's post count

### Weekly
- Review caption performance (which captions get most views)
- Check stock levels, add new videos if < 5 per product
- Test proxy connection (web dashboard → Tools → Proxy Test)

### Monthly (or when alerted)
- Re-login via QR code (Telegram `/relogin` or web dashboard)
- Review AI strategy (`/growth` command)
- Clean up old processed videos if disk space low
- Check competitor data for new trends

---

## 6. Support

For issues or questions:
1. Check this guide first
2. Review logs: `sudo journalctl -u tiktok-machine -f`
3. Check web dashboard Events tab
4. Verify all services running: `sudo systemctl status tiktok-machine tiktok-webapp cloudflared`
