#!/usr/bin/env python3
"""
import_cookies.py — Convert browser-exported TikTok cookies to TiktokAutoUploader format

Usage:
    python3 import_cookies.py <username> <cookies_json_path>

Example:
    python3 import_cookies.py myshop /tmp/tiktok_cookies.json

This script accepts cookies exported from browser extensions like:
- EditThisCookie (Chrome)
- Cookie-Editor (Firefox)
- Get cookies.txt LOCALLY

And converts them to the pickle format that TiktokAutoUploader expects.
"""
import json
import pickle
import os
import sys
from pathlib import Path


def parse_netscape_format(text: str) -> list:
    """Parse Netscape cookie.txt format."""
    cookies = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies.append({
                "domain": parts[0],
                "httpOnly": parts[1].lower() == "true",
                "path": parts[2],
                "secure": parts[3].lower() == "true",
                "expirationDate": int(parts[4]) if parts[4].isdigit() else 9999999999,
                "name": parts[5],
                "value": parts[6],
            })
    return cookies


def import_cookies(username: str, input_path: str, uploader_dir: str = None):
    """
    Import cookies from a JSON or Netscape format file.

    Args:
        username: TikTok account label (used in cookie filename)
        input_path: Path to exported cookies file
        uploader_dir: TiktokAutoUploader installation path (auto-detected if None)
    """
    # Auto-detect uploader directory
    if not uploader_dir:
        # Try common locations
        candidates = [
            "/opt/TiktokAutoUploader",
            os.path.expanduser("~/tiktokflow/TiktokAutoUploader"),
            os.path.expanduser("~/TiktokAutoUploader"),
        ]
        for c in candidates:
            if os.path.isdir(c):
                uploader_dir = c
                break

    if not uploader_dir:
        print("❌ Cannot find TiktokAutoUploader directory.")
        print("   Specify it with --uploader-dir or set TIKTOK_UPLOADER_DIR env var.")
        sys.exit(1)

    # Load input file
    with open(input_path, "r") as f:
        raw = f.read()

    # Try JSON first
    try:
        raw_json = json.loads(raw)
        if isinstance(raw_json, list):
            cookies = raw_json
        else:
            # Single cookie object
            cookies = [raw_json]
    except json.JSONDecodeError:
        # Try Netscape format
        cookies = parse_netscape_format(raw)

    if not cookies:
        print("❌ No cookies found in input file")
        sys.exit(1)

    # Extract only the cookies TiktokAutoUploader needs
    needed_names = {"sessionid", "tt-target-idc"}
    needed = [c for c in cookies if c.get("name") in needed_names]

    # Validate
    if not any(c.get("name") == "sessionid" for c in needed):
        print("❌ No 'sessionid' cookie found in input")
        print("   Make sure you exported cookies while logged in to TikTok")
        sys.exit(1)

    # Add default tt-target-idc if missing
    if not any(c.get("name") == "tt-target-idc" for c in needed):
        print("⚠️  No 'tt-target-idc' found — using default 'useast2a'")
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

    # Ensure cookies directory exists
    cookies_dir = os.path.join(uploader_dir, "CookiesDir")
    os.makedirs(cookies_dir, exist_ok=True)
    # Ensure directory permissions are 700 (owner only)
    os.chmod(cookies_dir, 0o700)

    # Save pickle file
    out_path = os.path.join(cookies_dir, f"tiktok_session-{username}.cookie")
    with open(out_path, "wb") as f:
        pickle.dump(needed, f)
    # Ensure cookie file permissions are 600 (owner read/write only)
    os.chmod(out_path, 0o600)

    # Print summary
    session_value = next(c["value"] for c in needed if c["name"] == "sessionid")
    target_idc = next((c["value"] for c in needed if c["name"] == "tt-target-idc"), "N/A")

    print(f"✅ Cookies imported for '{username}'")
    print(f"   Saved to: {out_path}")
    print(f"   sessionid: {session_value[:10]}...{session_value[-4:]}")
    print(f"   tt-target-idc: {target_idc}")
    print(f"   Total cookies: {len(needed)}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("Usage: python3 import_cookies.py <username> <cookies_file> [--uploader-dir /path/to/TiktokAutoUploader]")
        sys.exit(1)

    username = sys.argv[1]
    input_path = sys.argv[2]

    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        sys.exit(1)

    # Check for optional --uploader-dir flag
    uploader_dir = None
    if "--uploader-dir" in sys.argv:
        idx = sys.argv.index("--uploader-dir")
        if idx + 1 < len(sys.argv):
            uploader_dir = sys.argv[idx + 1]

    # Also check env var
    if not uploader_dir:
        uploader_dir = os.environ.get("TIKTOK_UPLOADER_DIR")

    import_cookies(username, input_path, uploader_dir)


if __name__ == "__main__":
    main()
