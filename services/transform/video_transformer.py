"""Video transformation service - TikTok-native overlay styles and rendering."""
from __future__ import annotations

import os
import random
import logging
from typing import Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# TIKTOK-NATIVE OVERLAY STYLES
# =============================================================================

TIKTOK_STYLES: List[Dict] = [
    # ── STYLE 1: Classic Yellow ──────────────────────────────────────────
    {
        "name": "classic_yellow",
        "fill": (255, 215, 0),
        "outline_color": (0, 0, 0),
        "outline_width": 8,
        "shadow_color": (0, 0, 0, 180),
        "shadow_offset": (3, 4),
        "shadow_blur": 0,
        "css": "color: #FFD700; text-shadow: 3px 4px 0px #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000;",
        "weight": 30,
    },

    # ── STYLE 2: Bold White ──────────────────────────────────────────────
    {
        "name": "bold_white",
        "fill": (255, 255, 255),
        "outline_color": (0, 0, 0),
        "outline_width": 8,
        "shadow_color": (0, 0, 0, 200),
        "shadow_offset": (4, 4),
        "shadow_blur": 0,
        "css": "color: #FFFFFF; text-shadow: 4px 4px 0px #000, -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000;",
        "weight": 25,
    },

    # ── STYLE 3: Bright Yellow ───────────────────────────────────────────
    {
        "name": "bright_yellow",
        "fill": (255, 255, 0),
        "outline_color": (0, 0, 0),
        "outline_width": 10,
        "shadow_color": None,
        "shadow_offset": (0, 0),
        "shadow_blur": 0,
        "css": "color: #FFFF00; text-shadow: -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000, 0 -4px 0 #000, 0 4px 0 #000, -4px 0 0 #000, 4px 0 0 #000;",
        "weight": 15,
    },

    # ── STYLE 4: TikTok Red ──────────────────────────────────────────────
    {
        "name": "tiktok_red",
        "fill": (254, 44, 85),
        "outline_color": (255, 255, 255),
        "outline_width": 6,
        "shadow_color": (0, 0, 0, 200),
        "shadow_offset": (3, 4),
        "shadow_blur": 0,
        "css": "color: #FE2C55; text-shadow: -2px -2px 0 #FFF, 2px -2px 0 #FFF, -2px 2px 0 #FFF, 2px 2px 0 #FFF, 3px 4px 0px #000;",
        "weight": 10,
    },

    # ── STYLE 5: White with Yellow Glow ──────────────────────────────────
    {
        "name": "white_yellow_glow",
        "fill": (255, 255, 255),
        "outline_color": (0, 0, 0),
        "outline_width": 6,
        "glow_color": (255, 200, 0),
        "glow_width": 12,
        "shadow_color": (0, 0, 0, 150),
        "shadow_offset": (2, 3),
        "shadow_blur": 0,
        "css": "color: #FFFFFF; text-shadow: 0 0 8px #FFC800, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000, 3px 3px 0 #000;",
        "weight": 8,
    },

    # ── STYLE 6: Yellow with Red Accent Shadow ───────────────────────────
    {
        "name": "yellow_red_shadow",
        "fill": (255, 215, 0),
        "outline_color": (0, 0, 0),
        "outline_width": 8,
        "shadow_color": (200, 30, 30, 160),
        "shadow_offset": (3, 4),
        "shadow_blur": 0,
        "css": "color: #FFD700; text-shadow: 3px 4px 0px #C81E1E, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000;",
        "weight": 7,
    },

    # ── STYLE 7: White with Black Box ────────────────────────────────────
    {
        "name": "white_on_black_box",
        "fill": (255, 255, 255),
        "outline_color": None,
        "outline_width": 0,
        "shadow_color": None,
        "shadow_offset": (0, 0),
        "shadow_blur": 0,
        "box_bg": (0, 0, 0, 160),
        "box_padding": 20,
        "box_radius": 16,
        "css": "color: #FFFFFF; background: rgba(0,0,0,0.65); padding: 12px 24px; border-radius: 12px;",
        "weight": 5,
    },

    # ── STYLE 8: Fire / Urgency ──────────────────────────────────────────
    {
        "name": "fire_urgency",
        "fill": (255, 69, 0),
        "outline_color": (0, 0, 0),
        "outline_width": 8,
        "glow_color": (255, 255, 0),
        "glow_width": 14,
        "shadow_color": (0, 0, 0, 200),
        "shadow_offset": (3, 4),
        "shadow_blur": 0,
        "css": "color: #FF4500; text-shadow: 0 0 6px #FFFF00, -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000, 4px 4px 0 #000;",
        "weight": 5,
    },
]


def pick_style(force_style: str = None) -> Dict:
    """Pick a TikTok overlay style."""
    if force_style:
        for s in TIKTOK_STYLES:
            if s["name"] == force_style:
                return s
        logger.warning(f"Unknown style '{force_style}', falling back to random")

    styles = [s["name"] for s in TIKTOK_STYLES]
    weights = [s["weight"] for s in TIKTOK_STYLES]
    chosen_name = random.choices(styles, weights=weights, k=1)[0]
    return next(s for s in TIKTOK_STYLES if s["name"] == chosen_name)


# =============================================================================
# MALAY MARKET CAPTION BUILDER
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

FONTS = ["Outfit", "Inter", "Montserrat", "Poppins", "Plus Jakarta Sans"]


def build_overlay_caption(base_caption: str = None) -> str:
    """Build an overlay caption with TikTok Shop structure."""
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

    if random.random() < 0.4:
        caption = caption.replace(" ", "  ", 1)

    if len(caption) > 180:
        caption = caption[:177] + "..."

    return caption


# =============================================================================
# SKIA TEXT RENDERER
# =============================================================================

class TextRenderer:
    """Renders text with emoji to a transparent PNG using Skia."""

    def __init__(self):
        self.font_paths = [
            "/usr/local/share/fonts/tiktok/",
            "/usr/share/fonts/truetype/noto/",
            "/usr/share/fonts/truetype/dejavu/",
            "/usr/share/fonts/",
        ]

    def render(self, text: str, style: Dict, width: int, height: int,
               output_png: str) -> bool:
        """Render text with emoji to PNG using a TikTok-native style."""
        try:
            import skia
        except ImportError:
            logger.warning("Skia not available — trying Playwright fallback")
            return self._render_playwright(text, style, width, height, output_png)

        try:
            info = skia.ImageInfo.MakeN32Premul(width, height)
            surface = skia.Surface.MakeRaster(info)
            canvas = surface.getCanvas()
            canvas.clear(skia.ColorTRANSPARENT)

            typeface = self._load_typeface(skia)
            font_size = random.randint(62, 82)
            font = skia.Font(typeface, font_size)

            max_w = width * 0.85
            lines = self._wrap_text(text, font, max_w)
            if not lines:
                return False

            line_height = font_size * 1.3
            total_h = len(lines) * line_height
            y_bias = random.uniform(0.38, 0.44)
            start_y = height * y_bias - total_h / 2

            if style.get("box_bg"):
                self._render_box_style(canvas, lines, font, font_size,
                                       start_y, width, height, style, skia)
            else:
                self._render_layered_text(canvas, lines, font, font_size,
                                          start_y, width, style, skia)

            img = surface.makeImageSnapshot()
            img.save(output_png, skia.kPNG)
            logger.info(f"Rendered: {style['name']} → {output_png}")
            return True

        except Exception as e:
            logger.error(f"Skia render failed: {e}")
            return self._render_playwright(text, style, width, height, output_png)

    def _load_typeface(self, skia):
        search_dirs = [
            "/usr/local/share/fonts/tiktok",
            "/usr/share/fonts/truetype/noto",
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts",
        ]
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

        return skia.Typeface.MakeDefault()

    def _wrap_text(self, text: str, font, max_width: float) -> List[str]:
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

    def _render_box_style(self, canvas, lines: List[str], font, font_size: int,
                          start_y: float, width: int, height: int, style: Dict, skia):
        pass  # Simplified - box style not fully implemented

    def _render_layered_text(self, canvas, lines: List[str], font, font_size: int,
                             start_y: float, width: int, style: Dict, skia):
        """Render text in layers: shadow → glow → outline → fill."""
        line_height = font_size * 1.3
        fill_color = style["fill"]
        outline_color = style.get("outline_color")
        outline_width = style.get("outline_width", 8)
        shadow_color = style.get("shadow_color")
        shadow_offset = style.get("shadow_offset", (0, 0))
        glow_color = style.get("glow_color")
        glow_width = style.get("glow_width", 0)

        for i, line in enumerate(lines):
            y = start_y + i * line_height
            x = width / 2 - font.measureText(line) / 2

            # Shadow
            if shadow_color:
                paint = skia.Paint()
                paint.setColor(skia.Color(*shadow_color))
                canvas.drawTextBlob(skia.TextBlob(line, font),
                                    x + shadow_offset[0], y + shadow_offset[1], paint)

            # Glow
            if glow_color:
                paint = skia.Paint()
                paint.setColor(skia.Color(*glow_color))
                paint.setStyle(skia.Paint.kStroke_Style)
                paint.setStrokeWidth(glow_width)
                canvas.drawTextBlob(skia.TextBlob(line, font), x, y, paint)

            # Outline
            if outline_color and outline_width > 0:
                paint = skia.Paint()
                paint.setColor(skia.Color(*outline_color))
                paint.setStyle(skia.Paint.kStroke_Style)
                paint.setStrokeWidth(outline_width)
                canvas.drawTextBlob(skia.TextBlob(line, font), x, y, paint)

            # Fill
            paint = skia.Paint()
            paint.setColor(skia.Color(*fill_color))
            canvas.drawTextBlob(skia.TextBlob(line, font), x, y, paint)

    def _render_playwright(self, text: str, style: Dict, width: int, height: int,
                           output_png: str) -> bool:
        """Playwright fallback (not implemented)."""
        return False


class VideoTransformer:
    """Video transformation service using FFmpeg and Skia."""

    def __init__(self):
        self.renderer = TextRenderer()

    def process_video(self, input_video: Path, output_video: Path,
                      caption: str, style: Dict, width: int, height: int,
                      sound_file: Path, speed: float, brightness: float,
                      contrast: float, trim_start: float, overlay_y: float) -> bool:
        """Process a video with overlay and audio."""
        # This would integrate with FFmpegAdapter
        return False