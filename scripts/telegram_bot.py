"""
Telegram Bot Interface

Primary interface for controlling the TikTok Auto-Posting Machine.
Only responds to the configured Telegram user ID.

Commands:
  /status  — Current queue, stock levels, today's post count
  /growth  — Triggers AI strategy + competitor analysis + 10 new captions
  /stock   — Detailed stock breakdown per product
  /captions [product] — Show caption pool for a product
  /pause   — Pause the posting loop
  /resume  — Resume the posting loop
  /force [product] — Force next upload to be from specified product
  /logs    — Last 20 system events
"""
import asyncio
import logging
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from telegram import Update, Bot
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters
)

from db import Database
from ai_growth import AIGrowthEngine
from compliance import ComplianceEngine

logger = logging.getLogger(__name__)


# MYT timezone offset (UTC+8)
MYT_OFFSET = timedelta(hours=8)
MYT = timezone(MYT_OFFSET)


class TelegramBotInterface:
    """Telegram bot for controlling the TikTok posting machine."""

    def __init__(self, config: dict, db: Database, orchestrator=None):
        self.bot_token = config.get("bot_token", "")
        self.allowed_user_id = config.get("allowed_user_id")
        self.db = db
        self.orchestrator = orchestrator

        # Sub-configs
        self.ai_config = config.get("ai", {})
        self.compliance_config = config.get("compliance", {})
        self.products_config = config.get("products", {})
        self.content_config = config.get("content", {})
        self.posting_config = config.get("posting", {})

        self.app: Optional[Application] = None

    def start(self):
        """Start the bot in a background thread."""
        if not self.bot_token or self.bot_token == "YOUR_BOT_TOKEN_HERE":
            logger.error("Telegram bot token not configured — bot disabled")
            return

        self.app = Application.builder().token(self.bot_token).build()

        # Register command handlers
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("growth", self._cmd_growth))
        self.app.add_handler(CommandHandler("stock", self._cmd_stock))
        self.app.add_handler(CommandHandler("captions", self._cmd_captions))
        self.app.add_handler(CommandHandler("pause", self._cmd_pause))
        self.app.add_handler(CommandHandler("resume", self._cmd_resume))
        self.app.add_handler(CommandHandler("force", self._cmd_force))
        self.app.add_handler(CommandHandler("logs", self._cmd_logs))
        self.app.add_handler(CommandHandler("relogin", self._cmd_relogin))

        # Catch-all for unknown messages
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self._handle_unknown
        ))

        # Run in background thread
        thread = threading.Thread(target=self._run_bot, daemon=True)
        thread.start()
        logger.info("Telegram bot started in background thread")

    def _run_bot(self):
        """Run the bot polling loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.app.run_polling(drop_pending_updates=True)

    def _is_authorized(self, update: Update) -> bool:
        """Check if the user is authorized."""
        user_id = update.effective_user.id
        if user_id != self.allowed_user_id:
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            return False
        return True

    async def _send_message(self, chat_id: int, text: str):
        """Send a message, handling long messages by splitting."""
        if not self.app or not self.app.bot:
            return
        # Telegram limit is 4096 chars
        if len(text) <= 4000:
            await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        else:
            # Split into chunks
            chunks = self._split_message(text, 4000)
            for chunk in chunks:
                await self.app.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")
                await asyncio.sleep(0.5)

    def _split_message(self, text: str, max_len: int) -> list:
        """Split a long message into chunks at line boundaries."""
        lines = text.split("\n")
        chunks = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > max_len:
                if current:
                    chunks.append(current)
                current = line
            else:
                current = current + "\n" + line if current else line
        if current:
            chunks.append(current)
        return chunks

    # =========================================================================
    # COMMAND HANDLERS
    # =========================================================================

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._is_authorized(update):
            return

        now_myt = datetime.now(MYT)
        posted_today = self.db.get_posted_count_today()
        target = self.posting_config.get("daily_post_target", 7)
        last_post = self.db.get_last_post_time()
        stock_counts = self.db.get_raw_stock_counts()

        # Build status message
        lines = [
            f"📊 <b>Status Report</b>",
            f"🕐 Time: {now_myt.strftime('%I:%M %p')} MYT",
            f"",
            f"📈 <b>Today's Posts:</b> {posted_today}/{target}",
        ]

        if last_post:
            last_myt = last_post + MYT_OFFSET
            lines.append(f"⏱️ Last Post: {last_myt.strftime('%I:%M %p')} MYT")
        else:
            lines.append("⏱️ Last Post: Never")

        lines.append("")
        lines.append("📦 <b>Stock Levels:</b>")
        for product, count in stock_counts.items():
            warn = " ⚠️" if count < 5 else ""
            lines.append(f"  • {product}: {count} raw videos{warn}")

        if not stock_counts:
            lines.append("  (no products synced yet)")

        # Pause state
        if self.orchestrator and hasattr(self.orchestrator, 'paused') and self.orchestrator.paused:
            lines.append("")
            lines.append("⏸️ <b>Posting is PAUSED</b>")

        await self._send_message(update.effective_chat.id, "\n".join(lines))

    async def _cmd_growth(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /growth command — triggers AI strategy + captions."""
        if not self._is_authorized(update):
            return

        await self._send_message(
            update.effective_chat.id,
            "⏳ Generating growth strategy and captions...\n(this takes ~30 seconds)"
        )

        ai = AIGrowthEngine(self.ai_config, self.db)
        compliance = ComplianceEngine(self.compliance_config, ai_config=self.ai_config)

        # Generate strategy
        strategy = ai.generate_strategy(self.products_config)

        # Generate captions for each product
        all_new_captions = {}
        for product_name, product_conf in self.products_config.items():
            captions = ai.generate_captions(product_name, product_conf)
            if captions:
                approved = []
                for cap in captions:
                    is_ok, final_text, issues = compliance.process_caption(cap)
                    if is_ok:
                        self.db.add_caption(
                            product_name=product_name,
                            caption_text=final_text,
                            source="ai_generated",
                            compliance_checked=True,
                            original_text=cap if final_text != cap else None,
                        )
                        approved.append(final_text)
                all_new_captions[product_name] = approved

        # Build response
        lines = ["🚀 <b>Growth Strategy Report</b>", ""]

        if strategy:
            # Convert basic markdown to HTML for Telegram
            strategy_html = strategy.replace("**", "<b>").replace("**", "</b>")
            # Simple approach: just include as-is with monospace for code
            lines.append(strategy[:3000])
        else:
            lines.append("⚠️ Strategy generation failed (check AI config)")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("✨ <b>New Captions Added:</b>")

        for product, captions in all_new_captions.items():
            lines.append(f"\n📦 <b>{product}</b> ({len(captions)} new):")
            for cap in captions[:5]:
                lines.append(f"  • {cap}")

        if not all_new_captions:
            lines.append("  (no new captions generated)")

        await self._send_message(update.effective_chat.id, "\n".join(lines))

    async def _cmd_stock(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stock command — detailed stock breakdown."""
        if not self._is_authorized(update):
            return

        stock_counts = self.db.get_raw_stock_counts()
        products_due = self.db.get_products_due_next()

        lines = ["📦 <b>Detailed Stock Report</b>", ""]

        # Stock per product
        lines.append("<b>Raw Video Counts:</b>")
        for product, count in sorted(stock_counts.items()):
            warn = " ⚠️ LOW" if count < 5 else ""
            lines.append(f"  • {product}: {count} videos{warn}")

        if not stock_counts:
            lines.append("  (no products synced yet)")

        # Posting priority
        lines.append("")
        lines.append("<b>Posting Priority (next up):</b>")
        for p in products_due[:5]:
            last = p.get("last_posted")
            if last and last != "1970-01-01":
                last_str = last[:10]
            else:
                last_str = "never"
            lines.append(f"  • {p['product_name']}: {p['stock_count']} stock, last posted {last_str}")

        # Recent posts
        lines.append("")
        lines.append("<b>Recent Posts (last 5):</b>")
        with self.db._connect() as conn:
            recent = conn.execute(
                "SELECT * FROM posts ORDER BY posted_at DESC LIMIT 5"
            ).fetchall()
            for r in recent:
                r = dict(r)
                status_emoji = {"POSTED": "✅", "FAILED": "❌", "PENDING": "⏳"}.get(r["status"], "❓")
                posted = r.get("posted_at", "?")
                if posted and posted != "?":
                    posted = posted[:16]
                lines.append(f"  {status_emoji} {r['product_name']} — {posted} [{r['status']}]")

        await self._send_message(update.effective_chat.id, "\n".join(lines))

    async def _cmd_captions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /captions [product] command."""
        if not self._is_authorized(update):
            return

        # Get product name from args
        args = context.args
        if not args:
            # Show all products with caption counts
            lines = ["📋 <b>Caption Pools</b>", ""]
            for product in self.products_config.keys():
                captions = self.db.get_caption_pool_for_product(product)
                compliant = sum(1 for c in captions if c.get("compliance_checked"))
                lines.append(f"  • {product}: {len(captions)} total, {compliant} compliant")
            lines.append("")
            lines.append("Use /captions [product] to see details")
            await self._send_message(update.effective_chat.id, "\n".join(lines))
            return

        product_name = args[0]
        captions = self.db.get_caption_pool_for_product(product_name)

        lines = [f"📋 <b>Captions for {product_name}</b> ({len(captions)} total)", ""]

        for i, c in enumerate(captions[:20], 1):
            checked = "✅" if c.get("compliance_checked") else "⚠️"
            source = c.get("source", "?")
            used = c.get("times_used", 0)
            lines.append(f"{i}. {checked} [{source}] ({used}x) \"{c['caption_text'][:100]}\"")

        if len(captions) > 20:
            lines.append(f"\n... and {len(captions) - 20} more")

        await self._send_message(update.effective_chat.id, "\n".join(lines))

    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command."""
        if not self._is_authorized(update):
            return

        if self.orchestrator:
            self.orchestrator.paused = True
            self.db.log_event("USER_COMMAND", "Posting paused via Telegram")
            await self._send_message(update.effective_chat.id, "⏸️ Posting loop <b>PAUSED</b>.\nUse /resume to continue.")
        else:
            await self._send_message(update.effective_chat.id, "⚠️ Orchestrator not connected — cannot pause.")

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        if not self._is_authorized(update):
            return

        if self.orchestrator:
            self.orchestrator.paused = False
            self.db.log_event("USER_COMMAND", "Posting resumed via Telegram")
            await self._send_message(update.effective_chat.id, "▶️ Posting loop <b>RESUMED</b>.")
        else:
            await self._send_message(update.effective_chat.id, "⚠️ Orchestrator not connected — cannot resume.")

    async def _cmd_force(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /force [product] command."""
        if not self._is_authorized(update):
            return

        args = context.args
        if not args:
            await self._send_message(
                update.effective_chat.id,
                "Usage: /force [product_name]\nExample: /force Biocho"
            )
            return

        product_name = args[0]
        # Validate product exists
        if product_name not in self.products_config:
            available = ", ".join(self.products_config.keys())
            await self._send_message(
                update.effective_chat.id,
                f"❌ Unknown product: {product_name}\nAvailable: {available}"
            )
            return

        if self.orchestrator:
            self.orchestrator.force_next_product = product_name
            self.db.log_event("USER_COMMAND", f"Forced next product: {product_name}")
            await self._send_message(
                update.effective_chat.id,
                f"🎯 Next upload will be from <b>{product_name}</b> (forced)."
            )
        else:
            await self._send_message(update.effective_chat.id, "⚠️ Orchestrator not connected.")

    async def _cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /logs command."""
        if not self._is_authorized(update):
            return

        events = self.db.get_recent_events(limit=20)

        lines = ["📜 <b>Recent System Events</b>", ""]

        for e in events:
            emoji = {
                "UPLOAD_SUCCESS": "✅",
                "UPLOAD_FAIL": "❌",
                "COOKIE_WARNING": "⚠️",
                "STOCK_LOW": "⚠️",
                "PROXY_FAIL": "🚫",
                "AI_CALL": "🤖",
                "SCRAPE_COMPLETE": "🔍",
                "USER_COMMAND": "👤",
            }.get(e["event_type"], "ℹ️")

            time_str = e["occurred_at"][:16] if e["occurred_at"] else "?"
            lines.append(f"{emoji} [{time_str}] {e['message'][:100]}")

        if not events:
            lines.append("  (no events recorded yet)")

        await self._send_message(update.effective_chat.id, "\n".join(lines))

    async def _cmd_relogin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /relogin command — trigger QR code login."""
        if not self._is_authorized(update):
            return

        await self._send_message(
            update.effective_chat.id,
            " Starting QR code login...\nGenerating QR code (takes ~5 seconds)..."
        )

        try:
            # Import and run QR login
            import asyncio
            from pathlib import Path

            # Find the qr_login script
            project_root = Path(__file__).parent.parent
            qr_script = project_root / "scripts" / "qr_login.py"

            if not qr_script.exists():
                await self._send_message(
                    update.effective_chat.id,
                    "❌ QR login script not found"
                )
                return

            # Run QR login in background
            session_user = self.config.get("tiktok", {}).get("session_username", "myshop")
            uploader_dir = self.config.get("tiktok", {}).get("uploader_dir", "/opt/TiktokAutoUploader")

            # Get proxy from config (CRITICAL: login must use same proxy as uploads)
            proxy_url = self.config.get("proxy", {}).get("endpoint", "")
            if not proxy_url or proxy_url == "http://USER:PASS@HOST:PORT":
                proxy_url = None

            # Execute the QR login script
            import subprocess
            cmd = [
                sys.executable, str(qr_script),
                session_user,
                "--uploader-dir", uploader_dir,
                "--timeout", "120",
            ]
            if proxy_url:
                cmd.extend(["--proxy", proxy_url])

            # Run with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=130
            )

            if result.returncode == 0:
                # Check if QR image was generated
                import glob
                qr_files = glob.glob("/tmp/tiktok_qr_*.png")
                if qr_files:
                    qr_path = max(qr_files, key=os.path.getctime)
                    # Send QR image
                    with open(qr_path, "rb") as f:
                        await update.message.reply_photo(
                            photo=f,
                            caption="📱 Scan this QR code with TikTok app\n(Expires in 60 seconds)"
                        )
                    # Cleanup
                    os.remove(qr_path)

                # Send success message
                await self._send_message(
                    update.effective_chat.id,
                    result.stdout
                )
            else:
                await self._send_message(
                    update.effective_chat.id,
                    f"❌ QR login failed:\n{result.stderr[:500]}"
                )

        except subprocess.TimeoutExpired:
            await self._send_message(
                update.effective_chat.id,
                " QR login timed out (120s)"
            )
        except Exception as e:
            await self._send_message(
                update.effective_chat.id,
                f"❌ Error: {str(e)[:500]}"
            )

    async def _handle_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle unrecognized messages."""
        if not self._is_authorized(update):
            return
        await self._send_message(
            update.effective_chat.id,
            "🤔 Unknown command. Available commands:\n"
            "/status /growth /stock /captions /pause /resume /force /logs"
        )

    # =========================================================================
    # OUTBOUND NOTIFICATIONS (called by orchestrator)
    # =========================================================================

    def send_notification(self, message: str):
        """Send a notification message to the authorized user (thread-safe)."""
        if not self.bot_token or self.bot_token == "YOUR_BOT_TOKEN_HERE":
            return
        if not self.allowed_user_id:
            return

        # Use synchronous Bot API for notifications from the orchestrator thread
        try:
            bot = Bot(token=self.bot_token)
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                bot.send_message(
                    chat_id=self.allowed_user_id,
                    text=message,
                    parse_mode="HTML"
                )
            )
            loop.close()
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    def notify_upload_success(self, product_name: str, caption: str,
                              stock_report: dict, posts_today: int, target: int):
        """Send upload success notification."""
        now_myt = datetime.now(MYT)

        lines = [
            f"✅ <b>Posted: {product_name}</b>",
            f"🕐 Time: {now_myt.strftime('%I:%M %p')} MYT",
        ]

        # Stock summary
        stock_parts = []
        for product, info in stock_report.items():
            count = info.get("count", info) if isinstance(info, dict) else info
            warn = " ⚠️" if (count if isinstance(count, int) else 0) < 5 else ""
            name = product
            stock_parts.append(f"{name} ({count} left{warn})")
        lines.append(f"📦 Stock: {', '.join(stock_parts)}")

        lines.append(f"📋 Caption: \"{caption[:80]}\"")
        lines.append(f"🔢 Posts today: {posts_today}/{target}")

        self.send_notification("\n".join(lines))

    def notify_upload_failure(self, product_name: str, error_msg: str,
                              video_path: str, will_retry: bool = True):
        """Send upload failure notification."""
        now_myt = datetime.now(MYT)

        lines = [
            f"❌ <b>Upload FAILED: {product_name}</b>",
            f"🕐 Time: {now_myt.strftime('%I:%M %p')} MYT",
            f"💥 Error: {error_msg[:200]}",
            f"📁 Video: {os.path.basename(video_path)}",
        ]

        if will_retry:
            retry_min = self.posting_config.get("retry_delay_minutes", 15)
            lines.append(f"🔁 Will retry in {retry_min} minutes")

        self.send_notification("\n".join(lines))

    def notify_warning(self, warning_type: str, message: str):
        """Send a warning notification."""
        emoji = {
            "stock_low": "⚠️",
            "cookie": "⚠️",
            "proxy": "⚠️",
        }.get(warning_type, "⚠️")

        self.send_notification(f"{emoji} <b>{warning_type.upper()}</b>: {message}")
