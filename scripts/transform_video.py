"""
Video Transformation Engine v2

Renders text overlays (including emojis) as transparent PNGs using Skia
(preferred) or Playwright (fallback) for proper font rendering, then
composites them onto the video via FFmpeg's overlay filter.

Why PNG overlay instead of FFmpeg drawtext?
  FFmpeg's drawtext uses FreeType, which cannot render color emoji on Linux.
  By rendering text+emoji to a PNG first (via Skia or a browser engine),
  we get full emoji fidelity, then composite that PNG on the video.

Renderer: Skia (primary, ~30MB RAM) or Playwright (fallback, ~400MB).
  For a 4GB VPS, Skia is the clear winner. Setup script pre-installs the
  same web fonts (Outfit, Inter, Montserrat, Poppins) so Skia never needs
  Playwright as fallback.

Style system: 8 TikTok-native overlay styles — bold text with thick
  outlines, hard shadows, and the classic yellow/white/red TikTok palette.

Transformations applied:
A. Speed micro-randomization (0.97–1.06x)
B. Brightness/contrast micro-shift
C. Frame trim (random start cut)
D. Text overlay with emoji — TikTok-native styles, PNG composite
E. Audio replacement with royalty-free tracks
F. Quality guards (frame count, bitrate floor, motion guard)

Encoding: CRF 23, maxrate 5M, high profile 4.0, yuv420p
Optimized for 2 CPU / 4GB VPS.
"""
import os
import re
import json
import random
import subprocess
import shutil
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional, List, Dict

logger = logging.getLogger(__name__)


# =============================================================================
# TIKTOK-NATIVE OVERLAY STYLES
# =============================================================================
#
# These replicate the visual styles you see on actual TikTok Shop videos:
# bold sans-serif text, thick outlines, hard shadows, high contrast.
#
# Each style is defined with:
#   - name: human-readable label
#   - fill: text fill color (R, G, B)
#   - outline_color: stroke color (R, G, B)
#   - outline_width: stroke thickness in pixels (thick = bold TikTok look)
#   - shadow_color: drop shadow color (R, G, B, A)
#   - shadow_offset: (dx, dy) pixel offset for shadow
#   - shadow_blur: blur radius (0 = hard shadow, which is the TikTok look)
#   - css: equivalent CSS for Playwright fallback rendering
#   - weight: selection probability weight (higher = picked more often)
#
# The key to the TikTok look: THICK outlines + hard shadows + bold fonts.
# Thin text with soft shadows looks like a filter. We want POP.

TIKTOK_STYLES: List[Dict] = [
    # ── STYLE 1: Classic Yellow ──────────────────────────────────────────
    # The #1 most common TikTok Shop style. Gold text, black outline,
    # hard shadow. This is the "beg kuning" look.
    {
        "name": "classic_yellow",
        "fill": (255, 215, 0),           # Gold #FFD700
        "outline_color": (0, 0, 0),       # Black
        "outline_width": 8,               # Thick — signature TikTok boldness
        "shadow_color": (0, 0, 0, 180),   # Semi-transparent black
        "shadow_offset": (3, 4),          # Down-right, hard
        "shadow_blur": 0,                 # No blur — sharp TikTok shadow
        "css": "color: #FFD700; text-shadow: 3px 4px 0px #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000;",
        "weight": 30,                     # Most common — 30% of the time
    },

    # ── STYLE 2: Bold White ──────────────────────────────────────────────
    # Clean white text with heavy black outline + drop shadow.
    # Maximum readability on any background.
    {
        "name": "bold_white",
        "fill": (255, 255, 255),          # Pure white
        "outline_color": (0, 0, 0),       # Black
        "outline_width": 8,
        "shadow_color": (0, 0, 0, 200),
        "shadow_offset": (4, 4),
        "shadow_blur": 0,
        "css": "color: #FFFFFF; text-shadow: 4px 4px 0px #000, -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000;",
        "weight": 25,
    },

    # ── STYLE 3: Bright Yellow ───────────────────────────────────────────
    # Saturated yellow with extra-thick outline. No shadow — the outline
    # alone provides enough pop. Maximum visibility.
    {
        "name": "bright_yellow",
        "fill": (255, 255, 0),            # Pure yellow #FFFF00
        "outline_color": (0, 0, 0),
        "outline_width": 10,              # Extra thick — loudest style
        "shadow_color": None,             # No shadow needed
        "shadow_offset": (0, 0),
        "shadow_blur": 0,
        "css": "color: #FFFF00; text-shadow: -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000, 0 -4px 0 #000, 0 4px 0 #000, -4px 0 0 #000, 4px 0 0 #000;",
        "weight": 15,
    },

    # ── STYLE 4: TikTok Red ──────────────────────────────────────────────
    # TikTok brand red with white keyline + black shadow. Used sparingly
    # for urgency/CTA emphasis. Attention-grabbing.
    {
        "name": "tiktok_red",
        "fill": (254, 44, 85),            # TikTok red #FE2C55
        "outline_color": (255, 255, 255), # White keyline
        "outline_width": 6,
        "shadow_color": (0, 0, 0, 200),
        "shadow_offset": (3, 4),
        "shadow_blur": 0,
        "css": "color: #FE2C55; text-shadow: -2px -2px 0 #FFF, 2px -2px 0 #FFF, -2px 2px 0 #FFF, 2px 2px 0 #FFF, 3px 4px 0px #000;",
        "weight": 10,
    },

    # ── STYLE 5: White with Yellow Glow ──────────────────────────────────
    # White fill with a yellow outer stroke effect (simulated by rendering
    # a yellow outline layer behind the black outline). Gives a warm,
    # inviting feel — popular for beauty/skincare products.
    {
        "name": "white_yellow_glow",
        "fill": (255, 255, 255),          # White
        "outline_color": (0, 0, 0),       # Black inner outline
        "outline_width": 6,
        "glow_color": (255, 200, 0),      # Yellow outer glow
        "glow_width": 12,                 # Wider yellow layer behind
        "shadow_color": (0, 0, 0, 150),
        "shadow_offset": (2, 3),
        "shadow_blur": 0,
        "css": "color: #FFFFFF; text-shadow: 0 0 8px #FFC800, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000, 3px 3px 0 #000;",
        "weight": 8,
    },

    # ── STYLE 6: Yellow with Red Accent Shadow ───────────────────────────
    # Yellow text, black outline, with a subtle red shadow. Unique combo
    # that stands out from the typical yellow/white crowd.
    {
        "name": "yellow_red_shadow",
        "fill": (255, 215, 0),            # Gold
        "outline_color": (0, 0, 0),
        "outline_width": 8,
        "shadow_color": (200, 30, 30, 160),  # Dark red shadow
        "shadow_offset": (3, 4),
        "shadow_blur": 0,
        "css": "color: #FFD700; text-shadow: 3px 4px 0px #C81E1E, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000;",
        "weight": 7,
    },

    # ── STYLE 7: White with Black Box ────────────────────────────────────
    # White text inside a semi-transparent black rounded rectangle.
    # Clean, modern, very readable. Good for longer captions.
    {
        "name": "white_on_black_box",
        "fill": (255, 255, 255),
        "outline_color": None,            # No outline — box provides contrast
        "outline_width": 0,
        "shadow_color": None,
        "shadow_offset": (0, 0),
        "shadow_blur": 0,
        "box_bg": (0, 0, 0, 160),         # Semi-transparent black box
        "box_padding": 20,                # Pixels of padding around text
        "box_radius": 16,                 # Corner radius
        "css": "color: #FFFFFF; background: rgba(0,0,0,0.65); padding: 12px 24px; border-radius: 12px;",
        "weight": 5,
    },

    # ── STYLE 8: Fire / Urgency ──────────────────────────────────────────
    # Orange-red fill with yellow outer stroke + black outline. Maximum
    # urgency — for "stok terhad" / "checkout sekarang" type CTAs.
    {
        "name": "fire_urgency",
        "fill": (255, 69, 0),             # OrangeRed #FF4500
        "outline_color": (0, 0, 0),       # Black
        "outline_width": 8,
        "glow_color": (255, 255, 0),      # Yellow outer
        "glow_width": 14,
        "shadow_color": (0, 0, 0, 200),
        "shadow_offset": (3, 4),
        "shadow_blur": 0,
        "css": "color: #FF4500; text-shadow: 0 0 6px #FFFF00, -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000, 4px 4px 0 #000;",
        "weight": 5,                      # Rare — reserve for urgency
    },
]


def pick_style(force_style: str = None) -> Dict:
    """Pick a TikTok overlay style.

    Args:
        force_style: If set, always return this style (for testing/branding).
                    If None, use weighted random selection.

    Returns:
        Style dict from TIKTOK_STYLES
    """
    if force_style:
        # Find the forced style
        for s in TIKTOK_STYLES:
            if s["name"] == force_style:
                return s
        logger.warning(f"Unknown style '{force_style}', falling back to random")

    # Weighted random selection
    styles = [s["name"] for s in TIKTOK_STYLES]
    weights = [s["weight"] for s in TIKTOK_STYLES]
    chosen_name = random.choices(styles, weights=weights, k=1)[0]
    return next(s for s in TIKTOK_STYLES if s["name"] == chosen_name)


# =============================================================================
# MALAY MARKET CAPTION BUILDER (anti-spam variety)
# =============================================================================

CTA_POOL = [
    "tekan beg kuning bawah 🛒",
    "beg kuning ada di bawah ya",
    "checkout sekarang sebelum habis!",
    "stok terhad, cepat grab!",
    "tekan beg kuning sekarang 👇",
    "jangan tunggu lagi, stok tinggal sikit",
    "link di beg kuning, terus checkout",
    "promosi hari ni je, esok harga naik",
    "dah ramai borong, tinggal sikit je lagi",
    "tap beg kuning untuk dapatkan diskaun",
]

HOOK_POOL = [
    "korang pernah rasa...",
    "eh korang tau tak?",
    "tiba-tiba viral sebab...",
    "aku baru perasan...",
    "penyesalan terbesar...",
    "lepas pakai ni baru faham...",
    "jujur cakap...",
    "kenapa takde orang bagitau awal?",
    "ini yang aku cari selama ni!",
    "serius tak tipu...",
]

BENEFIT_CONNECTORS = ["sebab", "yang buat", "memang", "terus rasa", "auto jadi"]

EMOJI_POOL = ["😭", "🥰", "🔥", "💛", "🤲", "🛒", "👇", "✨", "💔", "🥹", "💯", "❤️"]

# Fonts for overlay rendering
FONTS = ["Outfit", "Inter", "Montserrat", "Poppins", "Plus Jakarta Sans"]


def build_overlay_caption(base_caption: str = None) -> str:
    """
    Build an overlay caption with TikTok Shop structure:
    hook + product benefit + emoji cluster + CTA

    3 random structures to avoid pattern detection.
    """
    base = base_caption or random.choice(HOOK_POOL)
    hook = random.choice(HOOK_POOL)
    cta = random.choice(CTA_POOL)
    emoji_str = "".join(random.choices(EMOJI_POOL, k=random.randint(1, 3)))

    struct = random.choice([1, 2, 3])

    if struct == 1:
        caption = f"{hook} {base} {emoji_str}\n{cta}"
    elif struct == 2:
        connector = random.choice(BENEFIT_CONNECTORS)
        caption = f"{base} {emoji_str}\n{connector} {hook}\n{cta}"
    else:
        caption = f"{base}\n{emoji_str} {cta}"

    # Anti-detection: occasional double-space
    if random.random() < 0.4:
        caption = caption.replace(" ", "  ", 1)

    # Cap at 180 chars for overlay readability
    if len(caption) > 180:
        caption = caption[:177] + "..."

    return caption


# =============================================================================
# ENCODING CONFIG (optimized for 2CPU/4GB VPS)
# =============================================================================

FFMPEG_THREADS = os.environ.get("FFMPEG_THREADS", "1")
FFMPEG_PRESET = os.environ.get("FFMPEG_PRESET", "veryfast")
FFMPEG_CRF = os.environ.get("FFMPEG_CRF", "23")
FFMPEG_MAXRATE = os.environ.get("FFMPEG_MAXRATE", "5M")
FFMPEG_BUFSIZE = os.environ.get("FFMPEG_BUFSIZE", "8M")
FFMPEG_ABR = os.environ.get("FFMPEG_ABR", "128k")
MIN_MB_PER_SEC = float(os.environ.get("MIN_MB_PER_SEC", "0.30"))
MIN_OUTPUT_FRAMES = int(os.environ.get("MIN_OUTPUT_FRAMES", "10"))


# =============================================================================
# SKIA TEXT RENDERER (TikTok-native styles with emoji)
# =============================================================================

class TextRenderer:
    """
    Renders text with emoji to a transparent PNG using Skia.

    Produces the authentic TikTok Shop look:
    - Bold sans-serif font (800-900 weight)
    - Thick outline (6-10px) for readability
    - Hard drop shadow (no blur) for depth
    - Optional glow layer for combo styles
    - Full color emoji support via Noto Color Emoji
    """

    def __init__(self):
        self.font_paths = [
            "/usr/local/share/fonts/tiktok/",  # Our installed web fonts
            "/usr/share/fonts/truetype/noto/",
            "/usr/share/fonts/truetype/dejavu/",
            "/usr/share/fonts/",
        ]

    def render(self, text: str, style: Dict, width: int, height: int,
               output_png: str) -> bool:
        """
        Render text with emoji to PNG using a TikTok-native style.

        Rendering order (back to front):
        1. Drop shadow (if style has one)
        2. Glow layer (if style has one — e.g., yellow outer glow)
        3. Outline stroke (thick, for TikTok boldness)
        4. Text fill (the actual color)

        Args:
            text: Caption text with emojis
            style: Dict from TIKTOK_STYLES
            width: Video width
            height: Video height
            output_png: Output PNG path

        Returns:
            True if rendering succeeded
        """
        try:
            import skia
        except ImportError:
            logger.warning("Skia not available — trying Playwright fallback")
            return self._render_playwright(text, style, width, height, output_png)

        try:
            # Create transparent surface
            info = skia.ImageInfo.MakeN32Premul(width, height)
            surface = skia.Surface.MakeRaster(info)
            canvas = surface.getCanvas()
            canvas.clear(skia.ColorTRANSPARENT)

            # Load font
            typeface = self._load_typeface(skia)
            font_size = random.randint(62, 82)
            font = skia.Font(typeface, font_size)

            # Word-wrap text
            max_w = width * 0.85
            lines = self._wrap_text(text, font, max_w)
            if not lines:
                return False

            # Calculate position (center with bottom bias)
            line_height = font_size * 1.3
            total_h = len(lines) * line_height
            y_bias = random.uniform(0.38, 0.44)
            start_y = height * y_bias - total_h / 2

            # Check if this is a "box" style (white text on black background)
            if style.get("box_bg"):
                self._render_box_style(canvas, lines, font, font_size,
                                       start_y, width, height, style, skia)
            else:
                # Standard layered rendering: shadow → glow → outline → fill
                self._render_layered_text(canvas, lines, font, font_size,
                                          start_y, width, style, skia)

            # Save PNG
            img = surface.makeImageSnapshot()
            img.save(output_png, skia.kPNG)
            logger.info(f"Rendered: {style['name']} → {output_png}")
            return True

        except Exception as e:
            logger.error(f"Skia render failed: {e}")
            # Try Playwright as last resort
            return self._render_playwright(text, style, width, height, output_png)

    def _load_typeface(self, skia):
        """Load the best available font typeface."""
        # Search order: web fonts → Noto → DejaVu → default
        search_dirs = [
            "/usr/local/share/fonts/tiktok",
            "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts",
        ]
        # Prefer bold/black weights for TikTok look
        preferred_names = [
            "Outfit-Black", "Outfit-Bold",
            "Inter-Bold", "Inter-Black",
            "Montserrat-Black", "Montserrat-Bold",
            "Poppins-Black", "Poppins-Bold",
            "PlusJakartaSans-ExtraBold", "PlusJakartaSans-Bold",
            "NotoSans-Bold", "DejaVuSans-Bold",
        ]

        for dir_path in search_dirs:
            if not os.path.isdir(dir_path):
                continue
            for name in preferred_names:
                for ext in [".ttf", ".otf"]:
                    fp = os.path.join(dir_path, name + ext)
                    if os.path.exists(fp):
                        try:
                            tf = skia.Typeface.MakeFromFile(fp)
                            if tf:
                                logger.debug(f"Loaded font: {fp}")
                                return tf
                        except Exception:
                            pass
                # Also try any .ttf in the dir
                for f in sorted(os.listdir(dir_path)):
                    if f.endswith((".ttf", ".otf")) and ("bold" in f.lower() or "black" in f.lower() or "heavy" in f.lower()):
                        fp = os.path.join(dir_path, f)
                        try:
                            tf = skia.Typeface.MakeFromFile(fp)
                            if tf:
                                return tf
                        except Exception:
                            pass

        # Fallback: any font at all
        for dir_path in search_dirs:
            if not os.path.isdir(dir_path):
                continue
            for f in sorted(os.listdir(dir_path)):
                if f.endswith((".ttf", ".otf")):
                    fp = os.path.join(dir_path, f)
                    try:
                        tf = skia.Typeface.MakeFromFile(fp)
                        if tf:
                            return tf
                    except Exception:
                        pass

        return skia.Typeface.MakeDefault()

    def _wrap_text(self, text: str, font, max_width: float) -> List[str]:
        """Word-wrap text to fit within max_width."""
        lines = []
        words = text.replace("\n", " \n ").split(" ")
        cur = ""
        for w in words:
            if w == "\n":
                if cur:
                    lines.append(cur)
                cur = ""
                continue
            test = cur + " " + w if cur else w
            if font.measureText(test) > max_width and cur:
                lines.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines

    def _render_layered_text(self, canvas, lines: List[str], font, font_size: int,
                             start_y: float, width: int, style: Dict, skia):
        """
        Render text in layers (back to front):
        1. Drop shadow
        2. Glow layer (outer stroke)
        3. Outline (thick black stroke)
        4. Fill (text color)
        """
        line_height = font_size * 1.3
        fill_color = style["fill"]
        outline_color = style.get("outline_color")
        outline_width = style.get("outline_width", 8)
        shadow_color = style.get("shadow_color")
        shadow_offset = style.get("shadow_offset", (0, 0))
        glow_color = style.get("glow_color")
        glow_width = style.get("glow_width", 0)

        for i, line in enumerate(lines):
            tw = font.measureText(line)
            x = (width - tw) / 2
            y = start_y + i * line_height

            # Layer 1: Drop shadow
            if shadow_color and shadow_color[3] > 0:
                dx, dy = shadow_offset
                shadow_paint = skia.Paint(
                    AntiAlias=True,
                    Color=skia.Color(*shadow_color),
                )
                canvas.drawString(line, x + dx, y + dy, font, shadow_paint)

            # Layer 2: Glow (wide outer stroke in glow color)
            if glow_color and glow_width > 0:
                glow_paint = skia.Paint(
                    AntiAlias=True,
                    Style=skia.Paint.kStroke_Style,
                    Color=skia.Color(*glow_color),
                    StrokeWidth=glow_width,
                    StrokeJoin=skia.Paint.kRound_Join,
                )
                canvas.drawString(line, x, y, font, glow_paint)

            # Layer 3: Outline (thick stroke)
            if outline_color and outline_width > 0:
                outline_paint = skia.Paint(
                    AntiAlias=True,
                    Style=skia.Paint.kStroke_Style,
                    Color=skia.Color(*outline_color),
                    StrokeWidth=outline_width,
                    StrokeJoin=skia.Paint.kRound_Join,
                )
                canvas.drawString(line, x, y, font, outline_paint)

            # Layer 4: Fill (text color on top)
            fill_paint = skia.Paint(
                AntiAlias=True,
                Color=skia.Color(*fill_color),
            )
            canvas.drawString(line, x, y, font, fill_paint)

    def _render_box_style(self, canvas, lines: List[str], font, font_size: int,
                          start_y: float, width: int, height: int, style: Dict, skia):
        """Render white text inside a semi-transparent black rounded box."""
        line_height = font_size * 1.3
        padding = style.get("box_padding", 20)
        radius = style.get("box_radius", 16)
        bg_color = style.get("box_bg", (0, 0, 0, 160))

        # Calculate total text dimensions
        max_line_w = max(font.measureText(line) for line in lines)
        total_h = len(lines) * line_height

        # Box dimensions
        box_w = max_line_w + padding * 2
        box_h = total_h + padding * 2
        box_x = (width - box_w) / 2
        box_y = start_y - padding

        # Draw rounded rectangle background
        rect = skia.RRect.MakeRectXY(
            skia.Rect.MakeXYWH(box_x, box_y, box_w, box_h),
            radius, radius
        )
        bg_paint = skia.Paint(
            AntiAlias=True,
            Color=skia.Color(*bg_color),
            Style=skia.Paint.kFill_Style,
        )
        canvas.drawRRect(rect, bg_paint)

        # Draw text (white fill, no outline needed — box provides contrast)
        fill_paint = skia.Paint(
            AntiAlias=True,
            Color=skia.Color(255, 255, 255),
        )
        for i, line in enumerate(lines):
            tw = font.measureText(line)
            x = (width - tw) / 2
            y = start_y + i * line_height
            canvas.drawString(line, x, y, font, fill_paint)

    def _render_playwright(self, text: str, style: Dict, width: int, height: int,
                           output_png: str) -> bool:
        """Fallback: render via headless Chromium."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Neither Skia nor Playwright available")
            return False

        css = style.get("css", "color: #FFD700; text-shadow: 2px 2px 0 #000;")
        font_family = random.choice(FONTS)
        font_size = random.randint(62, 78)
        margin_bottom = random.randint(35, 45)

        safe_text = text.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        font_url = font_family.replace(" ", "+")

        html = f"""<!DOCTYPE html><html><head><style>
        @import url('https://fonts.googleapis.com/css2?family={font_url}:wght@800;900&display=swap');
        html,body{{margin:0;padding:0;width:100%;height:100%;background:transparent;
        display:flex;justify-content:center;align-items:center;overflow:hidden}}
        .caption{{text-align:center;width:82%;
        font-family:'{font_family}','Noto Color Emoji','Segoe UI Emoji',sans-serif;
        font-weight:900;line-height:1.35;white-space:pre-line;word-wrap:break-word;
        margin-bottom:{margin_bottom}%;box-sizing:border-box;{css}}}
        </style></head><body><div class="caption">{safe_text}</div>
        <script>
        const box=document.querySelector('.caption');
        const maxW=window.innerWidth*0.85;const maxH=window.innerHeight*0.45;
        let fs={font_size};box.style.fontSize=fs+'px';
        while((box.scrollHeight>maxH||box.scrollWidth>maxW)&&fs>30)
        {{fs-=2;box.style.fontSize=fs+'px';}}
        </script></body></html>"""

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=[
                    "--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox",
                    "--disable-extensions", "--renderer-process-limit=1",
                ])
                ctx = browser.new_context(viewport={"width": width, "height": height})
                page = ctx.new_page()
                page.set_content(html, wait_until="domcontentloaded", timeout=10000)
                try:
                    page.evaluate("document.fonts.ready")
                except Exception:
                    pass
                page.wait_for_timeout(200)
                page.screenshot(path=output_png, omit_background=True)
                browser.close()
            logger.info(f"Playwright render: {style['name']} → {output_png}")
            return True
        except Exception as e:
            logger.error(f"Playwright render failed: {e}")
            return False


# =============================================================================
# MAIN TRANSFORMER
# =============================================================================

class VideoTransformer:
    """Transforms raw videos into unique processed videos with TikTok-native overlays."""

    def __init__(self, config: dict):
        self.config = config
        self.processed_dir = config.get("processed_dir", "content/processed")
        self.sounds_dir = config.get("sounds_dir", "sounds")
        self.failed_dir = config.get("failed_dir", "content/failed")
        self.renderer = TextRenderer()
        os.makedirs(self.processed_dir, exist_ok=True)
        os.makedirs(self.failed_dir, exist_ok=True)

    def transform(self, raw_video_path: str, product_name: str,
                  caption_text: str, audio_mode: str = "mix") -> Tuple[str, dict]:
        """
        Transform a raw video with TikTok-native overlay.

        Returns:
            (output_path, params) where params includes style info, quality metrics, etc.
        """
        params = {}

        # Probe video
        width, height = self._get_video_resolution(raw_video_path)
        duration = self._get_video_duration(raw_video_path)
        if width is None or duration is None or duration < 1.0:
            raise RuntimeError(f"Cannot probe video: {raw_video_path}")

        params["input_width"] = width
        params["input_height"] = height
        params["input_duration"] = round(duration, 3)

        # Randomize transforms
        speed = random.uniform(0.97, 1.06)
        brightness = random.uniform(-0.04, 0.04)
        contrast = random.uniform(0.97, 1.06)
        trim_start = random.uniform(0, 0.8) if random.random() < 0.7 else 0.0
        overlay_y = random.uniform(0.35, 0.50)

        params.update({
            "speed_factor": round(speed, 4),
            "brightness": round(brightness, 4),
            "contrast": round(contrast, 4),
            "trim_start": round(trim_start, 3),
            "overlay_y_percent": round(overlay_y * 100, 1),
        })

        # Build overlay caption
        overlay_caption = build_overlay_caption(caption_text)
        # Check config for forced style
        force_style = self.config.get("rendering", {}).get("force_style")
        style = pick_style(force_style)
        params["overlay_caption"] = overlay_caption
        params["style_name"] = style["name"]
        params["style_css"] = style.get("css", "")[:80]

        logger.info(f"Style: {style['name']} | Caption: {overlay_caption[:60]}...")

        # Render text+emoji to PNG
        tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK) else "/tmp"
        tmp_png = os.path.join(tmp_dir, f"caption_{product_name}_{int(time.time())}_{random.randint(1000,9999)}.png")

        rendered = self.renderer.render(overlay_caption, style, width, height, tmp_png)

        if not rendered or not os.path.exists(tmp_png):
            # Last resort: strip emojis and use drawtext
            logger.warning("PNG render failed — fallback to drawtext (no emojis)")
            emoji_re = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0]+", flags=re.UNICODE)
            overlay_caption = emoji_re.sub("", overlay_caption).strip()
            params["fallback_drawtext"] = True
            params["overlay_caption"] = overlay_caption
            tmp_png = None
        else:
            params["fallback_drawtext"] = False

        # Select sound
        sound_file = self._pick_random_sound()
        params["sound_file"] = os.path.basename(sound_file) if sound_file else None

        # Output path
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(self.processed_dir, f"{product_name}_{ts}_{random.randint(100,999)}.mp4")

        # FFmpeg
        self._run_ffmpeg(
            input_path=raw_video_path, output_path=output_path,
            caption_png=tmp_png, sound_file=sound_file,
            width=width, height=height, speed=speed,
            brightness=brightness, contrast=contrast,
            trim_start=trim_start, overlay_y=overlay_y,
        )

        # Cleanup PNG
        if tmp_png and os.path.exists(tmp_png):
            os.unlink(tmp_png)

        # Verify output
        if not os.path.exists(output_path):
            raise RuntimeError(f"FFmpeg did not produce output: {output_path}")

        out_size = os.path.getsize(output_path)
        if out_size < 1000:
            raise RuntimeError(f"Output too small ({out_size} bytes)")

        # Quality checks
        out_dur = self._get_video_duration(output_path) or 0
        out_frames = self._get_frame_count(output_path)
        out_mb = out_size / (1024 * 1024)
        mbps = (out_mb / out_dur) if out_dur else 0

        params.update({
            "output_path": output_path,
            "output_size_mb": round(out_mb, 2),
            "output_duration": round(out_dur, 2),
            "output_frames": out_frames,
            "mb_per_sec": round(mbps, 3),
            "low_quality": bool(out_dur and mbps < MIN_MB_PER_SEC),
        })

        # Motion guard
        if out_frames and out_frames < MIN_OUTPUT_FRAMES:
            quarantine = os.path.join(self.failed_dir, os.path.basename(output_path))
            shutil.move(output_path, quarantine)
            raise RuntimeError(f"Still image detected ({out_frames} frames). Quarantined.")

        logger.info(f"Done: {out_mb:.1f}MB, {out_dur:.1f}s, {out_frames}fr, {mbps:.2f}MB/s, style={style['name']}")
        return output_path, params

    def _run_ffmpeg(self, input_path, output_path, caption_png, sound_file,
                    width, height, speed, brightness, contrast, trim_start, overlay_y):
        """Build and execute FFmpeg command."""
        vf_parts = [
            f"trim=start={trim_start:.2f}",
            "setpts=PTS-STARTPTS",
            f"setpts=PTS/{speed:.3f}",
            f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        ]
        overlay_y_expr = f"(H-h)*{overlay_y:.3f}"

        cmd = ["ffmpeg", "-y", "-threads", FFMPEG_THREADS, "-i", input_path]

        if sound_file and os.path.exists(sound_file):
            cmd.extend(["-stream_loop", "-1", "-i", sound_file])

        if caption_png and os.path.exists(caption_png):
            cmd.extend(["-i", caption_png])
            vf = ",".join(vf_parts)
            filter_complex = (
                f"[0:v]{vf}[base];"
                f"[base][2:v]overlay=0:{overlay_y_expr}:format=auto:eof_action=repeat[outv]"
            )
            cmd.extend(["-filter_complex", filter_complex, "-map", "[outv]"])
        else:
            cmd.extend(["-vf", ",".join(vf_parts), "-map", "0:v"])

        if sound_file and os.path.exists(sound_file):
            cmd.extend(["-map", "1:a"])
        else:
            cmd.extend(["-map", "0:a?"])

        cmd.extend([
            "-c:v", "libx264", "-crf", FFMPEG_CRF, "-preset", FFMPEG_PRESET,
            "-maxrate", FFMPEG_MAXRATE, "-bufsize", FFMPEG_BUFSIZE,
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
            "-c:a", "aac", "-b:a", FFMPEG_ABR, "-ar", "44100",
            "-shortest", "-movflags", "+faststart", output_path,
        ])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr[-1000:]}")
                raise RuntimeError(f"FFmpeg exit code {result.returncode}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("FFmpeg timed out (>600s)")

    def _get_video_resolution(self, path):
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", path],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode != 0: return None, None
            s = json.loads(r.stdout)["streams"][0]
            w, h = int(s.get("width", 0)), int(s.get("height", 0))
            for sd in s.get("side_data_list", []):
                if sd.get("side_data_type") == "Display Matrix":
                    if abs(int(sd.get("rotation", 0))) in (90, 270): return h, w
            return w, h
        except Exception:
            return None, None

    def _get_video_duration(self, path):
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=15
            )
            return float(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
        except Exception:
            return None

    def _get_frame_count(self, path):
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                 "-show_entries", "stream=nb_read_packets",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=30
            )
            return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
        except Exception:
            return 0

    def _pick_random_sound(self):
        if not os.path.isdir(self.sounds_dir): return None
        files = [os.path.join(self.sounds_dir, f) for f in os.listdir(self.sounds_dir)
                 if f.lower().endswith((".mp3", ".wav", ".ogg", ".m4a"))]
        return random.choice(files) if files else None
