"""Deterministic, CPU-only slide rendering. Text is measured, never cropped."""

from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from aishorts.modules.script.script import SlideMedia
from aishorts.modules.slides.style import PALETTES, SlideRenderConfig, layout_regions


class SlideOverflowError(ValueError):
    """A slide cannot fit legibly; ask the script writer to shorten it."""


@lru_cache(maxsize=128)
def _font(size: int, bold: bool = False):
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(files("aishorts.resources") / "fonts" / filename), size)


def _wrap(draw, text, font, width):
    lines = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            if draw.textlength(word, font=font) > width:
                # URLs and long unbroken words still fit without disappearing.
                pieces, piece = [], ""
                for char in word:
                    if piece and draw.textlength(piece + char, font=font) > width:
                        pieces.append(piece)
                        piece = ""
                    piece += char
                pieces.append(piece)
            else:
                pieces = [word]
            for piece in pieces:
                candidate = f"{line} {piece}".strip()
                if line and draw.textlength(candidate, font=font) > width:
                    lines.append(line)
                    line = piece
                else:
                    line = candidate
        lines.append(line)
    return lines


def text_box(draw, text, box, color, size=38, minimum=26, bold=False):
    """Fit with wrapping and bounded font reduction; fail instead of clipping."""
    if not text:
        return 0
    x, y, width, height = box
    for chosen in range(size, minimum - 1, -1):
        font = _font(chosen, bold)
        lines = _wrap(draw, text, font, width)
        line_height = round(chosen * 1.35)
        if len(lines) * line_height <= height:
            for i, line in enumerate(lines):
                draw.text((x, y + i * line_height), line, font=font, fill=color, anchor="lt")
            return len(lines) * line_height
    raise SlideOverflowError(f"Text does not fit at {minimum}px: {text[:80]!r}")


def _items(draw, slide, box, palette, accent):
    x, y, w, h = box
    items = slide.items
    comparison = slide.layout == "comparison"
    horizontal = comparison and w >= 1200
    gap = 24
    cell_w = (w - gap) / 2 if horizontal else w
    cell_h = h if horizontal else (h - gap * (len(items) - 1)) / len(items)
    for i, item in enumerate(items):
        cx = x + i * (cell_w + gap) if horizontal else x
        cy = y if horizontal else y + i * (cell_h + gap)
        draw.rounded_rectangle((cx, cy, cx + cell_w, cy + cell_h), radius=18, fill=palette["panel"])
        process = slide.layout == "process"
        gutter = 82 if process else 28
        if process:
            draw.ellipse((cx + 20, cy + 22, cx + 64, cy + 66), fill=accent)
            text_box(draw, str(i + 1), (cx + 32, cy + 28, 32, 40), "white", size=26, minimum=26, bold=True)
            if i < len(items) - 1:
                mid = cx + 42
                draw.line((mid, cy + cell_h + 3, mid, cy + cell_h + gap - 4), fill=accent, width=3)
        heading_space = min(cell_h - 32, cell_h * (0.45 if item.body else 0.85))
        used = text_box(draw, item.heading, (cx + gutter, cy + 18, cell_w - gutter - 24, heading_space),
                        palette["ink"], size=42 if horizontal else 34, minimum=24, bold=True)
        if item.body:
            text_box(draw, item.body, (cx + gutter, cy + 24 + used, cell_w - gutter - 24, cell_h - used - 42),
                     palette["muted"], size=34 if horizontal else 30, minimum=23)


def _chart(draw, slide, box, palette, accent):
    x, y, w, h = box
    # Zero-based, signed horizontal bars: negative values are never made positive.
    values = [point.value for point in slide.chart]
    lo, hi = min(0, min(values)), max(0, max(values))
    if hi == lo:
        hi = 1
    label_w = w * 0.28
    plot_x, plot_w = x + label_w, w * 0.49
    zero_x = plot_x + (0 - lo) / (hi - lo) * plot_w
    row_h = (h - 60) / len(values)
    draw.line((zero_x, y, zero_x, y + h - 48), fill=palette["line"], width=3)
    for i, point in enumerate(slide.chart):
        row_y = y + i * row_h
        text_box(draw, point.label, (x, row_y + 8, label_w - 20, row_h - 12), palette["ink"], size=30, minimum=23)
        end_x = plot_x + (point.value - lo) / (hi - lo) * plot_w
        left, right = sorted((zero_x, end_x))
        if right - left >= 1:
            draw.rounded_rectangle((left, row_y + 10, right, row_y + row_h - 18), radius=5, fill=accent)
        value = f"{point.value:,.6g} {slide.unit}".strip()
        text_box(draw, value, (plot_x + plot_w + 18, row_y + 8, w * 0.23 - 18, row_h - 12), palette["ink"], size=29, minimum=21, bold=True)
    text_box(draw, "0", (zero_x - 8, y + h - 40, 80, 36), palette["muted"], size=23, minimum=23)


def render_slide(slide: SlideMedia, config: SlideRenderConfig, output: str | Path | None = None):
    if (config.width, config.height) != ((1080, 1920) if config.mode == "briefing" else (1920, 1080)):
        raise ValueError("Slide dimensions must match the presentation mode")
    palette = PALETTES[config.style.theme]
    accent = config.style.accent_color
    image = Image.new("RGB", (config.width, config.height), palette["bg"])
    draw = ImageDraw.Draw(image)
    portrait = config.mode == "briefing"
    w, h = image.size
    margin = 72 if portrait else 80
    draw.rectangle((0, 0, w, 10), fill=accent)
    brand = config.style.brand_name or {"lecture": "LEARNING NOTES", "documentary": "FIELD NOTES", "briefing": "THE BRIEF"}[config.mode]
    text_box(draw, brand, (margin, 64, w - 300, 60), palette["muted"], size=25, minimum=22, bold=True)
    text_box(draw, f"{config.chapter:02d} / {config.chapters:02d}", (w - 210, 64, 140, 50), palette["muted"], size=25, minimum=22)
    title_y, title_h = (170, 260) if portrait else (134, 142)
    text_box(draw, slide.title, (margin, title_y, w - 2 * margin, title_h), palette["ink"],
             size=76 if portrait else 60, minimum=48 if portrait else 42, bold=True)
    box, visual = layout_regions(config)
    x, y, bw, bh = box
    if visual:
        vx, vy, vw, vh = visual
        draw.rounded_rectangle((vx, vy, vx + vw, vy + vh), radius=20, fill=palette["panel"])
    if slide.layout in {"title", "quote"}:
        if slide.layout == "quote":
            draw.rectangle((x, y + 12, x + 6, y + bh - 20), fill=accent)
            x, bw = x + 36, bw - 36
        text_box(draw, slide.subtitle, (x, y + 28, bw, bh - 56), palette["ink"], size=56 if bw > 850 else 42, minimum=30)
    else:
        if slide.subtitle:
            used = text_box(draw, slide.subtitle, (x, y, bw, min(130, bh * 0.25)), palette["muted"], size=32, minimum=24)
            y, bh = y + used + 28, bh - used - 28
        if slide.layout == "chart":
            _chart(draw, slide, (x, y, bw, bh), palette, accent)
        else:
            _items(draw, slide, (x, y, bw, bh), palette, accent)
    footer_y = 1622 if portrait else 878
    source = " · ".join(filter(None, (slide.source, config.attribution)))
    text_box(draw, source, (margin, footer_y, w - 2 * margin, 80), palette["muted"], size=21, minimum=17)
    # The caption band is kept separate from teaching content in every layout.
    caption_y = 1730 if portrait else 978
    if config.style.show_captions:
        draw.rectangle((0, caption_y - 20, w, h), fill=palette["panel"])
    draw.rectangle((margin, caption_y - 36, w - margin, caption_y - 32), fill=palette["line"])
    draw.rectangle((margin, caption_y - 36, margin + (w - 2 * margin) * config.chapter / config.chapters, caption_y - 32), fill=accent)
    if output is None:
        return image
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)
    return str(path)
