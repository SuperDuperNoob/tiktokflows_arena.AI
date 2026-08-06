"""Skia adapter for text rendering with emoji support."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import random
import os
from services.infrastructure.config import get_config


class SkiaAdapter:
    """Adapter for Skia text rendering."""

    def __init__(self):
        self.config = get_config()

    def render(self, text: str, style: Dict[str, Any], width: int, height: int,
               output_png: str) -> bool:
        """Render text with emoji to PNG using Skia."""
        try:
            import skia
        except ImportError:
            return False

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
            return True
        except Exception:
            return False

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
                        tf = skia.Typeface.MakeFromFile(fp)
                        if tf:
                            return tf

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
                          start_y: float, width: int, height: int, style: Dict[str, Any], skia):
        # Render box background
        pass

    def _render_layered_text(self, canvas, lines: List[str], font, font_size: int,
                             start_y: float, width: int, style: Dict[str, Any], skia):
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
                canvas.drawTextBlob(skia.TextBlob(line, font), x + shadow_offset[0], y + shadow_offset[1], paint)

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