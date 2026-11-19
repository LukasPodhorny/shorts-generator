"""Deterministic, CPU-only slide rendering. Text is measured, never cropped."""

from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from aishorts.modules.script.script import SlideMedia
from aishorts.modules.slides.style import PALETTES, SlideRenderConfig, layout_regions


class SlideOverflowError(ValueError):
    """A slide cannot fit legibly; ask the script writer to shorten it."""


@lru_cache(maxsize=128)
def _font(size: int, bold: bool = False):
    filename = "InterDisplay-Bold.ttf" if bold else "Inter-Regular.ttf"
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


def _measure(draw, text, size, bold, width):
    font = _font(size, bold)
    lines = _wrap(draw, text, font, width) if text.strip() else []
    return font, lines, round(size * 1.26)


def _height(block):
    _, lines, leading = block
    return len(lines) * leading


def _paint(draw, block, x, y, color):
    font, lines, leading = block
    for i, line in enumerate(lines):
        draw.text((x, y + i * leading), line, font=font, fill=color, anchor="lt")


def _fit(draw, text, width, height, size, minimum, bold=False):
    for chosen in range(size, minimum - 1, -1):
        block = _measure(draw, text, chosen, bold, width)
        if _height(block) <= height:
            return block
    raise SlideOverflowError(f"Text does not fit at {minimum}px: {text[:80]!r}")


def text_box(draw, text, box, color, size=38, minimum=26, bold=False):
    """Fit with wrapping and bounded font reduction; fail instead of clipping."""
    if not text:
        return 0
    x, y, width, height = box
    block = _fit(draw, text, width, height, size, minimum, bold)
    _paint(draw, block, x, y, color)
    return _height(block)


def _items(draw, slide, box, palette, accent, *, portrait, has_visual):
    x, y, w, h = box
    count = len(slide.items)
    process = slide.layout == "process"
    comparison = slide.layout == "comparison"
    columns = 1
    if w >= 1250 and count > 1:
        columns = count if process and count <= 3 else 2
    horizontal_process = process and columns > 1
    gap = 26 if columns > 1 or not has_visual else 18
    cell_w = (w - gap * (columns - 1)) // columns
    pad_x = 32 if comparison or columns > 1 else 12
    gutter = pad_x
    if process and not horizontal_process:
        gutter += 62
    elif not comparison and not process:
        gutter += 32
    top = 72 if horizontal_process else 24
    bottom = 19 if has_visual else 26
    width = cell_w - gutter - pad_x
    heading_size, body_size = (54, 41) if not has_visual else (44, 34)
    if not portrait and columns == 1:
        heading_size, body_size = (40, 32) if has_visual else (50, 36)

    # Fit the group as a whole. Cards take the height of their text, and only
    # cards on the same row share a height.
    for reduction in range(max(heading_size - 25, body_size - 23) + 1):
        cells = []
        for item in slide.items:
            heading = _measure(draw, item.heading, max(25, heading_size - reduction), True, width)
            body = _measure(draw, item.body, max(23, body_size - reduction), False, width)
            body_gap = 9 if _height(body) else 0
            cells.append((heading, body, body_gap))
        row_heights = [
            top + max(_height(head) + spacing + _height(body) for head, body, spacing in cells[i:i + columns]) + bottom
            for i in range(0, count, columns)
        ]
        group_height = sum(row_heights) + gap * (len(row_heights) - 1)
        if group_height <= h:
            break
    else:
        raise SlideOverflowError("The teaching notes are too long for this layout")

    if has_visual:
        balance = 0.18 if portrait else 0.42
    else:
        balance = 0.14 if portrait else 0.26
    cy = y + int((h - group_height) * balance)
    for row, row_h in enumerate(row_heights):
        for col, (heading, body, body_gap) in enumerate(cells[row * columns:(row + 1) * columns]):
            i = row * columns + col
            cx = x + col * (cell_w + gap)
            if comparison or columns > 1:
                draw.rounded_rectangle((cx, cy, cx + cell_w, cy + row_h), radius=22,
                                       fill=palette["panel"], outline=palette["line"], width=2)
                if comparison:
                    color = accent if i == 0 else palette["line"]
                    draw.rounded_rectangle((cx + 10, cy + 20, cx + 14, cy + row_h - 20), radius=2, fill=color)
            else:
                draw.line((cx, cy + row_h, cx + cell_w, cy + row_h), fill=palette["line"], width=2)

            if process:
                sx, sy = cx + pad_x, cy + 16
                if columns == 1 and i + 1 < count:
                    draw.line((sx + 22, sy + 42, sx + 22, cy + row_h + gap + 16),
                              fill=palette["line"], width=2)
                draw.rounded_rectangle((sx, sy, sx + 44, sy + 38), radius=9, outline=accent, width=2)
                draw.text((sx + 22, sy + 19), f"{i + 1:02d}", fill=palette["ink"],
                          font=_font(21, True), anchor="mm")
                if horizontal_process and col + 1 < columns and i + 1 < count:
                    draw.line((cx + cell_w + 2, sy + 19, cx + cell_w + gap - 2, sy + 19), fill=accent, width=2)
            elif not comparison:
                dot_y = cy + top + 14
                draw.rounded_rectangle((cx + pad_x, dot_y, cx + pad_x + 15, dot_y + 5), radius=2, fill=accent)
            tx, ty = cx + gutter, cy + top
            _paint(draw, heading, tx, ty, palette["ink"])
            _paint(draw, body, tx, ty + _height(heading) + body_gap, palette["muted"])
        cy += row_h + gap


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
    row_h = min(94, (h - 42) / len(values))
    plot_h = row_h * len(values)
    y += int((h - plot_h - 42) * 0.38)
    draw.line((zero_x, y, zero_x, y + plot_h), fill=palette["line"], width=2)
    for i, point in enumerate(slide.chart):
        row_y = y + i * row_h
        label = _fit(draw, point.label, label_w - 20, row_h - 4, 30, 21)
        _paint(draw, label, x, row_y + (row_h - _height(label)) / 2, palette["ink"])
        end_x = plot_x + (point.value - lo) / (hi - lo) * plot_w
        left, right = sorted((zero_x, end_x))
        mid_y = row_y + row_h / 2
        half_bar = min(15, row_h / 4)
        draw.rounded_rectangle((plot_x, mid_y - half_bar, plot_x + plot_w, mid_y + half_bar),
                               radius=5, fill=palette["panel"], outline=palette["line"])
        if right - left >= 1:
            draw.rounded_rectangle((left, mid_y - half_bar, right, mid_y + half_bar), radius=5, fill=accent)
        value = f"{point.value:,.6g} {slide.unit}".strip()
        amount = _fit(draw, value, w * 0.23 - 18, row_h - 4, 28, 20, True)
        _paint(draw, amount, plot_x + plot_w + 18, row_y + (row_h - _height(amount)) / 2, palette["ink"])
    draw.text((zero_x, y + plot_h + 8), "0", font=_font(20), fill=palette["muted"], anchor="mt")


@lru_cache(maxsize=6)
def _background(width, height, theme):
    palette = PALETTES[theme]
    gradient = Image.linear_gradient("L").rotate(90).resize((width, height))
    colors = tuple(ImageColor.getrgb(palette[key]) for key in ("bg", "wash"))
    channels = [
        gradient.point([round(start + (end - start) * v / 255) for v in range(256)])
        for start, end in zip(*colors)
    ]
    return Image.merge("RGB", channels)


def _hero(draw, slide, box, palette):
    x, y, width, height = box
    head_size = 105 if width >= 900 else 84
    subtitle = _fit(draw, slide.subtitle, min(width, 1100), height * 0.40, 47, 28)
    gap = 28 if _height(subtitle) else 0
    headline = _fit(draw, slide.title, min(width, 1370), height - _height(subtitle) - gap, head_size, 42, True)
    height_used = _height(headline) + gap + _height(subtitle)
    top = y + int((height - height_used) * 0.46)
    _paint(draw, headline, x, top, palette["ink"])
    _paint(draw, subtitle, x, top + _height(headline) + gap, palette["muted"])


def _scene_indicator(draw, config, margin, palette, accent):
    w = config.width
    if config.chapters > 1:
        right = w - margin
        count = f"{config.chapter:02d} / {config.chapters:02d}"
        font = _font(24, True)
        draw.text((right, 67), count, fill=palette["ink"], font=font, anchor="rm")
        if config.chapters <= 12:
            end = right - draw.textlength(count, font=font) - 24
            step = min(22, 148 // config.chapters)
            for i in range(config.chapters):
                left = end - (config.chapters - i) * step
                color = accent if i + 1 == config.chapter else palette["line"]
                draw.rounded_rectangle((left, 64, left + step - 5, 70), radius=3, fill=color)


def _credits(draw, slide, config, margin, y, palette):
    source = "  ·  ".join(filter(None, (slide.source.strip(), config.attribution.strip())))
    if not source:
        return
    width = config.width - 2 * margin
    font = _font(20)
    # Long media credits remain in the description. Avoid overflow after the
    # assets have already been retrieved.
    lines = _wrap(draw, source, font, width)
    if len(lines) > 2:
        lines = lines[:2]
        while draw.textlength(lines[-1] + "…", font=font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    _paint(draw, (font, lines, 25), margin, y, palette["muted"])


def render_slide(slide: SlideMedia, config: SlideRenderConfig, output: str | Path | None = None):
    if (config.width, config.height) != ((1080, 1920) if config.mode == "briefing" else (1920, 1080)):
        raise ValueError("Slide dimensions must match the presentation mode")
    palette = PALETTES[config.style.theme]
    accent = config.style.accent_color
    image = _background(config.width, config.height, config.style.theme).copy()
    draw = ImageDraw.Draw(image)
    portrait = config.mode == "briefing"
    w = image.width
    margin = 72 if portrait else 88
    _scene_indicator(draw, config, margin, palette, accent)
    box, visual = layout_regions(config, slide.layout)
    x, y, bw, bh = box
    if visual:
        vx, vy, vw, vh = visual
        draw.rectangle((vx - 2, vy - 2, vx + vw + 1, vy + vh + 1),
                       fill=palette["panel"], outline=palette["line"], width=2)
    if slide.layout == "title":
        if visual is None:
            box = (x, 170, bw, 1360 if portrait else 670)
        _hero(draw, slide, box, palette)
    else:
        title_y = 156 if visual else 360 if portrait else 206
        title_h = (176 if portrait else 142) if visual else (258 if portrait else 184)
        used = text_box(draw, slide.title, (margin, title_y, w - 2 * margin, title_h),
                        palette["ink"], size=74 if portrait else 68, minimum=42, bold=True)
        if visual is None:
            bottom = y + bh
            y = title_y + used + (48 if portrait else 38)
            bh = bottom - y
        if slide.layout == "quote":
            quote = _fit(draw, slide.subtitle, min(bw - 42, 1250), bh, 62 if bw >= 850 else 50, 30)
            top = y + int((bh - _height(quote)) * 0.40)
            draw.rounded_rectangle((x, top, x + 5, top + _height(quote)), radius=2, fill=accent)
            _paint(draw, quote, x + 42, top, palette["ink"])
        elif slide.subtitle:
            used = text_box(draw, slide.subtitle, (x, y, bw, min(110, bh * 0.24)), palette["muted"], size=34, minimum=24)
            y, bh = y + used + 22, bh - used - 22
        if slide.layout == "chart":
            _chart(draw, slide, (x, y, bw, bh), palette, accent)
        elif slide.layout != "quote":
            _items(draw, slide, (x, y, bw, bh), palette, accent, portrait=portrait, has_visual=bool(visual))
    _credits(draw, slide, config, margin, 1660 if portrait else 889, palette)
    if output is None:
        return image
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)
    return str(path)
