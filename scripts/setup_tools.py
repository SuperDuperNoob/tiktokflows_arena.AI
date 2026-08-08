"""
Setup Utility Script

Run this to perform initial setup tasks:
- Initialize the database
- Add seed captions to the pool
- Verify configuration
- Test proxy connection
"""
import os
import sys
import json
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)


def verify_config():
    """Verify all configuration is valid."""
    config_path = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    if not os.path.exists(config_path):
        print("❌ config.yaml not found")
        return None

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    checks = []

    # Check Telegram
    tg = config.get("telegram", {})
    if tg.get("bot_token") and tg["bot_token"] != "YOUR_BOT_TOKEN_HERE":
        checks.append(("✅", "Telegram bot token configured"))
    else:
        checks.append(("❌", "Telegram bot token NOT configured"))

    if tg.get("allowed_user_id") and tg["allowed_user_id"] != 123456789:
        checks.append(("✅", f"Telegram user ID set: {tg['allowed_user_id']}"))
    else:
        checks.append(("❌", "Telegram user ID not changed from default"))

    # Check Proxy
    proxy = config.get("proxy", {})
    if proxy.get("endpoint") and proxy["endpoint"] != "http://USER:PASS@HOST:PORT":
        checks.append(("✅", "Proxy endpoint configured"))
    else:
        checks.append(("❌", "Proxy endpoint NOT configured"))

    # Check AI
    ai = config.get("ai", {})
    if ai.get("api_key") and ai["api_key"] != "your-api-key-here":
        checks.append(("✅", "AI API key configured"))
    else:
        checks.append(("⚠️", "AI API key not configured (optional — /growth won't work)"))

    # Check Apify
    apify = config.get("apify", {})
    if apify.get("api_token") and apify["api_token"] != "your-apify-token-here":
        checks.append(("✅", "Apify token configured"))
    else:
        checks.append(("⚠️", "Apify token not configured (optional — competitor scraping won't work)"))

    # Check products
    products = config.get("products", {})
    if len(products) > 0:
        checks.append(("✅", f"Products configured: {', '.join(products.keys())}"))
    else:
        checks.append(("❌", "No products configured"))

    # Check sounds
    sounds_dir = os.path.join(PROJECT_ROOT, "sounds")
    if os.path.isdir(sounds_dir):
        sound_files = [f for f in os.listdir(sounds_dir) if f.endswith((".mp3", ".wav", ".ogg"))]
        if len(sound_files) >= 10:
            checks.append(("✅", f"Sounds directory: {len(sound_files)} audio files"))
        elif len(sound_files) > 0:
            checks.append(("⚠️", f"Sounds directory: only {len(sound_files)} files (recommend 20+)"))
        else:
            checks.append(("⚠️", "Sounds directory is empty — add royalty-free audio files"))
    else:
        checks.append(("❌", "Sounds directory missing"))

    # Check rclone
    import subprocess
    try:
        result = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True, timeout=10)
        remotes = result.stdout.strip().split("\n")
        gd_remote = config.get("google_drive", {}).get("rclone_remote", "gdrive")
        if f"{gd_remote}:" in remotes:
            checks.append(("✅", f"rclone remote '{gd_remote}' configured"))
        else:
            checks.append(("❌", f"rclone remote '{gd_remote}' NOT found. Run: rclone config"))
    except FileNotFoundError:
        checks.append(("❌", "rclone not installed. Run: apt install rclone"))
    except Exception as e:
        checks.append(("⚠️", f"rclone check failed: {e}"))

    # Check TiktokAutoUploader
    uploader_dir = config.get("tiktok", {}).get("uploader_dir", "/opt/TiktokAutoUploader")
    if os.path.isdir(uploader_dir):
        checks.append(("✅", f"TiktokAutoUploader found at {uploader_dir}"))
        session_user = config.get("tiktok", {}).get("session_username", "myshop")
        cookie_path = os.path.join(uploader_dir, "CookiesDir", f"tiktok_session-{session_user}.cookie")
        if os.path.exists(cookie_path):
            checks.append(("✅", f"TikTok session cookies found for '{session_user}'"))
        else:
            checks.append(("❌", f"No session cookies for '{session_user}'. Run login first."))
    else:
        checks.append(("❌", f"TiktokAutoUploader not found at {uploader_dir}"))

    print("\n📋 Configuration Verification")
    print("=" * 50)
    for status, msg in checks:
        print(f"  {status} {msg}")
    print("")

    return config


def test_proxy(config):
    """Test the proxy connection and verify exit IP."""
    import httpx

    proxy_url = config.get("proxy", {}).get("endpoint", "")
    if not proxy_url or proxy_url == "http://USER:PASS@HOST:PORT":
        print("❌ Proxy not configured — skipping test")
        return

    from lib import mask_proxy
    print(f"\n🌐 Testing proxy: {mask_proxy(proxy_url)}")

    try:
        proxies = {"http://": proxy_url, "https://": proxy_url}
        resp = httpx.get("https://ipinfo.io/json", proxies=proxies, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        print(f"  IP: {data.get('ip')}")
        print(f"  City: {data.get('city')}")
        print(f"  Region: {data.get('region')}")
        print(f"  Country: {data.get('country')}")
        print(f"  Org: {data.get('org')}")

        expected = config.get("proxy", {}).get("expected_country", "MY")
        if data.get("country") == expected:
            print(f"  ✅ Country matches expected: {expected}")
        else:
            print(f"  ❌ Country mismatch! Expected {expected}, got {data.get('country')}")

    except Exception as e:
        print(f"  ❌ Proxy test failed: {e}")


def init_db():
    """Initialize the database."""
    config_path = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    db_path = config.get("logging", {}).get("db_path", "logs/tiktok.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(PROJECT_ROOT, db_path)

    from db import Database
    db = Database(db_path)
    print(f"✅ Database initialized at {db_path}")
    return db


def add_seed_captions(db, config):
    """Add some seed captions to get started."""
    compliance_config = config.get("compliance", {})
    ai_config = config.get("ai", {})
    from compliance_engine import ComplianceEngine
    engine = ComplianceEngine(compliance_config, ai_config=ai_config)

    products = config.get("products", {})

    # Seed captions per product (these are examples — replace with your own)
    seed_captions = {
        "Biocho": [
            "Rasa sedap badan bertenaga setiap hari 🍫 #biocho #tenaga #kesihatan",
            "Amalan harian untuk gaya hidup lebih sihat ✨ #wellness #sihat #biocho",
            "Ramai dah cuba dan suka! Korang bila lagi? 😍 #fyp #tiktokshop #biocho",
            "Rahsia hari-hari aku ceria ☀️ #lifestyle #healthylife #biocho",
            "Satu-satunya yang aku ambil setiap pagi 🌅 #morningroutine #biocho",
        ],
        "Serum": [
            "Kulit rasa fresh lepas pakai 🧴 #skincare #glowing #serum",
            "Finally jumpa serum yang sesuai dengan kulit aku! 💧 #skincareroutine #fyp",
            "Glow up journey starts here ✨ #glowup #kulit #skincare",
            "Wajib try untuk kulit yang lebih berseri 🌟 #beauty #tiktokshop #serum",
            "Tips kulit sihat: konsisten pakai serum setiap malam 🌙 #skincaretips #fyp",
        ],
    }

    added = 0
    for product_name, captions in seed_captions.items():
        if product_name not in products:
            continue

        for caption in captions:
            is_ok, final_text, issues = engine.process_caption(caption)
            if is_ok:
                db.add_caption(
                    product_name=product_name,
                    caption_text=final_text,
                    source="manual",
                    compliance_checked=True,
                    original_text=caption if final_text != caption else None,
                )
                added += 1
                print(f"  ✅ [{product_name}] {final_text[:60]}...")
            else:
                print(f"  ❌ [{product_name}] REJECTED: {caption[:60]}... — {issues}")

    print(f"\n✅ Added {added} seed captions to the pool")


def main():
    print("\n🔧 TikTok Auto-Posting Machine — Setup Utility")
    print("=" * 50)

    action = "all"
    if len(sys.argv) > 1:
        action = sys.argv[1]

    if action in ("all", "verify"):
        config = verify_config()

    if action in ("all", "proxy"):
        if config:
            test_proxy(config)

    if action in ("all", "init"):
        db = init_db()
        if config:
            add_seed_captions(db, config)

    print("\n✅ Setup complete!")
    print("   Start the service: systemctl start tiktok-machine")
    print("   View logs: journalctl -u tiktok-machine -f")


if __name__ == "__main__":
    main()
