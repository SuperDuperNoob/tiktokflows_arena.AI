#!/usr/bin/env python3
"""
qr_login.py — Headless TikTok login via QR code (no VPS GUI required)

Usage:
    python3 qr_login.py <username> [--uploader-dir /path/to/TiktokAutoUploader]

Example:
    python3 qr_login.py myshop

This script:
1. Launches headless Chromium on the VPS
2. Navigates to TikTok login page
3. Takes a screenshot of the QR code
4. Waits for you to scan it with your TikTok app
5. Captures the resulting session cookies
6. Saves them in TiktokAutoUploader's pickle format

Requirements:
    pip install playwright
    playwright install chromium
"""
import asyncio
import base64
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("❌ Playwright not installed")
    print("   Install with: pip3 install playwright && playwright install chromium")
    sys.exit(1)


def find_uploader_dir() -> str:
    """Find TiktokAutoUploader installation directory."""
    candidates = [
        "/opt/TiktokAutoUploader",
        os.path.expanduser("~/tiktokflow/TiktokAutoUploader"),
        os.path.expanduser("~/TiktokAutoUploader"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c

    print("❌ Cannot find TiktokAutoUploader directory")
    print("   Specify with --uploader-dir or set TIKTOK_UPLOADER_DIR env var")
    sys.exit(1)


async def qr_login(username: str, uploader_dir: str, timeout_seconds: int = 120,
                    proxy_url: str = None):
    """
    Perform QR code login and save cookies.

    CRITICAL: If proxy_url is provided, the login browser routes through it.
    This ensures TikTok sees the SAME IP for login and uploads — essential
    for account safety. Without proxy, login uses VPS direct IP which may
    be a different country/network type than your upload proxy.

    Args:
        username: TikTok account label
        uploader_dir: Path to TiktokAutoUploader
        timeout_seconds: How long to wait for QR scan
        proxy_url: HTTP proxy URL (e.g. http://user:pass@host:port)
                   If None, uses VPS direct IP (NOT recommended)
    """
    print("📱 TikTok QR Login")
    print("=" * 40)

    if proxy_url:
        print(f" Using proxy: {proxy_url[:40]}...")
        print(f"   Login IP will match upload IP ✅")
    else:
        print(f"⚠️  NO PROXY — login will use VPS direct IP")
        print(f"   This may cause IP mismatch with uploads ️")

    async with async_playwright() as p:
        # Launch headless browser
        print("🌐 Launching Chromium (headless)...")

        launch_kwargs = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        }

        # Route browser through proxy if provided
        if proxy_url:
            launch_kwargs["proxy"] = {"server": proxy_url}

        browser = await p.chromium.launch(**launch_kwargs)

        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()

        # Navigate to TikTok login
        print("🔗 Navigating to TikTok login...")
        await page.goto("https://www.tiktok.com/login", wait_until="networkidle", timeout=30000)

        # Wait for QR code to appear
        print("📷 Waiting for QR code...")
        try:
            await page.wait_for_selector('canvas, img[src*="qr"], [class*="qr"]', timeout=15000)
        except Exception:
            print("⚠️  QR code selector not found — taking screenshot anyway")

        # Small delay to ensure QR is fully rendered
        await page.wait_for_timeout(2000)

        # Take screenshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        qr_path = f"/tmp/tiktok_qr_{username}_{timestamp}.png"
        await page.screenshot(path=qr_path)

        print(f"\n✅ QR code saved to: {qr_path}")
        print(f"\n📱 How to view the QR code:")
        print(f"   Option 1: Download the file:")
        print(f"             scp {username}@your-vps:{qr_path} ~/Downloads/")
        print(f"   Option 2: Open base64 in browser:")
        print(f"             (see below)")
        print(f"   Option 3: Send via Telegram (if bot configured)")

        # Generate base64 for easy viewing
        with open(qr_path, "rb") as f:
            qr_b64 = base64.b64encode(f.read()).decode()

        print(f"\n📋 Base64 (paste into browser address bar):")
        print(f"   data:image/png;base64,{qr_b64[:100]}...")
        print(f"   (full base64 is {len(qr_b64)} characters)")

        # Save base64 to file for easy copying
        b64_path = f"/tmp/tiktok_qr_{username}_{timestamp}.b64"
        with open(b64_path, "w") as f:
            f.write(qr_b64)
        print(f"\n💾 Full base64 saved to: {b64_path}")

        print(f"\n Waiting for you to scan the QR code...")
        print(f"   (timeout: {timeout_seconds} seconds)")
        print(f"   Open TikTok app → Profile → Menu → Scan QR Code")

        # Wait for login (sessionid cookie to appear)
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < timeout_seconds:
            try:
                # Check if sessionid cookie exists
                has_session = await page.evaluate("() => document.cookie.includes('sessionid')")
                if has_session:
                    logged_in = True
                    print(f"\n✅ Login detected!")
                    break
            except Exception:
                pass

            await page.wait_for_timeout(2000)
            elapsed = int(time.time() - start_time)
            remaining = timeout_seconds - elapsed
            if elapsed % 10 == 0:
                print(f"    Still waiting... ({remaining}s remaining)")

        if not logged_in:
            print(f"\n❌ Login timed out after {timeout_seconds} seconds")
            print("   The QR code may have expired. Run the script again.")
            await browser.close()
            sys.exit(1)

        # Wait a bit for all cookies to settle
        await page.wait_for_timeout(3000)

        # Extract cookies
        cookies = await context.cookies()

        # Filter to needed cookies
        needed_names = {"sessionid", "tt-target-idc"}
        needed = [c for c in cookies if c["name"] in needed_names]

        # Add default tt-target-idc if missing
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

        # Fix sameSite
        for c in needed:
            if c.get("sameSite") == "None":
                c["sameSite"] = "Strict"

        # Save cookies
        cookies_dir = os.path.join(uploader_dir, "CookiesDir")
        os.makedirs(cookies_dir, exist_ok=True)
        # Ensure directory permissions are 700 (owner only)
        os.chmod(cookies_dir, 0o700)
        out_path = os.path.join(cookies_dir, f"tiktok_session-{username}.cookie")

        with open(out_path, "wb") as f:
            pickle.dump(needed, f)
        # Ensure cookie file permissions are 600 (owner read/write only)
        os.chmod(out_path, 0o600)

        # Print summary
        session_value = next((c["value"] for c in needed if c["name"] == "sessionid"), "")
        target_idc = next((c["value"] for c in needed if c["name"] == "tt-target-idc"), "N/A")

        print(f"\n✅ Cookies saved!")
        print(f"   Path: {out_path}")
        print(f"   sessionid: {session_value[:10]}...{session_value[-4:]}")
        print(f"   tt-target-idc: {target_idc}")
        print(f"   Total cookies: {len(needed)}")

        # Cleanup browser
        await browser.close()

        # Cleanup temp files
        if os.path.exists(qr_path):
            os.remove(qr_path)
        if os.path.exists(b64_path):
            os.remove(b64_path)

        print(f"\n🎉 Done! You can now use TikTok uploads with username '{username}'")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Usage: python3 qr_login.py <username> [--uploader-dir /path] [--timeout 120] [--proxy http://user:pass@host:port]")
        sys.exit(1)

    username = sys.argv[1]

    # Parse optional arguments
    uploader_dir = None
    timeout = 120
    proxy_url = None

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--uploader-dir" and i + 1 < len(sys.argv):
            uploader_dir = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--timeout" and i + 1 < len(sys.argv):
            timeout = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--proxy" and i + 1 < len(sys.argv):
            proxy_url = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    # Check env var for proxy
    if not proxy_url:
        proxy_url = os.environ.get("TIKTOK_LOGIN_PROXY")

    # Auto-detect if still not set
    if not uploader_dir:
        uploader_dir = os.environ.get("TIKTOK_UPLOADER_DIR")
    if not uploader_dir:
        uploader_dir = find_uploader_dir()

    # Try to auto-detect proxy from config.yaml
    if not proxy_url:
        config_paths = [
            os.path.join(uploader_dir, "..", "config", "config.yaml"),
            os.path.expanduser("~/tiktokflow/tiktok-machine/config/config.yaml"),
            "/opt/tiktok-machine/config/config.yaml",
        ]
        for cp in config_paths:
            if os.path.exists(cp):
                try:
                    import yaml
                    with open(cp) as f:
                        cfg = yaml.safe_load(f)
                    proxy_url = cfg.get("proxy", {}).get("endpoint", "")
                    if proxy_url and proxy_url not in ("http://USER:PASS@HOST:PORT", ""):
                        print(f" Auto-detected proxy from config.yaml ✅")
                        break
                    else:
                        proxy_url = None
                except Exception:
                    pass

    print(f"🔧 Configuration:")
    print(f"   Username: {username}")
    print(f"   Uploader dir: {uploader_dir}")
    print(f"   Timeout: {timeout}s")
    print(f"   Proxy: {proxy_url or 'NONE (VPS direct IP)'}")
    print()

    asyncio.run(qr_login(username, uploader_dir, timeout, proxy_url))


if __name__ == "__main__":
    main()
