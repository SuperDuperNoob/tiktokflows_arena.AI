# System Lifecycle: How It Really Works

This document provides a step-by-step breakdown of how the repository functions from start to finish, based strictly on the code logic across the python files.

There are **three main interconnected pillars** working simultaneously: 
1. The **Background Orchestrator** (the engine)
2. The **Web Dashboard** (the control room)
3. The **Telegram Bot** (the remote)

Here is the exact lifecycle of how a video goes from being added to the system, all the way to a published TikTok post.

---

### Stage 1: System Setup & Data Entry (The Web Dashboard)
*(Handled by `webapp/server.py` and `webapp/static/app.js`)*

1. **Adding the Product:** You open the web dashboard and add a new product (e.g., "Biocho" and ID "12345"). The FastAPI backend modifies the `content/products.json` file to store the product ID and creates an empty folder at `content/raw/Biocho/` (adding a hidden `.keep` file so Google Drive syncs it).
2. **Adding the Product Tags:** Inside the products tab, you type in 2-5 "Yellow Bag Tags". The server stores this list inside `products.json` under that specific product.
3. **Adding the Captions:** You go to the Captions tab, select the product, and type your base "Video Overlay Text" and your "Post Description". The server inserts this as a new row into the SQLite database (`db.py` -> `caption_pool` table).
4. **Dropping the Raw Video:** You drop your raw MP4 files into your Google Drive folder, which is linked to the local `content/raw/` directory.

---

### Stage 2: The Orchestrator Boot & Scheduling
*(Handled by `scripts/upload_orchestrator.py`)*

5. **The Infinite Loop:** You start the python script. The orchestrator boots up, spins up the Telegram bot in the background, and immediately triggers `_do_sync()` which forces the `sync_drive.py` module to download your new MP4 videos from Drive into the local `content/raw/Biocho/` folder.
6. **The Waiting Game:** The system enters an infinite `while self._running:` loop. It calculates when the next post should happen by looking at the daily limit and adding a randomized "human jitter" delay. Once the timer hits zero, it triggers a `_run_cycle()`.

---

### Stage 3: Data Selection & Content Splicing
*(Handled by `scripts/upload_orchestrator.py`)*

7. **Selecting the Video:** The code queries the SQLite database to figure out which product hasn't been posted recently and has raw videos available. It grabs the top 5 *least used* raw MP4 files for that product and randomly picks one.
8. **Fetching the Text:** 
   * It calls `_get_product_info()` to read `products.json`, grabbing your TikTok Product ID and randomly picking one of your Yellow Bag Tags. 
   * It calls `_get_caption()` to hit the SQLite database and retrieve the least-used caption dictionary for that product (grabbing your Overlay Text and Description Text).

---

### Stage 4: Network Verification & Video Transformation
*(Handled by `scripts/upload_orchestrator.py` and `scripts/transform_video.py`)*

9. **Proxy Check:** Before burning CPU power, it securely checks your proxy connection. It sends a request to `ipinfo.io` and parses the ASN network data. If it detects a datacenter name (like "Hetzner" or "DigitalOcean") instead of a residential ISP, it aborts the entire upload to protect your account.
10. **Text Rendering:** The `transform()` function is called. It takes your Video Overlay Text, mixes it with a random hook (e.g., *"korang tau tak?"*), adds random emojis, and appends a Call-to-Action. It feeds this text to the `TextRenderer` class, which uses `skia-python` to draw the text + emojis into a transparent, high-definition PNG file.
11. **FFmpeg Obfuscation:** The code builds a giant FFmpeg command. It speeds up the raw video slightly (0.97-1.06x), alters the brightness, occasionally trims the first fraction of a second, strips the original audio, drops in a random MP3 from the `sounds/` folder, and lays the PNG text file vertically down the center. 
12. **Quality Guards:** After rendering, the script uses `ffprobe` to scan the new output MP4 file to ensure it isn't an unplayable static frame, and verifies the file size isn't suspiciously small.

---

### Stage 5: Uploading to TikTok Shop
*(Handled by `TiktokAutoUploader/tiktok_uploader/tiktok_v2.py`)*

13. **Database Pre-Log:** The orchestrator writes a `TRANSFORMING` entry into the SQLite `posts` table.
14. **Injecting the Data:** It calls the `upload_video()` function, passing in your Post Description as the `title`, and injecting your Product ID and Yellow Bag Tag into the `products` list parameter.
15. **Signature Bypass:** The uploader script reads your local `tiktok_session` cookies. It modifies the underlying JSON payload to include the product tag (`add_from: 2`, `type: 33`). It then launches a local headless javascript engine to execute `browser.js`, which generates a verified `X-Bogus` signature tricking TikTok into thinking a real Chrome browser constructed the payload.
16. **Execution:** The payload and video are HTTP POSTed to the TikTok web servers via the verified residential proxy.

---

### Stage 6: Cleanup & Telegram Notification
*(Handled by `scripts/upload_orchestrator.py` and `scripts/telegram_bot.py`)*

17. **File Management:** If TikTok accepts the post, the orchestrator moves the burned MP4 video out of the `content/processed/` folder and archives it into `content/posted/`. 
18. **Ledger Updates:** The script updates the SQLite `posts` table to `POSTED`, increments the "used" count for the raw video file, and updates the "used" count on the caption text so it goes to the bottom of the pile.
19. **Ping the User:** It fires a message to your Telegram bot via the `python-telegram-bot` library: *"✅ Upload Success! Biocho [3/7 posts today]..."*
20. **Reset:** The orchestrator goes back to sleep, calculating the random jitter for the next cycle.

---

### (Optional) Stage 7: The AI Growth Trigger
*(Handled by `scripts/telegram_bot.py` and `scripts/ai_engine.py`)*

At any point, you can pick up your phone and type `/growth` in Telegram. The bot wakes up `ai_engine.py`, looks at the products in your SQLite database, and calls the OpenAI API to generate 10 brand new Video Overlays and Descriptions. It scrubs them through `scripts/compliance.py` to ensure no illegal medical claims exist, and silently injects them into the `caption_pool` table so the Orchestrator can use them in the next loop.