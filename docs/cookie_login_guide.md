# TikTok Cookie Login Guide

Two methods to get TikTok session cookies onto your VPS **without needing a GUI on the VPS**.

After login, you can manage everything via:
- **Telegram bot** — Quick commands (`/status`, `/pause`, `/force`)
- **Web dashboard** — Deep configuration at `https://your-domain.com` (Cloudflare Tunnel)

---

## Method 1: Browser Extension Export (Easiest)

**Do this on your home computer. No VPS access needed during login.**

### Step 1: Install Browser Extension

| Browser | Extension | Link |
|---|---|---|
| Chrome | EditThisCookie | [Install](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg) |
| Firefox | Cookie-Editor | [Install](https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/) |

### Step 2: Login to TikTok

1. Open https://tiktok.com in your browser
2. Log in normally (email/phone/password or QR code)
3. Stay on the TikTok page

### Step 3: Export Cookies

**Chrome (EditThisCookie):**
1. Click the cookie icon in your browser toolbar
2. Click the Export button (↓ arrow icon)
3. Save the JSON file as `tiktok_cookies.json`

**Firefox (Cookie-Editor):**
1. Click the cookie icon
2. Click "Export" → "Export as JSON"
3. Save as `tiktok_cookies.json`

### Step 4: Upload to VPS

```bash
scp tiktok_cookies.json archery@your-vps:/tmp/
```

### Step 5: Convert on VPS

SSH into your VPS and run:

```bash
python3 /home/archery/tiktokflow/tiktok-machine/scripts/import_cookies.py myshop /tmp/tiktok_cookies.json
```

Or manually:

```python
python3 << 'EOF'
import json, pickle, os

username = "myshop"
cookies_dir = "/home/archery/tiktokflow/TiktokAutoUploader/CookiesDir"
os.makedirs(cookies_dir, exist_ok=True)

with open("/tmp/tiktok_cookies.json") as f:
    raw = json.load(f)

# Extract sessionid and tt-target-idc
needed = []
for c in raw:
    if c.get("name") == "sessionid":
        needed.append({
            "domain": ".tiktok.com",
            "httpOnly": True,
            "name": "sessionid",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
            "value": c["value"],
            "expirationDate": c.get("expirationDate", 9999999999),
        })
    elif c.get("name") == "tt-target-idc":
        needed.append(c)

# If tt-target-idc not found, add default
if not any(c["name"] == "tt-target-idc" for c in needed):
    needed.append({
        "domain": ".tiktok.com",
        "httpOnly": False,
        "name": "tt-target-idc",
        "path": "/",
        "value": "useast2a",
        "sameSite": "Lax",
        "secure": False,
    })

# Fix sameSite (pickle format doesn't accept "None")
for c in needed:
    if c.get("sameSite") == "None":
        c["sameSite"] = "Strict"

# Save
out_path = os.path.join(cookies_dir, f"tiktok_session-{username}.cookie")
with open(out_path, "wb") as f:
    pickle.dump(needed, f)

print(f"✅ Cookies saved for '{username}'")
print(f"   Path: {out_path}")
print(f"   sessionid: {needed[0]['value'][:10]}...")
EOF
```

### Step 6: Verify

```bash
ls -la /home/archery/tiktokflow/TiktokAutoUploader/CookiesDir/
# Should show: tiktok_session-myshop.cookie
```

### Done!

Your cookies are now on the VPS. The upload system will use them automatically.

**Next steps:**
- Monitor cookie age via the **web dashboard** → Tools tab → Cookie Status
- Get Telegram alerts when cookies are >7 days old
- Re-login using the same method when needed

---

## Method 5: QR Code Headless Login

**Run on VPS. No GUI needed. Scan QR from your phone.**

### Prerequisites

Install Playwright on the VPS:

```bash
pip3 install playwright
playwright install chromium
```

### Step 1: Run the QR Login Script

```bash
python3 /home/archery/tiktokflow/tiktok-machine/scripts/qr_login.py myshop
```

You'll see output like:

```
📱 TikTok QR Login
==================
QR code saved to: /tmp/tiktok_qr_20240115_143022.png
Base64 (first 80 chars): iVBORw0KGgoAAAANSUhEUgAA...

Open the PNG file or decode the base64 to see the QR code.
Scan it with your TikTok app within 60 seconds.

Waiting for login... (press Ctrl+C to cancel)
```

### Step 2: Get the QR Code Image

**Option A: Download the PNG file**

```bash
# From your local machine:
scp archery@your-vps:/tmp/tiktok_qr_*.png ~/Downloads/
# Open it on your computer
```

**Option B: View base64 in browser**

Copy the base64 string from the script output, then open in your browser:

```
data:image/png;base64,PASTE_BASE64_HERE
```

**Option C: Send via Telegram** (if you have a bot set up)

```bash
# If you have curl and a Telegram bot token:
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendPhoto" \
  -F "chat_id=<YOUR_CHAT_ID>" \
  -F "photo=@/tmp/tiktok_qr_*.png"
```

### Step 3: Scan the QR Code

1. Open TikTok app on your phone
2. Go to Profile → Menu (☰) → Settings → Scan QR Code
3. Scan the QR code from the image
4. Confirm login on your phone

### Step 4: Wait for Confirmation

The script will detect the login and save cookies:

```
✅ Login successful!
   Cookies saved to: /home/archery/tiktokflow/TiktokAutoUploader/CookiesDir/tiktok_session-myshop.cookie
   sessionid: abc123de...
```

### Done!

---

## Re-Login When Cookies Expire

TikTok sessions typically last **30 days**. Our system monitors cookie age and sends a Telegram warning when they're >7 days old.

### To Re-Login

**Method 1 (Browser Export):**
1. Log in to TikTok on your home computer
2. Export cookies again
3. Upload and convert on VPS (overwrite old file)

**Method 5 (QR Code):**
1. Run the QR login script again
2. Scan new QR code
3. Cookies auto-overwrite

---

## Troubleshooting

### "User not found on system"

This is normal for first login. The script creates the cookie file.

### "No sessionid found in cookies"

Your browser export didn't include the session cookie. Make sure you're logged in to TikTok when exporting.

### "QR code expired"

QR codes expire in ~60 seconds. Run the script again and scan quickly.

### "Cookies saved but uploads fail"

The session may have expired or been invalidated. Re-login using either method.

### Cookie file location

```
/home/archery/tiktokflow/TiktokAutoUploader/CookiesDir/tiktok_session-<username>.cookie
```

Replace `<username>` with whatever name you use (e.g., `myshop`).

---

## Automation: Scheduled Re-Login

For Method 5, you can set up a cron job to remind you to re-login:

```bash
# Add to crontab (runs every 25 days):
crontab -e

# Add this line:
0 9 */25 * * echo "⚠️ TikTok cookies may expire soon. Run: python3 /home/archery/tiktokflow/tiktok-machine/scripts/qr_login.py myshop" | mail -s "TikTok Re-Login Reminder" your@email.com
```

Or rely on the Telegram warning from the orchestrator (sends alert when cookies are >7 days old).
